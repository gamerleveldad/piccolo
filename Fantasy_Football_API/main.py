import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
import asyncpg  # type: ignore[import]
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ti import calculate_ti_score

HANDCUFF_CSV_FILE = File(...)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("fantasy_api")

# adding environment variables for Sleeper API and PostgreSQL connection
SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME", "your_username")
SLEEPER_SEASON = os.getenv("SLEEPER_SEASON", "2026")
SLEEPER_DYNASTY_LEAGUE_ID = os.getenv(
    "SLEEPER_DYNASTY_LEAGUE_ID", "1360812344053071872"
)

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")


async def get_db_connection():
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    return await asyncpg.connect(db_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    Verifies and creates required PostgreSQL table schemas before accepting requests.
    """
    # Startup execution
    conn = await get_db_connection()
    try:
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
            ADD COLUMN IF NOT EXISTS rotowire_id VARCHAR(50);
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
        logger.info("Database schemas verified successfully via lifespan startup.")
    except (asyncpg.PostgresError, OSError) as e:
        logger.error(f"Failed to initialize database schemas during startup: {e}")
    finally:
        await conn.close()

    # Yield control back to FastAPI to serve requests
    yield

    # Shutdown logic can be placed here if needed in the future


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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_league) as resp:
                if resp.status != 200:
                    return {"mode": "disabled"}
                league_data = await resp.json()

            if league_data.get("status") == "pre_draft":
                url_drafts = f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/drafts"
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
                    u["user_id"]: u.get("metadata", {}).get(
                        "team_name", u["display_name"]
                    )
                    for u in users
                }

            async with session.get(
                f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/rosters"
            ) as r_resp:
                rosters = await r_resp.json()
                roster_to_owner = {
                    r["roster_id"]: user_map.get(
                        r["owner_id"], f"Team {r['roster_id']}"
                    )
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


# --- Append to the end of Fantasy_Football_API/main.py ---


@app.post("/api/rankings/team-units")
async def update_team_unit_rankings(rankings: dict):
    """
    Receives team unit rankings (1-32) from React UI and stores in DB.
    Expected JSON format:
    {
        "MIA": {"oline_rank": 5, "qb_rank": 10, "wr_rank": 1, "te_rank": 20, "rb_rank": 3, "def_rank": 18, "off_rank": 4}
    }
    """
    conn = await get_db_connection()
    try:
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
    finally:
        await conn.close()


@app.get("/api/ti/master-board")
async def get_master_draft_board():
    """
    Pulls player projections, historical metrics, and team unit ranks,
    calculates live TI scores, and returns sorted master draft board.
    """
    conn = await get_db_connection()
    try:
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
    finally:
        await conn.close()


@app.get("/api/sleeper/leagues")
async def get_user_leagues():
    """
    Fetches the user_id using SLEEPER_USERNAME, then retrieves all active leagues for the season.
    """
    url_user = f"https://api.sleeper.app/v1/user/{SLEEPER_USERNAME}"

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Get User ID from Username
            async with session.get(url_user) as resp_user:
                if resp_user.status != 200:
                    raise HTTPException(
                        status_code=404, detail="Sleeper user not found"
                    )
                user_data = await resp_user.json()
                user_id = user_data.get("user_id")

            # 2. Get all leagues for that user ID and season
            url_leagues = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{SLEEPER_SEASON}"
            async with session.get(url_leagues) as resp_leagues:
                if resp_leagues.status != 200:
                    raise HTTPException(
                        status_code=500, detail="Failed to fetch leagues"
                    )
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
    conn = await get_db_connection()
    try:
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

            # Select target score based on board mode
            target_score = (
                score_data["ti_score_dynasty"]
                if board_type == "dynasty"
                else score_data["ti_score"]
            )

            draft_board.append(
                {
                    "player_id": p_id,
                    "player_name": p["player_name"],
                    "position": p["position"],
                    "team": p["team_abbr"],
                    "age": p.get("age"),
                    "bye_week": p.get("bye_week"),
                    "depth_chart_position": p.get("depth_chart_position"),
                    "depth_chart_order": p.get("depth_chart_order"),
                    "is_pinned": p["is_pinned"],
                    "manual_rank": p["manual_rank"],
                    "ti_score": score_data["ti_score"],
                    "ti_score_dynasty": score_data["ti_score_dynasty"],
                    "consistency_score": cons_data["rating"],
                    "consistency_label": cons_data["label"],
                    "target_score": target_score,
                    "projected_points": p.get("projected_points") or 0.0,
                    "projected_next_game": p.get("projected_next_game") or 0.0,
                    "projected_next_4": p.get("projected_next_4") or 0.0,
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

        return {"board_type": board_type, "players": draft_board}
    finally:
        await conn.close()


@app.post("/api/ti/board/{board_type}/reorder")
async def reorder_board_player(board_type: str, payload: ReorderPayload):
    """
    Saves new manual ranks to `board_player_order` upon drag-and-drop.
    """
    conn = await get_db_connection()
    try:
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
    finally:
        await conn.close()


@app.post("/api/ti/board/{board_type}/reset")
async def reset_board_order(board_type: str):
    """
    Clears all manual overrides for a specific board type, reverting back to pure TI calculations.
    """
    conn = await get_db_connection()
    try:
        await conn.execute(
            "DELETE FROM board_player_order WHERE board_type = $1", board_type
        )
        return {
            "status": "success",
            "message": f"Board {board_type} reset to default TI order.",
        }
    finally:
        await conn.close()


# --- Insert in Fantasy_Football_API/main.py near existing team-units endpoint ---


@app.get("/api/rankings/team-units")
async def get_team_unit_rankings():
    """
    Fetches all stored 1-32 team unit rankings from PostgreSQL.
    Returns a dictionary keyed by team abbreviation.
    """
    conn = await get_db_connection()
    try:
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
    finally:
        await conn.close()


import io

import pandas as pd  # type: ignore[import]

upload_file = File(...)


@app.post("/api/projections/upload")
async def upload_projections_csv(file: UploadFile = upload_file):
    """
    Accepts a CSV file downloaded from a projections site,
    parses the Player and FPTS columns, and updates the database.
    """
    content = await file.read()

    try:
        # Read the CSV into a pandas DataFrame
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))

        # Standardize column names to uppercase for easy matching
        df.columns = [str(c).upper().strip() for c in df.columns]

        conn = await get_db_connection()
        updated_count = 0

        try:
            update_query = """
                UPDATE player_ti 
                SET projected_points = $1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(player_name) LIKE LOWER($2);
            """

            for _, row in df.iterrows():
                # Find the player name and fantasy points columns dynamically
                player_col = next((col for col in df.columns if "PLAYER" in col), None)
                fpts_col = next(
                    (col for col in df.columns if "FPTS" in col or "POINTS" in col),
                    None,
                )

                if not player_col or not fpts_col:
                    continue

                # --- NEW: Skip completely empty rows or NaN values ---
                if pd.isna(row[player_col]) or pd.isna(row[fpts_col]):
                    continue

                # Clean full name from CSV (e.g. "Josh Allen" or "Josh Allen BUF")
                raw_name = str(row[player_col]).split("(")[0].strip()
                if not raw_name:
                    continue

                name_parts = raw_name.split()
                if (
                    len(name_parts) > 1
                    and len(name_parts[-1]) in [2, 3]
                    and name_parts[-1].isupper()
                ):
                    clean_name = " ".join(name_parts[:-1])
                else:
                    clean_name = raw_name

                try:
                    proj_pts = float(row[fpts_col])
                    if pd.isna(proj_pts):
                        continue

                    proj_ppg = round(proj_pts / 17.0, 2)

                    # Direct full-name matching against PostgreSQL full names
                    search_pattern = f"%{clean_name}%"

                    result = await conn.execute(update_query, proj_ppg, search_pattern)

                    if result.startswith("UPDATE"):
                        count = int(result.split(" ")[1])
                        updated_count += count

                except ValueError:
                    continue

            return {"status": "success", "updated": updated_count}

        finally:
            await conn.close()

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


# --- Append to Fantasy_Football_API/main.py ---


@app.get("/api/sleeper/leagues/{user_identifier}")
async def get_sleeper_leagues(user_identifier: str, year: str = "2026"):
    """
    Fetches all NFL leagues for a Sleeper user.
    Automatically resolves text usernames to numeric user_ids.
    """
    async with aiohttp.ClientSession() as session:
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
    async with aiohttp.ClientSession() as session, session.get(url) as resp:
        if resp.status == 200:
            return await resp.json()
        return []


@app.get("/api/sleeper/draft/{draft_id}/state")
async def get_draft_state(draft_id: str, user_id: str = None, roster_id: str = None):
    """
    Fetches live picks for a draft. Uses deep metadata extraction to bypass
    Sleeper's hidden roster_ids in Auction Mock Drafts.
    """
    draft_url = f"https://api.sleeper.app/v1/draft/{draft_id}"
    picks_url = f"https://api.sleeper.app/v1/draft/{draft_id}/picks"

    async with aiohttp.ClientSession() as session:
        # Resolve numeric user_id if text username was provided
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

    # 1. Clean the manual override
    user_roster_id_str = str(roster_id).strip() if roster_id else None

    # 2. Fallback auto-resolution if no override is provided
    if not user_roster_id_str and user_id_str and draft_meta:
        draft_order = draft_meta.get("draft_order") or {}
        d_slot = draft_order.get(user_id_str)
        if d_slot:
            slot_to_roster = draft_meta.get("slot_to_roster_id") or {}
            user_roster_id_str = str(slot_to_roster.get(str(d_slot), d_slot))

    drafted_player_ids = []
    my_roster = {"QB": [], "RB": [], "WR": [], "TE": [], "DEF": [], "K": [], "ALL": []}
    amount_spent = 0

    for pick in picks:
        pid = str(pick.get("player_id") or "")
        if not pid:
            continue

        drafted_player_ids.append(pid)

        metadata = pick.get("metadata") or {}
        pick_owner_user = str(pick.get("picked_by") or "")

        # Deep extraction for Auction Mocks where roster_id is buried
        pick_roster_id = str(
            pick.get("roster_id")
            or metadata.get("roster_id")
            or metadata.get("team_id")
            or ""
        )

        is_my_pick = False

        # Match 1: Manual Override matches the deep-extracted roster ID
        if user_roster_id_str and pick_roster_id == user_roster_id_str:
            is_my_pick = True
        # Match 2: Real user ID matches the pick owner
        elif user_id_str and user_id_str.isdigit() and pick_owner_user == user_id_str:
            is_my_pick = True

        if is_my_pick:
            pos = metadata.get("position", "ALL")
            # Extract amount from metadata or root
            amount_val = metadata.get("amount") or pick.get("amount") or 0

            my_roster["ALL"].append(pid)
            if pos in my_roster:
                my_roster[pos].append(pid)

            try:
                amount_spent += int(amount_val)
            except (ValueError, TypeError):
                pass

    # Safety catch for budget setting
    total_budget = draft_meta.get("settings", {}).get("budget") or 200

    return {
        "draft_id": draft_id,
        "status": draft_meta.get("status"),
        "draft_type": draft_meta.get("type"),
        "budget": total_budget,
        "total_roster_spots": draft_meta.get("settings", {}).get("roster_size", 16),
        "drafted_player_ids": drafted_player_ids,
        "my_roster": my_roster,
        "amount_spent": amount_spent,
        "remaining_budget": max(0, total_budget - amount_spent),
    }


def check_bye_constraint(pos: str, player_bye: int, my_roster_byes: dict) -> dict:
    """Evaluates a player's bye week against the user's drafted roster."""
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
    """Converts raw CV into a 0-100 rating with a readable tier label."""
    if cv is None:
        cv = 0.40

    # Softened curve: 0.20 or lower = 100 (Rock Solid), 0.75 or higher = 0 (Boom/Bust)
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
    """
    Calculates diminishing marginal utility as roster slots fill up for a given position.
    """
    pos = pos.upper()
    if pos in ("QB", "TE"):
        if drafted_count == 1:
            return 0.30
        if drafted_count >= 2:
            return 0.05
    elif pos == "RB":
        if drafted_count == 2:
            return 0.85  # 3rd RB (1st bench RB)
        if drafted_count == 3:
            return 0.65  # 4th RB
        if drafted_count >= 4:
            return 0.40  # 5th+ RB
    elif pos == "WR":
        if drafted_count == 3:
            return 0.90  # 4th WR (1st bench WR)
        if drafted_count == 4:
            return 0.75  # 5th WR
        if drafted_count >= 5:
            return 0.50  # 6th+ WR
    return 1.00


# --- Update in Fantasy_Football_API/main.py ---


@app.get("/api/draft/recommendations")
async def get_live_recommendations(
    draft_id: str, user_id: str, format: str = "snake", roster_id: str = None
):
    draft_state = await get_draft_state(draft_id, user_id, roster_id)
    drafted_set = {str(pid) for pid in draft_state["drafted_player_ids"]}
    my_roster_pids = [str(pid) for pid in draft_state["my_roster"]["ALL"]]

    conn = await get_db_connection()
    try:
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

        # First Pass: Compute raw TI scores and build baselines
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

        # Second Pass: Apply Roster Need Multiplier to TI Score & VORP
        for item in raw_player_data:
            p = item["db_record"]
            pos = item["pos"]
            score_data = item["score_data"]
            bye_check = item["bye_check"]

            # --- APPLY ROSTER NEED MULTIPLIER HERE ---
            roster_count = my_roster_counts.get(pos, 0)
            need_mult = calculate_roster_need_multiplier(pos, roster_count)

            raw_ti = score_data["ti_score"]
            base = baselines.get(pos, 10.0)
            raw_vorp = raw_ti - base

            # Apply need penalty
            final_ti = round(raw_ti * need_mult, 2)
            final_vorp = round(raw_vorp * need_mult, 2)

            c_score = p.get("consistency_score")
            cons_data = format_consistency_score(c_score)

            available_players.append(
                {
                    "player_id": p["player_id"],
                    "sleeper_id": item["sleeper_id"],
                    "player_name": p["player_name"],
                    "position": pos,
                    "team": p["team_abbr"],
                    "age": p.get("age"),
                    "bye_week": p.get("bye_week"),
                    "depth_chart_position": p.get("depth_chart_position"),
                    "depth_chart_order": p.get("depth_chart_order"),
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
                    "auction_max_bid": 0,
                }
            )
        # 4. Auction "Don't Go Over" Calculation
        # Realistic Auction "Don't Go Over" Max Bid Calculation
        if format.lower() == "auction":
            total_budget = draft_state.get("budget", 200) or 200
            rem_budget = draft_state["remaining_budget"]
            open_spots = max(1, draft_state["total_roster_spots"] - len(my_roster_pids))
            absolute_max_bid = max(1, rem_budget - (open_spots - 1))

            # Position target allocation % and starter count in standard lineup
            pos_config = {
                "QB": {"alloc": 0.15, "starters": 1},
                "RB": {"alloc": 0.35, "starters": 2},
                "WR": {"alloc": 0.35, "starters": 3},
                "TE": {"alloc": 0.10, "starters": 1},
            }

            # Calculate average starter TI score for each position
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

                # Average dollars allocated per starter slot
                avg_slot_cost = (cfg["alloc"] * total_budget) / cfg["starters"]

                # Ratio of player's TI relative to an average starter
                ti_ratio = (
                    player["ti_score"] / avg_starter_ti if avg_starter_ti > 0 else 1.0
                )

                # Budget decay factor (scales bids as remaining budget diminishes)
                budget_scale = rem_budget / total_budget if total_budget > 0 else 1.0

                bid_calc = ti_ratio * avg_slot_cost * budget_scale
                recommended_bid = round(bid_calc)

                # Cap at absolute max capacity to ensure $1 is reserved for all open spots
                player["auction_max_bid"] = (
                    min(recommended_bid, absolute_max_bid) if recommended_bid > 0 else 1
                )

        # 5. Sort Recommendations by Adjusted VORP
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
            "my_roster_byes": my_roster_byes,
            "my_roster_counts": my_roster_counts,
            "baselines": baselines,
            "board": available_players,
        }
    finally:
        await conn.close()


@app.post("/api/handcuffs/upload")
async def upload_handcuffs_csv(file: UploadFile = HANDCUFF_CSV_FILE):
    """Ingests FantasyPros Handcuff rankings CSV to update depth chart orders."""
    content = await file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    df.columns = [str(c).upper().strip() for c in df.columns]

    conn = await get_db_connection()
    updated = 0
    try:
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
    finally:
        await conn.close()
