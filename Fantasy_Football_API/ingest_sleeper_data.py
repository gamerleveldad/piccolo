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
        # Ensure all metadata columns exist in player_ti before attempting updates
        await conn.execute("""
            ALTER TABLE player_ti 
            ADD COLUMN IF NOT EXISTS age INT,
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
        logger.info("Verified player_ti table schema for Sleeper metadata.")

        # Update query inside sync_sleeper_to_db() in ingest_sleeper_data.py
        update_query = """
            UPDATE player_ti SET
                player_name = $1,
                age = $2,
                practice_participation = $3,
                depth_chart_position = $4,
                status = $5,
                depth_chart_order = $6,
                years_exp = $7,
                fantasy_positions = $8,
                practice_description = $9,
                injury_body_part = $10,
                search_rank = $11,
                sleeper_id = $12,
                espn_id = $13,
                yahoo_id = $14,
                sportradar_id = $15,
                rotowire_id = $16
            WHERE player_id = $17;
        """
        
        updated_count = 0
        for sleeper_id, p in players_data.items():
            gsis_id = p.get("gsis_id")
            if not gsis_id:
                continue
                
            full_name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            f_pos = p.get("fantasy_positions")
            fantasy_positions_str = ",".join(f_pos) if isinstance(f_pos, list) else None
            
            result = await conn.execute(
                update_query,
                full_name, # $1
                p.get("age"), # $2
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
                gsis_id # $17
            )
            
            if result != "UPDATE 0":
                updated_count += 1

        logger.info(f"Successfully enriched {updated_count} players with Sleeper metadata.")
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(sync_sleeper_to_db())