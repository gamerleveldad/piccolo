import csv
import io
import json
import logging
import math
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
import asyncpg  # type: ignore[import]
import pandas as pd  # type: ignore[import]
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ti import calculate_ti_score

HANDCUFF_CSV_FILE = File(...)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("fantasy_api")

# Environment variables for Sleeper API and PostgreSQL connection
SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME", "your_username")
SLEEPER_SEASON = os.getenv("SLEEPER_SEASON", "2026")
SLEEPER_DYNASTY_LEAGUE_ID = os.getenv(
    "SLEEPER_DYNASTY_LEAGUE_ID", "1360812344053071872"
)

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

# Global Resource Pointers
db_pool = None
http_session = None


def calculate_survival_probability(adp: float, next_pick: int) -> int:
    """
    Estimates the probability (0-100%) that a player with given ADP
    will still be on the board at next_pick using a Gaussian error function.
    """
    if not adp or adp <= 0:
        return 50  # Fallback if no ADP data exists

    # Standard deviation scales proportionally with ADP depth
    sigma = max(2.5, adp * 0.12)

    # Cumulative Distribution Function: P(Drafted after next_pick)
    # Z-score relative to the target pick
    z = (next_pick - adp) / (sigma * math.sqrt(2))
    cdf = 0.5 * (1.0 + math.erf(z))

    survival_prob = round((1.0 - cdf) * 100)
    return max(1, min(99, survival_prob))


def build_search_pattern(raw_name: str) -> str:
    """Safely normalizes names by stripping suffixes, punctuation, and team names."""
    if not raw_name or not str(raw_name).strip():
        return ""

    # 1. Strip team abbreviations if in parentheses
    name = str(raw_name).split("(")[0].strip()

    # 2. Remove common suffixes (JR, SR, II, III, IV, V)
    name = re.sub(r"\b(JR|SR|II|III|IV|V)\b", "", name, flags=re.IGNORECASE).strip()

    # Split to check length safely before doing index lookups
    parts = name.split()
    if not parts:
        return ""

    # 3. Detect if first name is just an initial (e.g. "B. Robinson" or "B Robinson")
    is_initial = "." in parts[0] or len(parts[0]) == 1

    # 4. Remove all remaining punctuation
    name = re.sub(r"[^\w\s]", "", name).strip()

    parts = name.split()
    if not parts:
        return ""

    # 5. Drop trailing team abbreviations (e.g. "Bijan Robinson ATL")
    if len(parts) > 1 and len(parts[-1]) in [2, 3] and parts[-1].isupper():
        parts.pop()

    if not parts:
        return ""

    # 6. Build the SQL wildcard search pattern
    if len(parts) >= 2:
        last_name = parts[-1]
        first_name = parts[0]
        return (
            f"{first_name[0]}%{last_name}%"
            if is_initial
            else f"%{first_name}%{last_name}%"
        )

    return f"%{parts[0]}%"


def calculate_player_gems(history: list[dict], favorability_stars: int) -> list[str]:
    """
    Evaluates player performance over the last 4 weeks against expectations.
    - Lunchpail: Hit proj +/- 3 pts in >= 3 of last 4 weeks.
    - Breakout: Outperformed proj by >= +4 pts in >= 3 of last 4 weeks.
    - Underperformer: Underperformed proj by >= -4 pts in >= 3 of last 4 weeks.
    - Sleeper: Steady recently (<= 3.5 delta) AND favorability >= 4 stars this week.
    """
    if len(history) < 2:
        return []

    gems = []
    recent_4 = history[-4:]
    n = len(recent_4)

    lunchpail_count = sum(
        1 for h in recent_4 if abs(h["actual"] - h["projected"]) <= 3.0
    )
    breakout_count = sum(1 for h in recent_4 if (h["actual"] - h["projected"]) >= 4.0)
    underperform_count = sum(
        1 for h in recent_4 if (h["projected"] - h["actual"]) >= 4.0
    )
    steady_count = sum(1 for h in recent_4 if abs(h["actual"] - h["projected"]) <= 3.5)

    if lunchpail_count >= min(3, n):
        gems.append("Lunchpail")
    if breakout_count >= min(3, n):
        gems.append("Breakout")
    if underperform_count >= min(3, n):
        gems.append("Underperformer")
    if steady_count >= min(2, n) and favorability_stars >= 4:
        gems.append("Sleeper")

    return gems


def get_favorability_index(pos: str, opp_team: str, def_ranks: dict) -> tuple[int, str]:
    """Returns a 1-5 star favorability rating based on opponent defensive rank vs position."""
    if not opp_team or opp_team not in def_ranks:
        return 3, "Neutral Matchup (16th vs Pos)"

    pos_key = f"{pos.lower()}_rank"
    rank = def_ranks[opp_team].get(
        pos_key, 16
    )  # 1 = stingiest defense, 32 = easiest matchup

    if rank >= 26:
        return 5, f"Smash Matchup (Opponent ranks #{rank} vs {pos})"
    elif rank >= 19:
        return 4, f"Favorable Matchup (Opponent ranks #{rank} vs {pos})"
    elif rank >= 13:
        return 3, f"Neutral Matchup (Opponent ranks #{rank} vs {pos})"
    elif rank >= 7:
        return 2, f"Tough Matchup (Opponent ranks #{rank} vs {pos})"
    else:
        return 1, f"Brutal Matchup (Opponent ranks #{rank} vs {pos})"


def get_intervening_picks(
    total_teams: int, current_overall_pick: int, user_slot: int
) -> list[int]:
    """
    Calculates the sequence of roster slots picking between current pick and user's next pick in a snake draft.
    """
    intervening_slots = []
    # Search up to 2 rounds ahead
    for pick_num in range(
        current_overall_pick, current_overall_pick + (total_teams * 2)
    ):
        round_num = (pick_num - 1) // total_teams + 1
        pick_in_round = (pick_num - 1) % total_teams + 1

        # Determine 1-indexed slot in snake format
        if round_num % 2 == 1:
            slot = pick_in_round
        else:
            slot = total_teams - pick_in_round + 1

        if pick_num > current_overall_pick and slot == user_slot:
            break  # Reached user's next turn

        if pick_num > current_overall_pick:
            intervening_slots.append(slot)

    return intervening_slots


# --- IN-MEMORY CACHE FOR SLEEPER PROJECTIONS & SCORING ---
SLEEPER_PROJECTIONS_CACHE = {
    "season": 2026,
    "timestamp": 0,
    "ttl_seconds": 86400,  # 24 hours
    "data": {},  # Maps sleeper_id -> projected stats dict
}

LEAGUE_SETTINGS_CACHE = {}  # Maps league_id -> {"timestamp": float, "settings": dict}


async def get_sleeper_raw_projections(season: int = 2026) -> dict:
    """
    Fetches raw season projections from Sleeper with a 24-hour in-memory cache.
    Safely handles both dictionary and list JSON responses.
    """
    global SLEEPER_PROJECTIONS_CACHE
    now = time.time()

    # Return cache if valid
    if SLEEPER_PROJECTIONS_CACHE["data"] and (
        now - SLEEPER_PROJECTIONS_CACHE["timestamp"]
        < SLEEPER_PROJECTIONS_CACHE["ttl_seconds"]
    ):
        return SLEEPER_PROJECTIONS_CACHE["data"]

    url = f"https://api.sleeper.app/v1/projections/nfl/regular/{season}"
    session = await get_session()

    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                raw_data = await resp.json()
                proj_dict = {}

                # Handle dictionary response (e.g., {"4046": {"stats": {...}}})
                if isinstance(raw_data, dict):
                    for p_id, item in raw_data.items():
                        if isinstance(item, dict):
                            # Sleeper sometimes nests data under "stats", sometimes it's flat
                            stats = item.get("stats") if "stats" in item else item
                            proj_dict[str(p_id)] = stats

                # Handle list response just in case the API format shifts
                elif isinstance(raw_data, list):
                    for item in raw_data:
                        if isinstance(item, dict):
                            p_id = str(item.get("player_id") or "")
                            if p_id:
                                stats = item.get("stats") if "stats" in item else item
                                proj_dict[p_id] = stats

                SLEEPER_PROJECTIONS_CACHE["data"] = proj_dict
                SLEEPER_PROJECTIONS_CACHE["timestamp"] = now
                SLEEPER_PROJECTIONS_CACHE["season"] = season
                return proj_dict
    except Exception as e:
        logger.error(f"Failed to fetch Sleeper projections: {e}")

    return SLEEPER_PROJECTIONS_CACHE.get("data", {})


async def get_sleeper_league_scoring(league_id: str) -> dict:
    """Fetches and caches scoring settings for a specific Sleeper league."""
    if not league_id:
        return {}

    global LEAGUE_SETTINGS_CACHE
    now = time.time()
    cached = LEAGUE_SETTINGS_CACHE.get(league_id)
    if cached and (now - cached["timestamp"] < 3600):  # 1 hour cache per league
        return cached["settings"]

    url = f"https://api.sleeper.app/v1/league/{league_id}"
    session = await get_session()
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                league_data = await resp.json()
                settings = league_data.get("scoring_settings") or {}
                LEAGUE_SETTINGS_CACHE[league_id] = {
                    "timestamp": now,
                    "settings": settings,
                }
                return settings
    except Exception as e:
        logger.error(f"Failed to fetch league scoring for {league_id}: {e}")

    return {}


def calculate_custom_league_points(
    stats: dict, scoring_settings: dict, position: str = ""
) -> float:
    """
    Applies custom league scoring multipliers to raw projected stats.
    Handles standard stats, IDP, and position bonuses (e.g. TE Premium).
    """
    if not stats or not scoring_settings:
        return 0.0

    total_pts = 0.0
    pos_upper = (position or "").upper()

    for stat_key, stat_val in stats.items():
        if not stat_val or not isinstance(stat_val, (int, float)):
            continue

        # Standard multiplier lookup
        multiplier = scoring_settings.get(stat_key, 0.0)
        if multiplier:
            total_pts += float(stat_val) * float(multiplier)

    # Apply positional bonuses (e.g. bonus_rec_te for TE Premium)
    if pos_upper == "TE" and "bonus_rec_te" in scoring_settings:
        total_pts += float(stats.get("rec", 0)) * float(
            scoring_settings["bonus_rec_te"]
        )
    elif pos_upper == "RB" and "bonus_rec_rb" in scoring_settings:
        total_pts += float(stats.get("rec", 0)) * float(
            scoring_settings["bonus_rec_rb"]
        )
    elif pos_upper == "WR" and "bonus_rec_wr" in scoring_settings:
        total_pts += float(stats.get("rec", 0)) * float(
            scoring_settings["bonus_rec_wr"]
        )

    return round(total_pts, 2)


# --- LAZY LOADERS: Bulletproof memory management ---
async def get_db():
    global db_pool
    if db_pool is None:
        db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
        db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    return db_pool


async def get_session():
    global http_session
    if http_session is None:
        http_session = aiohttp.ClientSession()
    return http_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    Verifies and creates required PostgreSQL table schemas before accepting requests.
    """
    try:
        pool = await get_db()
        async with pool.acquire() as conn:
            # Create team_unit_rankings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS team_unit_rankings (
                    team_abbr VARCHAR(5) PRIMARY KEY,
                    oline_rank INT CHECK (oline_rank BETWEEN 1 AND 32),
                    qb_rank INT CHECK (qb_rank BETWEEN 1 AND 32),
                    wr_rank INT CHECK (wr_rank BETWEEN 1 AND 32),
                    te_rank INT CHECK (te_rank BETWEEN 1 AND 32),
                    rb_rank INT CHECK (rb_rank BETWEEN 1 AND 32),
                    def_rank INT CHECK (def_rank BETWEEN 1 AND 32),
                    off_rank INT CHECK (off_rank BETWEEN 1 AND 32),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create player_ti table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS player_ti (
                    player_id VARCHAR(50) PRIMARY KEY,
                    player_name VARCHAR(100),
                    position VARCHAR(10),
                    team_abbr VARCHAR(5),
                    age INT,
                    bye_week INT,
                    adp FLOAT,
                    consensus_rank INT,
                    projected_points FLOAT,
                    projected_next_game FLOAT,
                    projected_next_4 FLOAT,
                    historical_avg_points FLOAT,
                    consistency_score FLOAT,
                    team_synergy_multiplier FLOAT,
                    ti_score FLOAT,
                    ti_score_dynasty FLOAT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Safely append new metadata columns to the existing table
            await conn.execute("""
                ALTER TABLE player_ti 
                ADD COLUMN IF NOT EXISTS practice_participation VARCHAR(50),
                ADD COLUMN IF NOT EXISTS depth_chart_position VARCHAR(20),
                ADD COLUMN IF NOT EXISTS status VARCHAR(50),
                ADD COLUMN IF NOT EXISTS depth_chart_order INT,
                ADD COLUMN IF NOT EXISTS years_exp INT,
                ADD COLUMN IF NOT EXISTS fantasy_positions VARCHAR(50),
                ADD COLUMN IF NOT EXISTS practice_description VARCHAR(255),
                ADD COLUMN IF NOT EXISTS injury_body_part VARCHAR(50),
                ADD COLUMN IF NOT EXISTS search_rank INT,
                ADD COLUMN IF NOT EXISTS sleeper_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS espn_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS yahoo_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS sportradar_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS rotowire_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS custom_tags JSONB DEFAULT '[]'::jsonb;
            """)

            # Create board_player_order table for custom drag-and-drop overrides
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS board_player_order (
                    board_type VARCHAR(50) NOT NULL,
                    player_id VARCHAR(50) NOT NULL,
                    manual_rank FLOAT NOT NULL,
                    is_pinned BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (board_type, player_id)
                );
            """)
            await conn.execute("""
                ALTER TABLE player_ti 
                ADD COLUMN IF NOT EXISTS fp_rank INT,
                ADD COLUMN IF NOT EXISTS fp_tier INT,
                ADD COLUMN IF NOT EXISTS fp_upside INT,
                ADD COLUMN IF NOT EXISTS fp_bust INT,
                ADD COLUMN IF NOT EXISTS fp_sos INT,
                ADD COLUMN IF NOT EXISTS fp_ecr_vs_adp INT;
            """)

            # In-Season Weekly Projections & Historical Actuals
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_projections (
                    id SERIAL PRIMARY KEY,
                    season INT NOT NULL,
                    week INT NOT NULL,
                    player_name TEXT NOT NULL,
                    position TEXT,
                    team_abbr TEXT,
                    projected_points NUMERIC(6, 2),
                    pos_rank INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(season, week, player_name, team_abbr)
                );

                CREATE TABLE IF NOT EXISTS weekly_actuals (
                    id SERIAL PRIMARY KEY,
                    season INT NOT NULL,
                    week INT NOT NULL,
                    sleeper_id TEXT NOT NULL,
                    actual_points NUMERIC(6, 2),
                    projected_points NUMERIC(6, 2),
                    UNIQUE(season, week, sleeper_id)
                );

                CREATE TABLE IF NOT EXISTS opponent_defense_rank (
                    team_abbr TEXT PRIMARY KEY,
                    qb_rank INT DEFAULT 16,
                    rb_rank INT DEFAULT 16,
                    wr_rank INT DEFAULT 16,
                    te_rank INT DEFAULT 16
                );
            """)

        logger.info("Database schemas verified successfully via lifespan startup.")
    except (asyncpg.PostgresError, OSError) as e:
        logger.error(f"Failed to initialize database schemas during startup: {e}")

    # Initialize session on startup
    await get_session()

    yield

    # Shutdown logic
    global http_session, db_pool
    if http_session:
        await http_session.close()
    if db_pool:
        await db_pool.close()


# Initialize FastAPI app using the lifespan context manager
app = FastAPI(title="Sleeper Fantasy Football API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "up"}


@app.get("/api/sleeper/familydynasty")
async def get_sleeper_matchups():
    url_league = f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}"
    session = await get_session()

    try:
        async with session.get(url_league) as resp:
            if resp.status != 200:
                return {"mode": "disabled"}
            league_data = await resp.json()

        if league_data.get("status") == "pre_draft":
            url_drafts = (
                f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/drafts"
            )
            async with session.get(url_drafts) as d_resp:
                drafts = await d_resp.json()
                if drafts:
                    return {
                        "mode": "draft",
                        "name": league_data.get("name"),
                        "draft_start": drafts[0].get("start_time"),
                    }

        current_week = league_data.get("settings", {}).get("leg", 1)

        async with session.get(
            f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/users"
        ) as u_resp:
            users = await u_resp.json()
            user_map = {
                u["user_id"]: u.get("metadata", {}).get("team_name", u["display_name"])
                for u in users
            }

        async with session.get(
            f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/rosters"
        ) as r_resp:
            rosters = await r_resp.json()
            roster_to_owner = {
                r["roster_id"]: user_map.get(r["owner_id"], f"Team {r['roster_id']}")
                for r in rosters
            }

        async with session.get(
            f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/matchups/{current_week}"
        ) as m_resp:
            matchups_raw = await m_resp.json()

        match_groups = {}
        for team in matchups_raw:
            m_id = team.get("matchup_id")
            if m_id not in match_groups:
                match_groups[m_id] = []

            match_groups[m_id].append(
                {
                    "owner_name": roster_to_owner.get(team["roster_id"], "Unknown"),
                    "points": team.get("points", 0.0),
                    "projected_points": sum(team.get("starters_points", [0])),
                    "starters": team.get("starters", []),
                    "players": team.get("players", []),
                    "custom_roster_points_map": team.get("players_points", {}),
                }
            )

        return {
            "mode": "matchups",
            "week": current_week,
            "matchups": list(match_groups.values()),
        }

    except aiohttp.ClientError as e:
        logger.error(f"Sleeper API fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Upstream Sleeper API error")


@app.post("/api/rankings/team-units")
async def update_team_unit_rankings(rankings: dict):
    """
    Receives team unit rankings (1-32) from React UI and stores in DB.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        query = """
            INSERT INTO team_unit_rankings 
            (team_abbr, oline_rank, qb_rank, wr_rank, te_rank, rb_rank, def_rank, off_rank)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (team_abbr) DO UPDATE SET
                oline_rank = EXCLUDED.oline_rank,
                qb_rank = EXCLUDED.qb_rank,
                wr_rank = EXCLUDED.wr_rank,
                te_rank = EXCLUDED.te_rank,
                rb_rank = EXCLUDED.rb_rank,
                def_rank = EXCLUDED.def_rank,
                off_rank = EXCLUDED.off_rank,
                updated_at = CURRENT_TIMESTAMP;
        """
        for team, ranks in rankings.items():
            await conn.execute(
                query,
                team,
                ranks.get("oline_rank"),
                ranks.get("qb_rank"),
                ranks.get("wr_rank"),
                ranks.get("te_rank"),
                ranks.get("rb_rank"),
                ranks.get("def_rank"),
                ranks.get("off_rank"),
            )
        return {"status": "success", "updated_teams": list(rankings.keys())}


@app.get("/api/rankings/team-units")
async def get_team_unit_rankings():
    """
    Fetches all stored 1-32 team unit rankings from PostgreSQL.
    Returns a dictionary keyed by team abbreviation.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM team_unit_rankings")
        rankings = {}
        for r in rows:
            rankings[r["team_abbr"]] = {
                "oline_rank": r["oline_rank"],
                "qb_rank": r["qb_rank"],
                "wr_rank": r["wr_rank"],
                "te_rank": r["te_rank"],
                "rb_rank": r["rb_rank"],
                "def_rank": r["def_rank"],
                "off_rank": r["off_rank"],
            }
        return {"rankings": rankings}


@app.get("/api/ti/master-board")
async def get_master_draft_board():
    """
    Pulls player projections, historical metrics, and team unit ranks,
    calculates live TI scores, and returns sorted master draft board.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        # Fetch team unit rankings
        team_rows = await conn.fetch("SELECT * FROM team_unit_rankings")
        team_ranks_map = {r["team_abbr"]: dict(r) for r in team_rows}

        # Fetch player metrics
        player_rows = await conn.fetch("SELECT * FROM player_ti")

        draft_board = []
        for p in player_rows:
            player_team = p.get("team_abbr")
            unit_ranks = team_ranks_map.get(player_team, {})

            # Run TI Calculation
            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                age=p.get("age"),
            )

            draft_board.append(
                {
                    "player_id": p["player_id"],
                    "player_name": p["player_name"],
                    "position": p["position"],
                    "team": player_team,
                    "ti": score_data["ti_score"],
                    "details": score_data,
                }
            )

        # Sort draft board descending by TI
        draft_board.sort(key=lambda x: x["ti"], reverse=True)
        return {"count": len(draft_board), "draft_board": draft_board}


@app.get("/api/sleeper/leagues")
async def get_user_leagues():
    """
    Fetches the user_id using SLEEPER_USERNAME, then retrieves all active leagues for the season.
    """
    url_user = f"https://api.sleeper.app/v1/user/{SLEEPER_USERNAME}"
    session = await get_session()

    try:
        # 1. Get User ID from Username
        async with session.get(url_user) as resp_user:
            if resp_user.status != 200:
                raise HTTPException(status_code=404, detail="Sleeper user not found")
            user_data = await resp_user.json()
            user_id = user_data.get("user_id")

        # 2. Get all leagues for that user ID and season
        url_leagues = (
            f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{SLEEPER_SEASON}"
        )
        async with session.get(url_leagues) as resp_leagues:
            if resp_leagues.status != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch leagues")
            leagues_data = await resp_leagues.json()

        # 3. Format the response for your React frontend dropdown
        active_leagues = []
        for league in leagues_data:
            active_leagues.append(
                {
                    "league_id": league.get("league_id"),
                    "name": league.get("name"),
                    "status": league.get("status"),
                    "total_rosters": league.get("total_rosters"),
                }
            )

        return {
            "username": SLEEPER_USERNAME,
            "season": SLEEPER_SEASON,
            "leagues": active_leagues,
        }

    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        logger.error(f"Failed to fetch user leagues: {e}")
        raise HTTPException(status_code=500, detail="Internal API error")


@app.get("/api/sleeper/leagues/{user_identifier}")
async def get_sleeper_leagues(user_identifier: str, year: str = "2026"):
    """
    Fetches all NFL leagues for a Sleeper user.
    Automatically resolves text usernames to numeric user_ids.
    """
    session = await get_session()

    # Step 1: Resolve the numeric user_id if a username is passed
    if not user_identifier.isdigit():
        user_url = f"https://api.sleeper.app/v1/user/{user_identifier}"
        async with session.get(user_url) as user_resp:
            if user_resp.status == 200:
                user_data = await user_resp.json()
                user_identifier = user_data.get("user_id", user_identifier)
            else:
                return []  # Username not found

    # Step 2: Fetch the leagues using the numeric user_id
    leagues_url = (
        f"https://api.sleeper.app/v1/user/{user_identifier}/leagues/nfl/{year}"
    )
    async with session.get(leagues_url) as leagues_resp:
        if leagues_resp.status == 200:
            return await leagues_resp.json()
        return []


@app.get("/api/sleeper/league/{league_id}/drafts")
async def get_sleeper_drafts(league_id: str):
    """
    Fetches all drafts associated with a specific Sleeper league.
    """
    url = f"https://api.sleeper.app/v1/league/{league_id}/drafts"
    session = await get_session()
    async with session.get(url) as resp:
        if resp.status == 200:
            return await resp.json()
        return []


class ReorderRequest(BaseModel):
    player_id: str
    target_above_player_id: str | None = None
    target_below_player_id: str | None = None


class ReorderPayload(BaseModel):
    player_id: str
    target_above_player_id: Optional[str] = None
    target_below_player_id: Optional[str] = None


async def fetch_team_unit_ranks(conn) -> dict:
    """
    Fetches all 1-32 team unit rankings from PostgreSQL.
    Returns a dictionary keyed by team abbreviation.
    """
    try:
        rows = await conn.fetch("SELECT * FROM team_unit_rankings")
        rankings = {}
        for r in rows:
            rankings[r["team_abbr"]] = {
                "oline_rank": r.get("oline_rank", 16),
                "qb_rank": r.get("qb_rank", 16),
                "wr_rank": r.get("wr_rank", 16),
                "te_rank": r.get("te_rank", 16),
                "rb_rank": r.get("rb_rank", 16),
                "def_rank": r.get("def_rank", 16),
                "off_rank": r.get("off_rank", 16),
            }
        return rankings
    except asyncpg.PostgresError as e:
        logger.warning(f"Could not load team unit rankings: {e}")
        return {}


@app.get("/api/ti/board/{board_type}")
async def get_draft_board(board_type: str):
    """
    Fetches the draft board, reading persisted drag-and-drop ranks
    from `board_player_order`.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        unit_ranks = await fetch_team_unit_ranks(conn)

        # 1. Fetch players joined with board_player_order
        query = """
            SELECT 
                p.*,
                b.manual_rank,
                COALESCE(b.is_pinned, FALSE) as is_pinned
            FROM player_ti p
            LEFT JOIN board_player_order b 
                ON p.player_id = b.player_id AND b.board_type = $1
            WHERE p.team_abbr IS NOT NULL 
              AND p.team_abbr NOT IN ('FA', 'UNK', 'None', '')
              AND (p.status IS NULL OR LOWER(p.status) NOT IN ('inactive', 'retired', 'cut'))
            ORDER BY b.manual_rank ASC NULLS LAST, p.projected_points DESC NULLS LAST
        """
        rows = await conn.fetch(query, board_type)

        draft_board = []
        for p in rows:
            p_id = p["player_id"]

            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                years_exp=p.get("years_exp"),
                age=p.get("age"),
                depth_chart_order=p.get("depth_chart_order"),
            )

            c_score = p.get("consistency_score")
            cons_data = format_consistency_score(c_score)
            raw_tags = p.get("custom_tags")
            parsed_tags = (
                json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
            )
            # Select target score based on board mode
            target_score = (
                score_data["ti_score_dynasty"]
                if board_type == "dynasty"
                else score_data["ti_score"]
            )
            pos_str = (p.get("position") or "WR").upper()
            tier_val = p.get("fp_tier")
            pos_tier_label = f"{pos_str} - T{tier_val}" if tier_val else None

            draft_board.append(
                {
                    "player_id": p_id,
                    "player_name": p["player_name"],
                    "position": pos_str,
                    "team": p["team_abbr"],
                    "age": p.get("age"),
                    "bye_week": p.get("bye_week"),
                    "depth_chart_position": p.get("depth_chart_position"),
                    "depth_chart_order": p.get("depth_chart_order"),
                    "is_pinned": p["is_pinned"],
                    "manual_rank": p["manual_rank"],
                    "pos_tier": pos_tier_label,
                    "fp_rank": p.get("fp_rank"),
                    "fp_tier": tier_val,
                    "fp_upside": p.get("fp_upside"),
                    "fp_bust": p.get("fp_bust"),
                    "fp_sos": p.get("fp_sos"),
                    "fp_ecr_vs_adp": p.get("fp_ecr_vs_adp"),
                    "ti_score": score_data["ti_score"],
                    "ti_score_dynasty": score_data["ti_score_dynasty"],
                    "consistency_score": cons_data["rating"],
                    "consistency_label": cons_data["label"],
                    "target_score": target_score,
                    "projected_points": p.get("projected_points") or 0.0,
                    "projected_next_game": p.get("projected_next_game") or 0.0,
                    "projected_next_4": p.get("projected_next_4") or 0.0,
                    "custom_tags": parsed_tags,
                    "details": score_data,
                }
            )

        # 2. Sort: Manual ranks take absolute priority (1.0, 2.0, 3.0...), unranked players fall back to target_score
        def board_sort_key(x):
            has_manual = x["manual_rank"] is not None
            # False (has manual rank) sorts before True (no manual rank)
            return (
                not has_manual,
                x["manual_rank"] if has_manual else -x["target_score"],
            )

        draft_board.sort(key=board_sort_key)

        return {"board_type": board_type, "draft_board": draft_board}


@app.post("/api/ti/board/{board_type}/reorder")
async def reorder_board_player(board_type: str, payload: ReorderPayload):
    """
    Saves new manual ranks to `board_player_order` upon drag-and-drop.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        # Fetch current player order for this board
        query = """
            SELECT 
                p.player_id,
                b.manual_rank,
                p.projected_points
            FROM player_ti p
            LEFT JOIN board_player_order b 
                ON p.player_id = b.player_id AND b.board_type = $1
            WHERE p.team_abbr IS NOT NULL 
              AND p.team_abbr NOT IN ('FA', 'UNK', 'None', '')
              AND (p.status IS NULL OR LOWER(p.status) NOT IN ('inactive', 'retired', 'cut'))
            ORDER BY b.manual_rank ASC NULLS LAST, p.projected_points DESC NULLS LAST
        """
        rows = await conn.fetch(query, board_type)

        # Exclude the dragged player to compute insertion point
        current_pids = [
            r["player_id"] for r in rows if r["player_id"] != payload.player_id
        ]

        # Calculate new insertion index
        insert_idx = len(current_pids)
        if (
            payload.target_above_player_id
            and payload.target_above_player_id in current_pids
        ):
            above_idx = current_pids.index(payload.target_above_player_id)
            insert_idx = above_idx + 1
        elif (
            payload.target_below_player_id
            and payload.target_below_player_id in current_pids
        ):
            below_idx = current_pids.index(payload.target_below_player_id)
            insert_idx = below_idx
        elif not payload.target_above_player_id:
            insert_idx = 0

        # Insert at new position
        current_pids.insert(insert_idx, payload.player_id)

        # Upsert sequential ranks (1.0, 2.0, 3.0...) into board_player_order
        upsert_sql = """
            INSERT INTO board_player_order (board_type, player_id, manual_rank, is_pinned, updated_at)
            VALUES ($1, $2, $3, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (board_type, player_id)
            DO UPDATE SET 
                manual_rank = EXCLUDED.manual_rank,
                is_pinned = TRUE,
                updated_at = CURRENT_TIMESTAMP;
        """

        async with conn.transaction():
            for idx, pid in enumerate(current_pids):
                await conn.execute(upsert_sql, board_type, pid, float(idx + 1))

        return {
            "status": "success",
            "board_type": board_type,
            "player_id": payload.player_id,
            "new_manual_rank": float(insert_idx + 1),
        }


@app.post("/api/ti/board/{board_type}/reset")
async def reset_board_order(board_type: str):
    """
    Clears all manual overrides for a specific board type, reverting back to pure TI calculations.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM board_player_order WHERE board_type = $1", board_type
        )
        return {
            "status": "success",
            "message": f"Board {board_type} reset to default TI order.",
        }


@app.post("/api/projections/upload")
async def upload_projections_csv(file: UploadFile = File(...)):
    """Accepts a CSV file, parses Player, FPTS, and Team to update projections."""
    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
        df.columns = [str(c).upper().strip() for c in df.columns]

        pool = await get_db()
        async with pool.acquire() as conn:
            updated_count = 0

            # Requires BOTH a name match and a team match (if team is provided)
            update_query = """
                UPDATE player_ti 
                SET projected_points = $1, updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(player_name) LIKE LOWER($2)
                AND ($3 = '' OR team_abbr = $3);
            """

            for _, row in df.iterrows():
                player_col = next((col for col in df.columns if "PLAYER" in col), None)
                fpts_col = next(
                    (col for col in df.columns if "FPTS" in col or "POINTS" in col),
                    None,
                )

                if (
                    not player_col
                    or not fpts_col
                    or pd.isna(row[player_col])
                    or pd.isna(row[fpts_col])
                ):
                    continue

                raw_name = str(row[player_col]).strip()
                search_pattern = build_search_pattern(raw_name)
                if not search_pattern:
                    continue

                # Attempt to extract team for safe matching
                team = ""
                team_col = next((c for c in df.columns if c == "TEAM"), None)
                if team_col and pd.notna(row[team_col]):
                    team = str(row[team_col]).upper().strip()
                else:
                    m = re.search(r"\(([A-Z]{2,3})\)", raw_name)
                    if m:
                        team = m.group(1)
                    else:
                        parts = raw_name.split()
                        if (
                            len(parts) > 1
                            and len(parts[-1]) in [2, 3]
                            and parts[-1].isupper()
                        ):
                            team = parts[-1]

                # Standardize common alternative abbreviations
                if team == "JAC":
                    team = "JAX"
                if team == "WSH":
                    team = "WAS"

                try:
                    proj_pts = float(row[fpts_col])
                    if pd.isna(proj_pts):
                        continue

                    proj_ppg = round(proj_pts / 17.0, 2)
                    result = await conn.execute(
                        update_query, proj_ppg, search_pattern, team
                    )

                    if result.startswith("UPDATE"):
                        updated_count += int(result.split(" ")[1])

                except ValueError:
                    continue

            return {"status": "success", "updated": updated_count}

    except Exception as e:
        logger.error(f"Projections Upload failed: {e}")
        return {"status": "error", "message": str(e)}

    except (
        asyncpg.PostgresError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        UnicodeDecodeError,
        OSError,
        ValueError,
    ) as e:
        logger.error(f"CSV Upload failed: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/sleeper/draft/{draft_id}/state")
async def get_draft_state(draft_id: str, user_id: str = None, roster_id: str = None):
    draft_url = f"https://api.sleeper.app/v1/draft/{draft_id}"
    picks_url = f"https://api.sleeper.app/v1/draft/{draft_id}/picks"
    session = await get_session()

    if user_id and not user_id.isdigit():
        user_url = f"https://api.sleeper.app/v1/user/{user_id}"
        async with session.get(user_url) as user_resp:
            if user_resp.status == 200:
                user_data = await user_resp.json()
                user_id = user_data.get("user_id", user_id)

    async with session.get(draft_url) as draft_resp:
        draft_meta = await draft_resp.json() if draft_resp.status == 200 else {}

    async with session.get(picks_url) as picks_resp:
        picks = await picks_resp.json() if picks_resp.status == 200 else []

    user_id_str = str(user_id) if user_id is not None else None
    user_roster_id_str = str(roster_id).strip() if roster_id else None

    draft_order = draft_meta.get("draft_order") or {}
    user_slot = draft_order.get(user_id_str, 1) if user_id_str else 1
    total_teams = draft_meta.get("settings", {}).get("teams") or max(
        len(draft_order), 12
    )

    if not user_roster_id_str and user_id_str and draft_meta:
        d_slot = draft_order.get(user_id_str)
        if d_slot:
            slot_to_roster = draft_meta.get("slot_to_roster_id") or {}
            user_roster_id_str = str(slot_to_roster.get(str(d_slot), d_slot))

    drafted_player_ids = []
    my_roster = {"QB": [], "RB": [], "WR": [], "TE": [], "DEF": [], "K": [], "ALL": []}
    team_rosters = {}
    amount_spent = 0

    for pick in picks:
        pid = str(pick.get("player_id") or "")
        if not pid:
            continue

        drafted_player_ids.append(pid)
        metadata = pick.get("metadata") or {}
        pick_owner_user = str(pick.get("picked_by") or "")
        pick_roster_id = str(
            pick.get("roster_id")
            or metadata.get("roster_id")
            or metadata.get("team_id")
            or ""
        )

        pos = metadata.get("position", "ALL").upper()
        if pick_roster_id:
            if pick_roster_id not in team_rosters:
                team_rosters[pick_roster_id] = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
            if pos in team_rosters[pick_roster_id]:
                team_rosters[pick_roster_id][pos] += 1

        is_my_pick = False
        if user_roster_id_str and pick_roster_id == user_roster_id_str:
            is_my_pick = True
        elif user_id_str and user_id_str.isdigit() and pick_owner_user == user_id_str:
            is_my_pick = True

        if is_my_pick:
            amount_val = metadata.get("amount") or pick.get("amount") or 0
            my_roster["ALL"].append(pid)
            if pos in my_roster:
                my_roster[pos].append(pid)

            try:
                amount_spent += int(amount_val)
            except (ValueError, TypeError):
                pass

    total_budget = draft_meta.get("settings", {}).get("budget") or 200
    current_pick_no = len(drafted_player_ids) + 1

    slot_to_roster = draft_meta.get("slot_to_roster_id") or {}

    return {
        "draft_id": draft_id,
        "status": draft_meta.get("status"),
        "draft_type": draft_meta.get("type", "snake"),
        "total_teams": total_teams,
        "user_slot": user_slot,
        "current_pick_no": current_pick_no,
        "budget": total_budget,
        "total_roster_spots": draft_meta.get("settings", {}).get("roster_size", 16),
        "drafted_player_ids": drafted_player_ids,
        "team_rosters": team_rosters,
        "my_roster": my_roster,
        "amount_spent": amount_spent,
        "remaining_budget": max(0, total_budget - amount_spent),
    }


def check_bye_constraint(pos: str, player_bye: int, my_roster_byes: dict) -> dict:
    if not player_bye:
        return {"blocked": False, "status": "CLEAR", "message": None}

    pos = pos.upper()
    current_byes = my_roster_byes.get(pos, [])

    if pos in ["QB", "TE"]:
        if player_bye in current_byes:
            return {
                "blocked": True,
                "status": "BLOCKED",
                "message": f"{pos} bye overlap (Wk {player_bye})",
            }
    elif pos in ["RB", "WR"]:
        count = current_byes.count(player_bye)
        if count >= 2:
            return {
                "blocked": True,
                "status": "BLOCKED",
                "message": f"Max (2) {pos} bye overlap (Wk {player_bye})",
            }
        elif count == 1:
            return {
                "blocked": False,
                "status": "WARNING",
                "message": f"Warning: 1 {pos} shares Wk {player_bye} bye",
            }

    return {"blocked": False, "status": "CLEAR", "message": None}


def format_consistency_score(cv: float) -> dict:
    if cv is None:
        cv = 0.40
    rating = int(max(0.0, min(100.0, ((0.75 - cv) / 0.55) * 100.0)))

    if rating >= 80:
        label = f"{rating} (Rock Solid)"
    elif rating >= 60:
        label = f"{rating} (Dependable)"
    elif rating >= 40:
        label = f"{rating} (Moderate)"
    else:
        label = f"{rating} (Boom / Bust)"

    return {"rating": rating, "label": label}


def calculate_roster_need_multiplier(pos: str, drafted_count: int) -> float:
    pos = pos.upper()
    if pos in ("QB", "TE"):
        if drafted_count == 1:
            return 0.30
        if drafted_count >= 2:
            return 0.05
    elif pos == "RB":
        if drafted_count == 2:
            return 0.85
        if drafted_count == 3:
            return 0.65
        if drafted_count >= 4:
            return 0.40
    elif pos == "WR":
        if drafted_count == 3:
            return 0.90
        if drafted_count == 4:
            return 0.75
        if drafted_count >= 5:
            return 0.50
    return 1.00


@app.get("/api/draft/recommendations")
async def get_live_recommendations(
    draft_id: str,
    user_id: str,
    format: str = "snake",
    roster_id: str = None,
    league_id: str = None,  # <-- Added league_id
):
    draft_state = await get_draft_state(draft_id, user_id, roster_id)
    drafted_set = {str(pid) for pid in draft_state["drafted_player_ids"]}
    my_roster_pids = [str(pid) for pid in draft_state["my_roster"]["ALL"]]

    # Fetch custom scoring settings and raw projections (cached)
    league_scoring = await get_sleeper_league_scoring(league_id) if league_id else {}
    raw_sleeper_projs = (
        await get_sleeper_raw_projections(2026) if league_scoring else {}
    )

    pool = await get_db()
    async with pool.acquire() as conn:
        unit_ranks = await fetch_team_unit_ranks(conn)

        # 1. Fetch user roster's bye weeks
        my_roster_byes = {"QB": [], "RB": [], "WR": [], "TE": [], "DEF": [], "K": []}
        my_roster_counts = {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "DEF": 0, "K": 0}

        if my_roster_pids:
            placeholders = ",".join(f"'{pid}'" for pid in my_roster_pids)
            roster_query = f"SELECT position, bye_week FROM player_ti WHERE sleeper_id::text IN ({placeholders})"
            my_roster_data = await conn.fetch(roster_query)

            for r in my_roster_data:
                pos_str = r["position"].upper() if r["position"] else "WR"
                if pos_str in my_roster_byes and r["bye_week"]:
                    my_roster_byes[pos_str].append(r["bye_week"])
                if pos_str in my_roster_counts:
                    my_roster_counts[pos_str] += 1

        # 2. Fetch active available players
        query = """
            SELECT * FROM player_ti
            WHERE team_abbr IS NOT NULL 
              AND team_abbr NOT IN ('FA', 'UNK', 'None', '')
              AND (status IS NULL OR LOWER(status) NOT IN ('inactive', 'retired', 'cut'))
        """
        all_players = await conn.fetch(query)

        available_players = []
        positional_scores = {"QB": [], "RB": [], "WR": [], "TE": []}

        # First Pass: Compute raw TI scores and baselines
        raw_player_data = []
        for p in all_players:
            s_id = str(p.get("sleeper_id") or "")
            if s_id in drafted_set:
                continue

            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                years_exp=p.get("years_exp"),
                age=p.get("age"),
                depth_chart_order=p.get("depth_chart_order"),
            )

            bye_check = check_bye_constraint(
                p.get("position", "WR"), p.get("bye_week"), my_roster_byes
            )
            pos = p.get("position", "WR").upper()

            raw_player_data.append(
                {
                    "db_record": p,
                    "sleeper_id": s_id,
                    "score_data": score_data,
                    "bye_check": bye_check,
                    "pos": pos,
                }
            )

            if pos in positional_scores and not bye_check["blocked"]:
                positional_scores[pos].append(score_data["ti_score"])

        # 3. Positional Replacement Baselines (VORP)
        replacement_cutoffs = {"QB": 12, "RB": 24, "WR": 30, "TE": 12}
        baselines = {}
        for pos, scores in positional_scores.items():
            scores.sort(reverse=True)
            cutoff_idx = replacement_cutoffs.get(pos, 12) - 1
            baselines[pos] = (
                scores[cutoff_idx]
                if len(scores) > cutoff_idx
                else (scores[-1] if scores else 10.0)
            )

        # 4. Compute Intervening Opponents and Turn Distance
        total_teams = draft_state.get("total_teams", 12)
        curr_pick = draft_state.get("current_pick_no", 1)
        user_slot = draft_state.get("user_slot", 1)
        intervening_slots = get_intervening_picks(total_teams, curr_pick, user_slot)
        picks_until_turn = len(intervening_slots)
        next_user_pick_no = curr_pick + picks_until_turn + 1

        team_rosters = draft_state.get("team_rosters", {})
        slot_to_roster = draft_state.get("slot_to_roster_id", {})
        intervening_needs = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
        for slot in intervening_slots:
            roster_id_key = str(slot_to_roster.get(str(slot), slot))
            roster = team_rosters.get(roster_id_key, {})
            if roster.get("QB", 0) < 1:
                intervening_needs["QB"] += 1
            if roster.get("RB", 0) < 2:
                intervening_needs["RB"] += 1
            if roster.get("WR", 0) < 3:
                intervening_needs["WR"] += 1
            if roster.get("TE", 0) < 1:
                intervening_needs["TE"] += 1

        # 5. Compute Tier Counts
        tier_counts = {}
        for item in raw_player_data:
            p = item["db_record"]
            pos = item["pos"]
            tier_val = p.get("fp_tier")
            if tier_val:
                key = f"{pos}_T{tier_val}"
                tier_counts[key] = tier_counts.get(key, 0) + 1

        # Second Pass: Attach Custom League Projections & Attributes
        for item in raw_player_data:
            p = item["db_record"]
            s_id = item["sleeper_id"]
            pos = item["pos"]
            score_data = item["score_data"]
            bye_check = item["bye_check"]

            roster_count = my_roster_counts.get(pos, 0)
            need_mult = calculate_roster_need_multiplier(pos, roster_count)

            raw_ti = score_data["ti_score"]
            base = baselines.get(pos, 10.0)
            raw_vorp = raw_ti - base

            final_ti = round(raw_ti * need_mult, 2)
            final_vorp = round(raw_vorp * need_mult, 2)

            c_score = p.get("consistency_score")
            cons_data = format_consistency_score(c_score)

            raw_tags = p.get("custom_tags")
            player_tags = (
                json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
            )

            tier_val = p.get("fp_tier")
            pos_tier_label = f"{pos} - T{tier_val}" if tier_val else None
            tier_remaining = (
                tier_counts.get(f"{pos}_T{tier_val}", 0) if tier_val else None
            )

            scarcity_alert = None
            if tier_val and tier_remaining is not None:
                if tier_remaining == 1:
                    scarcity_alert = f"LAST in {pos_tier_label}!"
                elif tier_remaining == 2:
                    scarcity_alert = f"Only 2 left in {pos_tier_label}"

            adp_val = p.get("adp") or p.get("fp_rank") or (curr_pick + 10)
            survival_odds = calculate_survival_probability(adp_val, next_user_pick_no)

            # Calculate Custom League Projection
            league_proj_ppg = None
            league_proj_total = None
            if league_scoring and s_id in raw_sleeper_projs:
                p_stats = raw_sleeper_projs[s_id]
                league_proj_total = calculate_custom_league_points(
                    p_stats, league_scoring, pos
                )
                league_proj_ppg = round(league_proj_total / 17.0, 2)

            available_players.append(
                {
                    "player_id": p["player_id"],
                    "sleeper_id": s_id,
                    "player_name": p["player_name"],
                    "position": pos,
                    "team": p["team_abbr"],
                    "age": p.get("age"),
                    "bye_week": p.get("bye_week"),
                    "depth_chart_position": p.get("depth_chart_position"),
                    "depth_chart_order": p.get("depth_chart_order"),
                    "pos_tier": pos_tier_label,
                    "tier_remaining": tier_remaining,
                    "scarcity_alert": scarcity_alert,
                    "survival_odds": survival_odds,
                    "league_proj_ppg": league_proj_ppg,
                    "league_proj_total": league_proj_total,
                    "fp_rank": p.get("fp_rank"),
                    "fp_tier": tier_val,
                    "fp_upside": p.get("fp_upside"),
                    "fp_bust": p.get("fp_bust"),
                    "fp_sos": p.get("fp_sos"),
                    "fp_ecr_vs_adp": p.get("fp_ecr_vs_adp"),
                    "ti_score": final_ti,
                    "ti_score_dynasty": score_data["ti_score_dynasty"],
                    "consistency_score": cons_data["rating"],
                    "consistency_label": cons_data["label"],
                    "projected_points": p.get("projected_points") or 0.0,
                    "is_starter": score_data["is_starter"],
                    "bye_status": bye_check["status"],
                    "bye_message": bye_check["message"],
                    "vorp_score": final_vorp,
                    "roster_need_mult": need_mult,
                    "custom_tags": player_tags,
                    "auction_max_bid": 0,
                }
            )

        # 6. Auction Calculation (if applicable)
        if format.lower() == "auction":
            total_budget = draft_state.get("budget", 200) or 200
            rem_budget = draft_state["remaining_budget"]
            open_spots = max(1, draft_state["total_roster_spots"] - len(my_roster_pids))
            absolute_max_bid = max(1, rem_budget - (open_spots - 1))

            pos_config = {
                "QB": {"alloc": 0.15, "starters": 1},
                "RB": {"alloc": 0.35, "starters": 2},
                "WR": {"alloc": 0.35, "starters": 3},
                "TE": {"alloc": 0.10, "starters": 1},
            }

            starter_ti_avg = {}
            for pos, cfg in pos_config.items():
                scores = sorted(positional_scores.get(pos, []), reverse=True)
                top_n = max(1, cfg["starters"] * 10)
                top_scores = scores[:top_n]
                starter_ti_avg[pos] = (
                    (sum(top_scores) / len(top_scores)) if top_scores else 12.0
                )

            for player in available_players:
                pos = player["position"]
                if pos not in pos_config or player["bye_status"] == "BLOCKED":
                    player["auction_max_bid"] = 1
                    continue

                cfg = pos_config[pos]
                avg_starter_ti = starter_ti_avg.get(pos, 12.0)
                avg_slot_cost = (cfg["alloc"] * total_budget) / cfg["starters"]
                ti_ratio = (
                    player["ti_score"] / avg_starter_ti if avg_starter_ti > 0 else 1.0
                )
                budget_scale = rem_budget / total_budget if total_budget > 0 else 1.0
                bid_calc = ti_ratio * avg_slot_cost * budget_scale
                recommended_bid = round(bid_calc)

                player["auction_max_bid"] = (
                    min(recommended_bid, absolute_max_bid) if recommended_bid > 0 else 1
                )

        # 7. Sort by Adjusted VORP
        def sort_key(x):
            status_weight = 2
            if x["bye_status"] == "BLOCKED":
                status_weight = 0
            elif x["bye_status"] == "WARNING":
                status_weight = 1
            return (status_weight, x["vorp_score"])

        available_players.sort(key=sort_key, reverse=True)

        return {
            "draft_state": draft_state,
            "draft_intel": {
                "picks_until_turn": picks_until_turn,
                "next_user_pick_no": next_user_pick_no,
                "intervening_teams_count": len(intervening_slots),
                "intervening_needs": intervening_needs,
            },
            "my_roster_byes": my_roster_byes,
            "my_roster_counts": my_roster_counts,
            "baselines": baselines,
            "board": available_players,
        }


@app.post("/api/handcuffs/upload")
async def upload_handcuffs_csv(file: UploadFile = HANDCUFF_CSV_FILE):
    """Ingests FantasyPros Handcuff rankings CSV to update depth chart orders."""
    content = await file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    df.columns = [str(c).upper().strip() for c in df.columns]

    pool = await get_db()
    async with pool.acquire() as conn:
        updated = 0
        for _, row in df.iterrows():
            starter_col = next(
                (c for c in df.columns if "STARTER" in c or "PLAYER" in c), None
            )
            handcuff_col = next((c for c in df.columns if "HANDCUFF" in c), None)

            if starter_col and pd.notna(row[starter_col]):
                s_name = str(row[starter_col]).split("(")[0].strip()
                await conn.execute(
                    "UPDATE player_ti SET depth_chart_order = 1 WHERE LOWER(player_name) LIKE LOWER($1) AND position = 'RB'",
                    f"%{s_name}%",
                )
                updated += 1

            if handcuff_col and pd.notna(row[handcuff_col]):
                h_name = str(row[handcuff_col]).split("(")[0].strip()
                await conn.execute(
                    "UPDATE player_ti SET depth_chart_order = 2 WHERE LOWER(player_name) LIKE LOWER($1) AND position = 'RB'",
                    f"%{h_name}%",
                )
                updated += 1

        return {"status": "success", "updated": updated}


class TagPayload(BaseModel):
    tags: list[str]


@app.post("/api/ti/player/{player_id}/tags")
async def update_player_tags(player_id: str, payload: TagPayload):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE player_ti
            SET custom_tags = $1::jsonb
            WHERE player_id = $2
        """,
            json.dumps(payload.tags),
            player_id,
        )
        return {"status": "success", "player_id": player_id, "tags": payload.tags}


@app.post("/api/admin/sync-sleeper")
async def sync_sleeper_master_data():
    """
    Seeds/Updates the database with Sleeper's master NFL player list.
    Solves missing rookies and team changes prior to projection uploads.
    Applies the official 2026 NFL Bye Week Schedule.
    """
    session = await get_session()
    async with session.get("https://api.sleeper.app/v1/players/nfl") as resp:
        players_data = await resp.json()

    # Official 2026 NFL Bye Week Schedule
    bye_map = {
        "CAR": 5,
        "KC": 5,
        "CIN": 6,
        "DET": 6,
        "MIA": 6,
        "MIN": 6,
        "BUF": 7,
        "JAX": 7,
        "LAC": 7,
        "WAS": 7,
        "HOU": 8,
        "NO": 8,
        "NYG": 8,
        "SF": 8,
        "PIT": 9,
        "TEN": 9,
        "CHI": 10,
        "DEN": 10,
        "PHI": 10,
        "TB": 10,
        "ATL": 11,
        "CLE": 11,
        "GB": 11,
        "LAR": 11,
        "NE": 11,
        "SEA": 11,
        "BAL": 13,
        "IND": 13,
        "LV": 13,
        "NYJ": 13,
        "ARI": 14,
        "DAL": 14,
    }

    records = []
    for sleeper_id, p in players_data.items():
        if not p.get("active"):
            continue

        pos = p.get("position")
        if pos not in ["QB", "RB", "WR", "TE", "K", "DEF"]:
            continue

        player_id = (
            p.get("gsis_id") or p.get("sportradar_id") or f"sleeper_{sleeper_id}"
        )
        full_name = p.get("full_name") or f"{p.get('first_name')} {p.get('last_name')}"
        team_abbr = p.get("team")

        # Cross-reference the team abbreviation to attach the correct 2026 bye week
        player_bye = bye_map.get(team_abbr, None) if team_abbr else None

        records.append(
            (
                player_id,
                sleeper_id,
                full_name,
                pos,
                team_abbr,
                p.get("age"),
                p.get("years_exp"),
                p.get("depth_chart_order"),
                player_bye,
            )
        )

    pool = await get_db()
    async with pool.acquire() as conn:
        upsert_query = """
            INSERT INTO player_ti (
                player_id, sleeper_id, player_name, position, team_abbr, age, years_exp, depth_chart_order, bye_week
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (player_id) DO UPDATE SET
                sleeper_id = EXCLUDED.sleeper_id,
                player_name = EXCLUDED.player_name,
                position = EXCLUDED.position,
                team_abbr = EXCLUDED.team_abbr,
                age = EXCLUDED.age,
                years_exp = EXCLUDED.years_exp,
                depth_chart_order = EXCLUDED.depth_chart_order,
                bye_week = EXCLUDED.bye_week,
                updated_at = CURRENT_TIMESTAMP;
        """
        async with conn.transaction():
            await conn.executemany(upsert_query, records)

        return {"status": "success", "synced_players": len(records)}


@app.post("/api/fantasypros/upload")
async def upload_fantasypros_csv(file: UploadFile = File(...)):
    """Ingests FantasyPros cheatsheet using strict Team + Name matching."""
    content = await file.read()
    decoded = content.decode("utf-8-sig")

    delimiter = "\t" if "\t" in decoded[:300] else ","
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)

    records = []
    for row in reader:
        clean_row = {}
        for k, v in row.items():
            if k is not None:
                clean_row[str(k).strip().upper()] = (
                    str(v).strip() if v is not None else ""
                )

        raw_name = ""
        for k, v in clean_row.items():
            if "PLAYER" in k:
                raw_name = v
                break

        search_pattern = build_search_pattern(raw_name)
        if not search_pattern:
            continue

        team = clean_row.get("TEAM", "").upper()
        if team == "JAC":
            team = "JAX"
        if team == "WSH":
            team = "WAS"

        def parse_num(val_str):
            m = re.search(r"(\d+)", str(val_str)) if val_str else None
            return int(m.group(1)) if m else None

        def parse_diff(diff_str):
            if not diff_str or diff_str in ("-", "N/A", "0", ""):
                return 0
            try:
                return int(float(str(diff_str).replace("+", "").strip()))
            except ValueError:
                return 0

        fp_rk = fp_tier = fp_upside = fp_bust = fp_sos = None
        fp_ecr_vs_adp = 0

        for k, v in clean_row.items():
            if k in ("RK", "RANK"):
                fp_rk = parse_num(v)
            elif "TIER" in k:
                fp_tier = parse_num(v)
            elif "UPSIDE" in k:
                fp_upside = parse_num(v)
            elif "BUST" in k:
                fp_bust = parse_num(v)
            elif "SOS" in k:
                fp_sos = parse_num(v)
            elif "ECR" in k and "ADP" in k:
                fp_ecr_vs_adp = parse_diff(v)

        records.append(
            (
                fp_rk,
                fp_tier,
                fp_upside,
                fp_bust,
                fp_sos,
                fp_ecr_vs_adp,
                search_pattern,
                team,
            )
        )

    pool = await get_db()
    async with pool.acquire() as conn:
        update_sql = """
            UPDATE player_ti
            SET 
                fp_rank = $1,
                fp_tier = $2,
                fp_upside = $3,
                fp_bust = $4,
                fp_sos = $5,
                fp_ecr_vs_adp = $6,
                updated_at = CURRENT_TIMESTAMP
            WHERE LOWER(player_name) LIKE LOWER($7)
            AND ($8 = '' OR team_abbr = $8);
        """
        async with conn.transaction():
            await conn.executemany(update_sql, records)

    return {"status": "success", "processed_records": len(records)}


@app.post("/api/weekly-projections/upload")
async def upload_weekly_projections(
    week: int = Form(...), season: int = Form(2026), file: UploadFile = File(...)
):
    """Memory-efficient upload for FantasyPros Weekly Projections CSV."""
    content = await file.read()
    decoded = content.decode("utf-8-sig")
    delimiter = "\t" if "\t" in decoded[:300] else ","
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)

    records = []
    for row in reader:
        clean_row = {
            str(k).strip().upper(): str(v).strip() for k, v in row.items() if k
        }
        raw_name = clean_row.get("PLAYER") or clean_row.get("PLAYER NAME") or ""
        if not raw_name:
            continue

        clean_name = raw_name.split("(")[0].strip()
        team = clean_row.get("TEAM", "").upper()
        pos = clean_row.get("POS", "").upper()

        # Extract numeric rank if pos is formatted like 'WR12'
        pos_rank = None
        m_rank = re.search(r"(\d+)", pos)
        if m_rank:
            pos_rank = int(m_rank.group(1))
            pos = re.sub(r"\d+", "", pos)

        try:
            fpts = float(clean_row.get("FPTS") or clean_row.get("POINTS") or 0.0)
        except ValueError:
            fpts = 0.0

        records.append((season, week, clean_name, pos, team, fpts, pos_rank))

    pool = await get_db()
    async with pool.acquire() as conn:
        upsert_query = """
            INSERT INTO weekly_projections (season, week, player_name, position, team_abbr, projected_points, pos_rank)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (season, week, player_name, team_abbr) DO UPDATE SET
                projected_points = EXCLUDED.projected_points,
                pos_rank = EXCLUDED.pos_rank,
                position = EXCLUDED.position;
        """
        async with conn.transaction():
            await conn.executemany(upsert_query, records)

    return {"status": "success", "processed_records": len(records), "week": week}


@app.get("/api/weekly/roster-analysis")
async def get_weekly_roster_analysis(
    league_id: str, week: int, user_id: str, season: int = 2026
):
    """
    Aggregates:
    - User starting lineup vs bench
    - Opponent starting lineup (head-to-head comparison)
    - Injury designations, bye statuses, favorability index, player gems
    - Top waiver wire targets sorted by weekly projection
    """
    session = await get_session()

    # 1. Fetch League Rosters, Users, and Matchups concurrently
    async with (
        session.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters") as r_resp,
        session.get(
            f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
        ) as m_resp,
        session.get(f"https://api.sleeper.app/v1/league/{league_id}/users") as u_resp,
    ):
        rosters = await r_resp.json()
        matchups = await m_resp.json()
        users = await u_resp.json()

    # Identify user roster_id
    user_map = {u["user_id"]: u.get("display_name", "Unknown") for u in users}
    user_roster_id = None
    for r in rosters:
        if (
            str(r.get("owner_id")) == str(user_id)
            or user_map.get(r.get("owner_id")) == user_id
        ):
            user_roster_id = r.get("roster_id")
            break

    # Locate opponent matchup
    my_matchup = next((m for m in matchups if m.get("roster_id") == user_roster_id), {})
    matchup_id = my_matchup.get("matchup_id")
    opp_matchup = next(
        (
            m
            for m in matchups
            if m.get("matchup_id") == matchup_id
            and m.get("roster_id") != user_roster_id
        ),
        {},
    )

    # 2. Query DB for Player TI metadata, weekly projections, defensive ranks, and performance history
    pool = await get_db()
    async with pool.acquire() as conn:
        all_meta = await conn.fetch("SELECT * FROM player_ti")
        proj_records = await conn.fetch(
            "SELECT * FROM weekly_projections WHERE season = $1 AND week = $2",
            season,
            week,
        )
        actuals_records = await conn.fetch(
            "SELECT * FROM weekly_actuals WHERE season = $1 AND week < $2", season, week
        )
        def_rank_rows = await conn.fetch("SELECT * FROM opponent_defense_rank")

    meta_map = {str(p["sleeper_id"]): dict(p) for p in all_meta if p.get("sleeper_id")}
    proj_map = {p["player_name"].lower(): dict(p) for p in proj_records}
    def_ranks = {d["team_abbr"]: dict(d) for d in def_rank_rows}

    # Map historical actuals: sleeper_id -> list[{actual, projected}]
    history_map = {}
    for a in actuals_records:
        s_id = str(a["sleeper_id"])
        if s_id not in history_map:
            history_map[s_id] = []
        history_map[s_id].append(
            {
                "actual": float(a["actual_points"]),
                "projected": float(a["projected_points"]),
            }
        )

    def enrich_player(
        sleeper_id: str, is_starter: bool = False, slot: str = "BN"
    ) -> dict:
        meta = meta_map.get(str(sleeper_id), {})
        name = meta.get("player_name", "Unknown Player")
        pos = meta.get("position", "WR")
        team = meta.get("team_abbr", "FA")
        bye = meta.get("bye_week")
        is_on_bye = bye == week

        proj_data = proj_map.get(name.lower(), {})
        proj_pts = float(
            proj_data.get("projected_points") or meta.get("projected_points") or 0.0
        )
        pos_rank = proj_data.get("pos_rank")

        fav_stars, fav_desc = get_favorability_index(pos, team, def_ranks)
        history = history_map.get(str(sleeper_id), [])
        gems = calculate_player_gems(history, fav_stars)
        injury_status = (
            meta.get("status") or "Active"
        )  # 'Questionable', 'Doubtful', 'Out', 'IR'

        return {
            "sleeper_id": str(sleeper_id),
            "player_name": name,
            "position": pos,
            "team": team,
            "slot": slot,
            "is_starter": is_starter,
            "projected_points": proj_pts,
            "pos_rank_label": f"{pos}#{pos_rank}" if pos_rank else pos,
            "is_on_bye": is_on_bye,
            "injury_status": injury_status,
            "favorability_stars": fav_stars,
            "favorability_desc": fav_desc,
            "gems": gems,
        }

    # Build My Lineup
    my_starters_ids = my_matchup.get("starters") or []
    my_all_pids = next(
        (r.get("players", []) for r in rosters if r.get("roster_id") == user_roster_id),
        [],
    )
    my_starter_slots = my_matchup.get("starter_slots") or [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "K",
        "DEF",
    ]

    my_starters = [
        enrich_player(
            pid, True, my_starter_slots[idx] if idx < len(my_starter_slots) else "FLEX"
        )
        for idx, pid in enumerate(my_starters_ids)
    ]
    my_bench = [
        enrich_player(pid, False, "BN")
        for pid in my_all_pids
        if pid not in my_starters_ids
    ]

    # Build Opponent Lineup
    opp_starters_ids = opp_matchup.get("starters") or []
    opp_starters = [
        enrich_player(
            pid, True, my_starter_slots[idx] if idx < len(my_starter_slots) else "FLEX"
        )
        for idx, pid in enumerate(opp_starters_ids)
    ]

    # Compute Totals
    my_total_proj = sum(p["projected_points"] for p in my_starters)
    opp_total_proj = sum(p["projected_points"] for p in opp_starters)

    # 3. Scan Waiver Wire (Free Agents)
    all_rostered_pids = set()
    for r in rosters:
        for p in r.get("players") or []:
            all_rostered_pids.add(str(p))

    waiver_candidates = []
    for s_id, meta in meta_map.items():
        if s_id not in all_rostered_pids and meta.get("team_abbr") not in (
            "FA",
            "UNK",
            None,
        ):
            enriched = enrich_player(s_id, False, "FA")
            if (
                enriched["projected_points"] > 5.0
                or "Breakout" in enriched["gems"]
                or "Sleeper" in enriched["gems"]
            ):
                waiver_candidates.append(enriched)

    waiver_candidates.sort(key=lambda x: x["projected_points"], reverse=True)

    return {
        "week": week,
        "my_team": {
            "roster_id": user_roster_id,
            "total_projected": round(my_total_proj, 2),
            "starters": my_starters,
            "bench": my_bench,
        },
        "opponent_team": {
            "roster_id": opp_matchup.get("roster_id"),
            "owner_name": user_map.get(str(opp_matchup.get("roster_id")), "Opponent"),
            "total_projected": round(opp_total_proj, 2),
            "starters": opp_starters,
        },
        "projected_diff": round(my_total_proj - opp_total_proj, 2),
        "waiver_recommendations": waiver_candidates[:15],
    }


@app.post("/api/weekly/calculate-awards")
async def calculate_weekly_awards(league_id: str, week: int):
    """Evaluates the 10 league awards for a completed matchup week."""
    session = await get_session()
    async with (
        session.get(
            f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
        ) as m_resp,
        session.get(f"https://api.sleeper.app/v1/league/{league_id}/users") as u_resp,
        session.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters") as r_resp,
    ):
        matchups = await m_resp.json()
        users = await u_resp.json()
        rosters = await r_resp.json()

    user_map = {u["user_id"]: u.get("display_name", "Unknown") for u in users}
    roster_owner_map = {
        r["roster_id"]: user_map.get(r.get("owner_id"), f"Team {r['roster_id']}")
        for r in rosters
    }

    # Group matchups by matchup_id
    games = {}
    team_scores = []
    for m in matchups:
        m_id = m.get("matchup_id")
        r_id = m.get("roster_id")
        pts = float(m.get("points") or 0.0)
        team_scores.append(
            {
                "roster_id": r_id,
                "name": roster_owner_map.get(r_id),
                "points": pts,
                "data": m,
            }
        )
        if m_id not in games:
            games[m_id] = []
        games[m_id].append(
            {
                "roster_id": r_id,
                "name": roster_owner_map.get(r_id),
                "points": pts,
                "data": m,
            }
        )

    all_scores = [t["points"] for t in team_scores]
    median_score = sorted(all_scores)[len(all_scores) // 2] if all_scores else 0

    awards = []

    # 1. Most Points & 2. Least Points
    sorted_teams = sorted(team_scores, key=lambda x: x["points"], reverse=True)
    awards.append(
        {
            "award": "🏆 Most Points",
            "team": sorted_teams[0]["name"],
            "desc": f"Exploded for {sorted_teams[0]['points']} pts!",
        }
    )
    awards.append(
        {
            "award": "💩 Least Points",
            "team": sorted_teams[-1]["name"],
            "desc": f"Stumbled with only {sorted_teams[-1]['points']} pts.",
        }
    )

    # 3. Nailbiter (Smallest Margin of Victory)
    game_margins = []
    for m_id, teams in games.items():
        if len(teams) == 2:
            diff = abs(teams[0]["points"] - teams[1]["points"])
            winner = teams[0] if teams[0]["points"] > teams[1]["points"] else teams[1]
            loser = teams[1] if winner == teams[0] else teams[0]
            game_margins.append(
                {"diff": diff, "winner": winner["name"], "loser": loser["name"]}
            )

    if game_margins:
        closest = min(game_margins, key=lambda x: x["diff"])
        awards.append(
            {
                "award": "😱 Nailbiter",
                "team": f"{closest['winner']} vs {closest['loser']}",
                "desc": f"Decided by a razor-thin {round(closest['diff'], 2)} pts!",
            }
        )

    # 4. Tough Break (Lost despite beating > 50% of league)
    tough_breaks = []
    for g in game_margins:
        loser_pts = next(t["points"] for t in team_scores if t["name"] == g["loser"])
        beaten_count = sum(1 for s in all_scores if loser_pts > s)
        if beaten_count >= len(all_scores) / 2:
            tough_breaks.append(
                {"name": g["loser"], "pts": loser_pts, "beaten": beaten_count}
            )
    if tough_breaks:
        tb_winner = max(tough_breaks, key=lambda x: x["pts"])
        awards.append(
            {
                "award": "💔 Tough Break",
                "team": tb_winner["name"],
                "desc": f"Scored {tb_winner['pts']} pts (would have beaten {tb_winner['beaten']} other teams), but took the L.",
            }
        )

    # 5. Lucky Week (Won despite scoring below median)
    lucky_winners = []
    for g in game_margins:
        win_pts = next(t["points"] for t in team_scores if t["name"] == g["winner"])
        lost_to_count = sum(1 for s in all_scores if win_pts < s)
        if lost_to_count >= len(all_scores) / 2:
            lucky_winners.append(
                {"name": g["winner"], "pts": win_pts, "lost_to": lost_to_count}
            )
    if lucky_winners:
        lucky = min(lucky_winners, key=lambda x: x["pts"])
        awards.append(
            {
                "award": "🍀 Lucky Week",
                "team": lucky["name"],
                "desc": f"Won with only {lucky['pts']} pts (would have lost to {lucky['lost_to']} other teams)!",
            }
        )

    # 6. Bench Star & 7. Nostradamus
    # Evaluates starters vs bench points
    for t in team_scores:
        players_points = t["data"].get("players_points") or {}
        starters = t["data"].get("starters") or []
        all_pids = t["data"].get("players") or []
        bench = [pid for pid in all_pids if pid not in starters]

        starter_pts = [players_points.get(pid, 0.0) for pid in starters]
        bench_pts = [players_points.get(pid, 0.0) for pid in bench]

        min_starter = min(starter_pts) if starter_pts else 0
        max_bench = max(bench_pts) if bench_pts else 0

        # Bench Star: 2+ bench outscoring starters
        outscoring_bench_count = sum(1 for bp in bench_pts if bp > min_starter)
        if outscoring_bench_count >= 2:
            awards.append(
                {
                    "award": "🪑 Bench Star",
                    "team": t["name"],
                    "desc": f"Left massive points on the bench ({outscoring_bench_count} bench players outscored active starters).",
                }
            )

        # Nostradamus: Perfect lineup
        if max_bench <= min_starter and starter_pts:
            awards.append(
                {
                    "award": "🔮 Nostradamus",
                    "team": t["name"],
                    "desc": f"Flawless lineup management! Lowest starter ({min_starter} pts) beat highest bench player ({max_bench} pts).",
                }
            )

    return {"week": week, "awards": awards}


@app.post("/api/discord/post-awards")
async def post_awards_to_discord(webhook_url: str, payload: dict):
    """Dispatches a formatted Discord Embed for the weekly league awards."""
    awards = payload.get("awards", [])
    week = payload.get("week", 1)

    fields = [
        {"name": a["award"], "value": f"**{a['team']}**\n{a['desc']}", "inline": False}
        for a in awards
    ]

    embed = {
        "title": f"⚡ Week {week} League Awards Recap",
        "description": "Here are this week's official honors, lucky escapes, and heartbreaking beats!",
        "color": 48065,  # Deep Teal (#00B5C1)
        "fields": fields,
        "footer": {"text": "Trey Index Analytics • Generated automatically"},
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json={"embeds": [embed]}) as resp:
            if resp.status in (200, 204):
                return {"status": "success", "message": "Dispatched to Discord!"}
            else:
                text = await resp.text()
                return {"status": "error", "detail": text}
