import os
import asyncpg
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_amon_ra")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def update_amon_ra():
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        # 1. Inspect any records containing 'St' and 'Brown' or 'Amon'
        rows = await conn.fetch("""
            SELECT player_id, player_name, position, team_abbr 
            FROM player_ti 
            WHERE player_name ILIKE '%St%Brown%' 
               OR player_name ILIKE '%Amon%';
        """)
        
        logger.info("Current records matching pattern:")
        for r in rows:
            logger.info(f"ID: {r['player_id']} | Name: '{r['player_name']}' | Pos: {r['position']} | Team: {r['team_abbr']}")

        # 2. Update Amon-Ra St. Brown specifically
        result = await conn.execute("""
            UPDATE player_ti 
            SET player_name = 'Amon-Ra St. Brown' 
            WHERE (player_name ILIKE '%St%Brown%' OR player_name ILIKE '%Amon%')
              AND position = 'WR'
              AND (team_abbr = 'DET' OR player_name ILIKE 'A.%');
        """)
        
        logger.info(f"Update operation status: {result}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_amon_ra())