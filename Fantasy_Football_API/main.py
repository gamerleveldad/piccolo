import os
import aiohttp
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fantasy_api")

app = FastAPI(title="Sleeper Fantasy Football API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SLEEPER_LEAGUE_ID = os.getenv("SLEEPER_LEAGUE_ID", "1360812344053071872")

@app.get("/health")
async def health_check():
    return {"status": "up"}

@app.get("/api/sleeper")
async def get_sleeper_matchups():
    url_league = f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_league) as resp:
                if resp.status != 200: 
                    return {"mode": "disabled"}
                league_data = await resp.json()
                
            if league_data.get("status") == "pre_draft":
                url_drafts = f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/drafts"
                async with session.get(url_drafts) as d_resp:
                    drafts = await d_resp.json()
                    if drafts:
                        return {
                            "mode": "draft",
                            "name": league_data.get("name"),
                            "draft_start": drafts[0].get("start_time")
                        }

            current_week = league_data.get("settings", {}).get("leg", 1)
            
            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/users") as u_resp:
                users = await u_resp.json()
                user_map = {u['user_id']: u.get('metadata', {}).get('team_name', u['display_name']) for u in users}
                
            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/rosters") as r_resp:
                rosters = await r_resp.json()
                roster_to_owner = {r['roster_id']: user_map.get(r['owner_id'], f"Team {r['roster_id']}") for r in rosters}

            async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/matchups/{current_week}") as m_resp:
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