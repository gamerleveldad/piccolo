import os
import asyncpg
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("name_update_fallback")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def update_names_fallback():
    url = "https://api.sleeper.app/v1/players/nfl"
    logger.info("Fetching Sleeper metadata for fallback matching...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            players_data = await resp.json() if resp.status == 200 else {}

    if not players_data:
        logger.error("Failed to fetch Sleeper data.")
        return

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        # Fetch players that still have a period in their name
        db_players = await conn.fetch("SELECT player_id, player_name, position, team_abbr FROM player_ti WHERE player_name LIKE '%.%'")
        
        updated_count = 0
        update_query = "UPDATE player_ti SET player_name = $1 WHERE player_id = $2;"

        for db_p in db_players:
            pid = db_p["player_id"]
            db_name = db_p["player_name"]
            db_pos = db_p["position"]
            db_team = db_p["team_abbr"]
            
            parts = db_name.split('.')
            if len(parts) != 2:
                continue
                
            first_initial = parts[0].strip().lower()
            last_name = parts[1].strip().lower()
            
            # Remove punctuation to ensure "St. Brown" or "Ja'Marr" matches cleanly
            clean_db_last = last_name.replace("'", "").replace(" ", "").replace("-", "")
            
            possible_matches = []
            
            for sleeper_id, sp in players_data.items():
                # Safety net: Use ( ... or "" ) to catch explicit None/null values from the API
                sp_first = (sp.get("first_name") or "").lower()
                sp_last = (sp.get("last_name") or "").lower()
                sp_pos = sp.get("position") or ""
                sp_status = (sp.get("status") or "").lower()
                
                clean_sp_last = sp_last.replace("'", "").replace(" ", "").replace("-", "")
                
                if sp_first.startswith(first_initial) and clean_sp_last == clean_db_last and sp_pos == db_pos:
                    full = sp.get("full_name") or f"{sp.get('first_name') or ''} {sp.get('last_name') or ''}".strip()
                    possible_matches.append({
                        "name": full,
                        "status": sp_status,
                        "team": sp.get("team") or ""
                    })
            
            match_found = None
            if len(possible_matches) == 1:
                match_found = possible_matches[0]["name"]
            elif len(possible_matches) > 1:
                # Collision handler (e.g. Jamaal Williams vs Javonte Williams)
                active_matches = [m for m in possible_matches if m["status"] == "active"]
                if len(active_matches) == 1:
                    match_found = active_matches[0]["name"]
                elif len(active_matches) > 1:
                    team_matches = [m for m in active_matches if m["team"] == db_team]
                    if len(team_matches) > 0:
                        match_found = team_matches[0]["name"]
                    else:
                        match_found = active_matches[0]["name"]
                else:
                    match_found = possible_matches[0]["name"]
                    
            if match_found:
                result = await conn.execute(update_query, match_found, pid)
                if result != "UPDATE 0":
                    updated_count += 1

        logger.info(f"Fallback successfully converted {updated_count} players using name and position matching.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_names_fallback())