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
                projected_points FLOAT,
                historical_avg_points FLOAT,
                consistency_score FLOAT,
                team_synergy_multiplier FLOAT,
                ti_score FLOAT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
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
                position=p.get("position") or "WR"
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


@app.get("/api/ti/board/{board_type}")
async def get_custom_board(board_type: str):
    """
    Fetches the draft board for a specific board type (e.g., 'standard', 'dynasty', 'chopped').
    Merges calculated TI scores with persistent manual rank overrides.
    """
    conn = await get_db_connection()
    try:
        # Fetch team unit rankings
        team_rows = await conn.fetch("SELECT * FROM team_unit_rankings")
        team_ranks_map = {r["team_abbr"]: dict(r) for r in team_rows}

        # Fetch base player metrics
        player_rows = await conn.fetch("SELECT * FROM player_ti")

        # Fetch custom manual board order overrides for this specific board type
        order_rows = await conn.fetch(
            "SELECT player_id, manual_rank, is_pinned FROM board_player_order WHERE board_type = $1",
            board_type
        )
        custom_order_map = {r["player_id"]: (r["manual_rank"], r["is_pinned"]) for r in order_rows}

        draft_board = []
        for p in player_rows:
            player_team = p.get("team_abbr")
            unit_ranks = team_ranks_map.get(player_team, {})

            # Calculate raw TI Score details
            score_data = calculate_ti_score(
                projected_pts=p.get("projected_points") or 0.0,
                historical_pts=p.get("historical_avg_points") or 0.0,
                coefficient_of_variation=p.get("consistency_score"),
                team_ranks=unit_ranks,
                position=p.get("position") or "WR"
            )

            p_id = p["player_id"]
            
            # Determine rank: use custom manual rank if pinned, otherwise default to TI score calculation
            if p_id in custom_order_map:
                effective_rank = custom_order_map[p_id][0]
                is_pinned = custom_order_map[p_id][1]
            else:
                # Higher TI scores should rank earlier (lower rank number)
                effective_rank = 1000.0 - score_data["ti_score"]
                is_pinned = False

            draft_board.append({
                "player_id": p_id,
                "player_name": p["player_name"],
                "position": p["position"],
                "team": player_team,
                "effective_rank": effective_rank,
                "is_pinned": is_pinned,
                "ti_score": score_data["ti_score"],
                "details": score_data
            })

        # Sort board by effective rank ascending
        draft_board.sort(key=lambda x: x["effective_rank"])

        # Normalize display index for easy UI rendering
        for idx, item in enumerate(draft_board, start=1):
            item["display_rank"] = idx

        return {
            "board_type": board_type,
            "count": len(draft_board),
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