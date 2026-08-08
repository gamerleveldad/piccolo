import os
import asyncpg
import aiohttp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sleeper_ingest")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def fetch_sleeper_players():
    url = "https://api.sleeper.app/v1/players/nfl"
    logger.info("Fetching All Players from Sleeper API (this may take a moment)...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.error(f"API Error: HTTP {resp.status}")
                return {}

async def sync_sleeper_to_db():
    players_data = await fetch_sleeper_players()
    if not players_data:
        return

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)
    
    try:
        update_query = """
            UPDATE player_ti SET
                age = $1,
                practice_participation = $2,
                depth_chart_position = $3,
                status = $4,
                depth_chart_order = $5,
                years_exp = $6,
                fantasy_positions = $7,
                practice_description = $8,
                injury_body_part = $9,
                search_rank = $10,
                sleeper_id = $11,
                espn_id = $12,
                yahoo_id = $13,
                sportradar_id = $14,
                rotowire_id = $15
            WHERE player_id = $16;
        """
        
        updated_count = 0
        for sleeper_id, p in players_data.items():
            # Match the NFLverse player_id format
            gsis_id = p.get("gsis_id")
            if not gsis_id:
                continue
                
            f_pos = p.get("fantasy_positions")
            fantasy_positions_str = ",".join(f_pos) if isinstance(f_pos, list) else None
            
            result = await conn.execute(
                update_query,
                p.get("age"),
                p.get("practice_participation"),
                p.get("depth_chart_position"),
                p.get("status"),
                p.get("depth_chart_order"),
                p.get("years_exp"),
                fantasy_positions_str,
                p.get("practice_description"),
                p.get("injury_body_part"),
                p.get("search_rank"),
                str(sleeper_id),
                str(p.get("espn_id")) if p.get("espn_id") else None,
                str(p.get("yahoo_id")) if p.get("yahoo_id") else None,
                str(p.get("sportradar_id")) if p.get("sportradar_id") else None,
                str(p.get("rotowire_id")) if p.get("rotowire_id") else None,
                gsis_id
            )
            
            if result != "UPDATE 0":
                updated_count += 1

        logger.info(f"Successfully enriched {updated_count} players with Sleeper metadata.")
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(sync_sleeper_to_db())