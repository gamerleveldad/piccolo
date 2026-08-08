import os
import aiohttp
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from pydantic import BaseModel
from typing import Optional
from ti import calculate_ti_score
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fantasy_api")

SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME", "your_username")
SLEEPER_SEASON = os.getenv("SLEEPER_SEASON", "2026")
SLEEPER_DYNASTY_LEAGUE_ID = os.getenv("SLEEPER_DYNASTY_LEAGUE_ID", "1360812344053071872")

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
    except Exception as e:
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
                            "draft_start": drafts[0].get("start_time")
                        }

            current_week = league_data.get("settings", {}).get("leg", 1)
            
            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/users") as u_resp:
                users = await u_resp.json()
                user_map = {u['user_id']: u.get('metadata', {}).get('team_name', u['display_name']) for u in users}
                
            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/rosters") as r_resp:
                rosters = await r_resp.json()
                roster_to_owner = {r['roster_id']: user_map.get(r['owner_id'], f"Team {r['roster_id']}") for r in rosters}

            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_DYNASTY_LEAGUE_ID}/matchups/{current_week}") as m_resp:
                matchups_raw = await m_resp.json()

            match_groups = {}
            for team in matchups_raw:
                m_id = team.get("matchup_id")
                if m_id not in match_groups: match_groups[m_id] = []
                
                match_groups[m_id].append({
                    "owner_name": roster_to_owner.get(team['roster_id'], "Unknown"),
                    "points": team.get("points", 0.0),
                    "projected_points": sum(team.get("starters_points", [0])),
                    "starters": team.get("starters", []),
                    "players": team.get("players", []),
                    "custom_roster_points_map": team.get("players_points", {})
                })

            return {
                "mode": "matchups",
                "week": current_week,
                "matchups": list(match_groups.values())
            }
            
    except Exception as e:
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
                ranks.get("off_rank")
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
        team_ranks_map = {r['team_abbr']: dict(r) for r in team_rows}

        # Fetch player metrics
        player_rows = await conn.fetch("SELECT * FROM player_ti")
        
        draft_board = []
        for p in player_rows:
            player_team = p.get('team_abbr')
            unit_ranks = team_ranks_map.get(player_team, {})
            
            # Run TI Calculation
            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                age=p.get("age")
            )

            draft_board.append({
                "player_id": p['player_id'],
                "player_name": p['player_name'],
                "position": p['position'],
                "team": player_team,
                "ti": score_data['ti_score'],
                "details": score_data
            })

        # Sort draft board descending by TI
        draft_board.sort(key=lambda x: x['ti'], reverse=True)
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
                    raise HTTPException(status_code=404, detail="Sleeper user not found")
                user_data = await resp_user.json()
                user_id = user_data.get("user_id")

            # 2. Get all leagues for that user ID and season
            url_leagues = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{SLEEPER_SEASON}"
            async with session.get(url_leagues) as resp_leagues:
                if resp_leagues.status != 200:
                    raise HTTPException(status_code=500, detail="Failed to fetch leagues")
                leagues_data = await resp_leagues.json()

            # 3. Format the response for your React frontend dropdown
            active_leagues = []
            for league in leagues_data:
                active_leagues.append({
                    "league_id": league.get("league_id"),
                    "name": league.get("name"),
                    "status": league.get("status"),
                    "total_rosters": league.get("total_rosters")
                })
                
            return {
                "username": SLEEPER_USERNAME, 
                "season": SLEEPER_SEASON, 
                "leagues": active_leagues
            }
            
    except Exception as e:
        logger.error(f"Failed to fetch user leagues: {e}")
        raise HTTPException(status_code=500, detail="Internal API error")

class ReorderRequest(BaseModel):
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
                "off_rank": r.get("off_rank", 16)
            }
        return rankings
    except Exception as e:
        logger.warning(f"Could not load team unit rankings: {e}")
        return {}
@app.get("/api/ti/board/{board_type}")
async def get_draft_board(board_type: str = "standard"):
    """
    Fetches the draft board (standard, dynasty, or chopped),
    applies TI score calculations, depth chart penalties,
    filters inactive/teamless players, and sorts by effective rank.
    """
    conn = await get_db_connection()
    try:
        # 1. Fetch current team unit rankings
        unit_ranks = await fetch_team_unit_ranks(conn)

        # 2. Query active players (excluding Free Agents, UNK, and Inactive/Retired players)
        query = """
            SELECT * FROM player_ti
            WHERE team_abbr IS NOT NULL 
              AND team_abbr NOT IN ('FA', 'UNK', 'None', '')
              AND (status IS NULL OR LOWER(status) NOT IN ('inactive', 'retired', 'cut'))
        """
        rows = await conn.fetch(query)

        # 3. Check for manual board pins/overrides if table exists
        pinned_dict = {}
        try:
            pins = await conn.fetch("SELECT player_id, manual_rank FROM board_pins WHERE board_type = $1", board_type)
            pinned_dict = {p["player_id"]: p["manual_rank"] for p in pins}
        except Exception:
            pass  # Fallback if board_pins table hasn't been instantiated yet

        draft_board = []
        for p in rows:
            p_id = p["player_id"]

            # Compute TI Scores
            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                age=p.get("age"),
                depth_chart_order=p.get("depth_chart_order")
            )

            is_pinned = p_id in pinned_dict
            
            # Select target score based on requested board type
            target_score = score_data["ti_score_dynasty"] if board_type == "dynasty" else score_data["ti_score"]

            draft_board.append({
                "player_id": p_id,
                "player_name": p["player_name"],
                "position": p["position"],
                "team": p["team_abbr"],
                "age": p.get("age"),
                "bye_week": p.get("bye_week"),
                "depth_chart_position": p.get("depth_chart_position"),
                "depth_chart_order": p.get("depth_chart_order"),
                "is_pinned": is_pinned,
                "manual_rank": pinned_dict.get(p_id),
                "ti_score": score_data["ti_score"],
                "ti_score_dynasty": score_data["ti_score_dynasty"],
                "target_score": target_score,
                "projected_points": p.get("projected_points") or 0.0,
                "projected_next_game": p.get("projected_next_game") or 0.0,
                "projected_next_4": p.get("projected_next_4") or 0.0,
                "details": score_data
            })

        # Sort by mathematical score descending
        draft_board.sort(key=lambda x: x["target_score"], reverse=True)

        # Calculate effective_rank for each player (honoring manual pins)
        for idx, item in enumerate(draft_board):
            if item["is_pinned"] and item["manual_rank"] is not None:
                item["effective_rank"] = float(item["manual_rank"])
            else:
                item["effective_rank"] = float(idx + 1)

        # Final sort by effective rank ascending
        draft_board.sort(key=lambda x: x["effective_rank"])

        return {
            "count": len(draft_board),
            "board_type": board_type,
            "draft_board": draft_board
        }
    finally:
        await conn.close()


@app.post("/api/ti/board/{board_type}/reorder")
async def reorder_board_player(board_type: str, req: ReorderRequest):
    """
    Updates a player's position relative to their adjacent global board neighbors.
    Supports filtered position drags by inserting the moved player between
    the global neighbors specified by the frontend payload.
    """
    conn = await get_db_connection()
    try:
        # Fetch current custom order records for reference
        order_rows = await conn.fetch(
            "SELECT player_id, manual_rank FROM board_player_order WHERE board_type = $1",
            board_type
        )
        rank_map = {r["player_id"]: r["manual_rank"] for r in order_rows}

        above_rank = rank_map.get(req.target_above_player_id) if req.target_above_player_id else None
        below_rank = rank_map.get(req.target_below_player_id) if req.target_below_player_id else None

        # Calculate new relative rank float
        if above_rank is not None and below_rank is not None:
            new_rank = (above_rank + below_rank) / 2.0
        elif above_rank is not None:
            # Moved to the bottom below the last element
            new_rank = above_rank + 1.0
        elif below_rank is not None:
            # Moved to the absolute top above the first element
            new_rank = below_rank - 1.0
        else:
            # Fallback default rank
            new_rank = 1.0

        # Upsert the new manual rank into PostgreSQL
        upsert_query = """
            INSERT INTO board_player_order (board_type, player_id, manual_rank, is_pinned, updated_at)
            VALUES ($1, $2, $3, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (board_type, player_id) DO UPDATE SET
                manual_rank = EXCLUDED.manual_rank,
                is_pinned = TRUE,
                updated_at = CURRENT_TIMESTAMP;
        """
        await conn.execute(upsert_query, board_type, req.player_id, new_rank)

        return {
            "status": "success",
            "board_type": board_type,
            "player_id": req.player_id,
            "new_manual_rank": new_rank
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
        await conn.execute("DELETE FROM board_player_order WHERE board_type = $1", board_type)
        return {"status": "success", "message": f"Board {board_type} reset to default TI order."}
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
                "off_rank": r["off_rank"]
            }
        return {"rankings": rankings}
    finally:
        await conn.close()

# --- Append to Fantasy_Football_API/main.py ---
from fastapi import UploadFile, File
import pandas as pd
import io

@app.post("/api/projections/upload")
async def upload_projections_csv(file: UploadFile = File(...)):
    """
    Accepts a CSV file downloaded from a projections site,
    parses the Player and FPTS columns, and updates the database.
    """
    content = await file.read()
    
    try:
        # Read the CSV into a pandas DataFrame
        df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        
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
                player_col = next((col for col in df.columns if 'PLAYER' in col), None)
                fpts_col = next((col for col in df.columns if 'FPTS' in col or 'POINTS' in col), None)
                
                if not player_col or not fpts_col:
                    continue 
                
                # --- NEW: Skip completely empty rows or NaN values ---
                if pd.isna(row[player_col]) or pd.isna(row[fpts_col]):
                    continue
                    
                # Clean full name from CSV (e.g. "Josh Allen" or "Josh Allen BUF")
                raw_name = str(row[player_col]).split('(')[0].strip()
                if not raw_name:
                    continue
                
                name_parts = raw_name.split()
                if len(name_parts) > 1 and len(name_parts[-1]) in [2, 3] and name_parts[-1].isupper():
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
            
    except Exception as e:
        logger.error(f"CSV Upload failed: {e}")
        return {"status": "error", "message": str(e)}

# --- Append to Fantasy_Football_API/main.py ---
import aiohttp

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
                    return [] # Username not found

        # Step 2: Fetch the leagues using the numeric user_id
        leagues_url = f"https://api.sleeper.app/v1/user/{user_identifier}/leagues/nfl/{year}"
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
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

@app.get("/api/sleeper/draft/{draft_id}/state")
async def get_draft_state(draft_id: str, user_id: str = None):
    """
    Fetches the live picks for a draft and returns the active state,
    including all drafted player IDs, and the specific roster/budget for the requested user.
    """
    draft_url = f"https://api.sleeper.app/v1/draft/{draft_id}"
    picks_url = f"https://api.sleeper.app/v1/draft/{draft_id}/picks"
    
    async with aiohttp.ClientSession() as session:
        # --- NEW: Resolve the numeric user_id if a username is passed ---
        if user_id and not user_id.isdigit():
            user_url = f"https://api.sleeper.app/v1/user/{user_id}"
            async with session.get(user_url) as user_resp:
                if user_resp.status == 200:
                    user_data = await user_resp.json()
                    user_id = user_data.get("user_id", user_id)
                    
        # 1. Fetch draft metadata
        async with session.get(draft_url) as draft_resp:
            draft_meta = await draft_resp.json() if draft_resp.status == 200 else {}
            
        # 2. Fetch live picks
        async with session.get(picks_url) as picks_resp:
            picks = await picks_resp.json() if picks_resp.status == 200 else []

    # Map user_id to their specific team slot in this draft
    user_draft_slot = None
    if user_id and draft_meta.get("draft_order"):
        user_draft_slot = draft_meta["draft_order"].get(user_id)

    drafted_player_ids = []
    my_roster = {
        "QB": [], "RB": [], "WR": [], "TE": [], "DEF": [], "K": [], "ALL": []
    }
    amount_spent = 0
    
    for pick in picks:
        pid = pick.get("player_id")
        if not pid:
            continue
            
        drafted_player_ids.append(pid)
        
        is_my_pick = False
        if pick.get("picked_by") == user_id:
            is_my_pick = True
        elif user_draft_slot and pick.get("roster_id") == user_draft_slot:
            is_my_pick = True
            
        if is_my_pick:
            metadata = pick.get("metadata", {})
            pos = metadata.get("position", "ALL")
            amount = metadata.get("amount", 0)
            
            my_roster["ALL"].append(pid)
            if pos in my_roster:
                my_roster[pos].append(pid)
            try:
                amount_spent += int(amount)
            except ValueError:
                pass

    total_budget = draft_meta.get("settings", {}).get("budget", 200)

    return {
        "draft_id": draft_id,
        "status": draft_meta.get("status"),
        "draft_type": draft_meta.get("type"), 
        "budget": total_budget,
        "total_roster_spots": draft_meta.get("settings", {}).get("roster_size", 16),
        "drafted_player_ids": drafted_player_ids,
        "my_roster": my_roster,
        "amount_spent": amount_spent,
        "remaining_budget": total_budget - amount_spent
    }

def check_bye_constraint(pos: str, player_bye: int, my_roster_byes: dict) -> dict:
    """Evaluates a player's bye week against the user's drafted roster."""
    if not player_bye:
        return {"blocked": False, "status": "CLEAR", "message": None}
        
    pos = pos.upper()
    current_byes = my_roster_byes.get(pos, [])
    
    if pos in ['QB', 'TE']:
        if player_bye in current_byes:
            return {"blocked": True, "status": "BLOCKED", "message": f"{pos} bye overlap (Wk {player_bye})"}
    elif pos in ['RB', 'WR']:
        count = current_byes.count(player_bye)
        if count >= 2:
            return {"blocked": True, "status": "BLOCKED", "message": f"Max (2) {pos} bye overlap (Wk {player_bye})"}
        elif count == 1:
            return {"blocked": False, "status": "WARNING", "message": f"Warning: 1 {pos} shares Wk {player_bye} bye"}
            
    return {"blocked": False, "status": "CLEAR", "message": None}

@app.get("/api/draft/recommendations")
async def get_live_recommendations(draft_id: str, user_id: str, format: str = "snake"):
    """
    Core Live Sync Endpoint:
    1. Fetches current draft state (who is taken, user's roster, budget).
    2. Filters available players from PostgreSQL.
    3. Calculates TI Scores and Bye Week constraints.
    4. Computes Auction Max Bids based on remaining budget.
    """
    # 1. Fetch live draft state
    draft_state = await get_draft_state(draft_id, user_id)
    drafted_ids = draft_state["drafted_player_ids"]
    my_roster_pids = draft_state["my_roster"]["ALL"]
    
    conn = await get_db_connection()
    try:
        unit_ranks = await fetch_team_unit_ranks(conn)
        
        # 2. Extract my roster's bye weeks
        # 2. Extract my roster's bye weeks
        my_roster_byes = {"QB": [], "RB": [], "WR": [], "TE": [], "DEF": [], "K": []}
        if my_roster_pids:
            placeholders = ",".join(f"'{pid}'" for pid in my_roster_pids)
            # --- FIXED: Query sleeper_id instead of player_id ---
            roster_query = f"SELECT position, bye_week FROM player_ti WHERE sleeper_id IN ({placeholders}) AND bye_week IS NOT NULL"
            my_roster_data = await conn.fetch(roster_query)
            for r in my_roster_data:
                pos = r["position"].upper() if r["position"] else "ALL"
                if pos in my_roster_byes:
                    my_roster_byes[pos].append(r["bye_week"])
                    
        # 3. Query all available active players
        query = """
            SELECT * FROM player_ti
            WHERE team_abbr IS NOT NULL 
              AND team_abbr NOT IN ('FA', 'UNK', 'None', '')
              AND (status IS NULL OR LOWER(status) NOT IN ('inactive', 'retired', 'cut'))
        """
        all_players = await conn.fetch(query)

        available_players = []
        pos_ti_sums = {"QB": [], "RB": [], "WR": [], "TE": []}
        
        for p in all_players:
            # Skip players already drafted
            if str(p.get("sleeper_id")) in drafted_ids:
                continue
                
            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR",
                age=p.get("age"),
                depth_chart_order=p.get("depth_chart_order")
            )
            
            # Ensure consistency score defaults safely
            c_score = p.get("consistency_score")
            consistency_val = round(c_score, 3) if c_score is not None else 0.400
            
            # Check Bye Week Constraints
            bye_check = check_bye_constraint(p.get("position", "WR"), p.get("bye_week"), my_roster_byes)
            
            p_dict = {
                "player_id": p["player_id"],
                "player_name": p["player_name"],
                "position": p.get("position", "WR"),
                "team": p["team_abbr"],
                "age": p.get("age"),
                "bye_week": p.get("bye_week"),
                "depth_chart_position": p.get("depth_chart_position"),
                "depth_chart_order": p.get("depth_chart_order"),
                "ti_score": score_data["ti_score"],
                "ti_score_dynasty": score_data["ti_score_dynasty"],
                "consistency_score": consistency_val,
                "projected_points": p.get("projected_points") or 0.0,
                "is_starter": score_data["is_starter"],
                "bye_status": bye_check["status"],
                "bye_message": bye_check["message"],
                "auction_max_bid": 0 
            }
            available_players.append(p_dict)
            
            # Store scores to calculate positional averages for Auction math
            pos = p_dict["position"].upper()
            if pos in pos_ti_sums and p_dict["is_starter"] and not bye_check["blocked"]:
                pos_ti_sums[pos].append(p_dict["ti_score"])

        # 4. Auction "Don't Go Over" Calculation
        if format.lower() == "auction":
            rem_budget = draft_state["remaining_budget"]
            # Target 16 total spots
            open_spots = draft_state["total_roster_spots"] - len(my_roster_pids)
            if open_spots < 1: open_spots = 1
            
            absolute_max_bid = rem_budget - (open_spots - 1)
            
            # Find average TI for top 24 available players at each skill position to create a baseline
            pos_avg = {}
            for pos, scores in pos_ti_sums.items():
                top_scores = sorted(scores, reverse=True)[:24]
                pos_avg[pos] = (sum(top_scores) / len(top_scores)) if len(top_scores) > 0 else 1.0

            # Target percentage allocation per position
            target_allocation = {"QB": 0.15, "RB": 0.35, "WR": 0.35, "TE": 0.10}

            for player in available_players:
                pos = player["position"].upper()
                if pos not in pos_avg or player["bye_status"] == "BLOCKED":
                    continue
                    
                baseline = pos_avg[pos]
                allocation = target_allocation.get(pos, 0.05)
                
                # Math: (Player TI / Pos Avg TI) * Target Allocation % * Remaining Budget
                bid_calc = (player["ti_score"] / baseline) * allocation * rem_budget
                recommended_bid = round(bid_calc)
                
                # Cannot exceed absolute max capacity
                player["auction_max_bid"] = min(recommended_bid, absolute_max_bid) if recommended_bid > 0 else 1

        # 5. Sort Board: Preferred clear players first, highest TI Score descending
        def sort_key(x):
            # Sort penalty: Blocked = 0, Warning = 1, Clear = 2
            status_weight = 2
            if x["bye_status"] == "BLOCKED": status_weight = 0
            elif x["bye_status"] == "WARNING": status_weight = 1
            return (status_weight, x["ti_score"])

        available_players.sort(key=sort_key, reverse=True)

        return {
            "draft_state": draft_state,
            "my_roster_byes": my_roster_byes,
            "board": available_players
        }
    finally:
        await conn.close()