import os
import asyncpg
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("name_update")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def update_names_to_full():
    url = "https://api.sleeper.app/v1/players/nfl"
    logger.info("Fetching Sleeper metadata to map full player names...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            players_data = await resp.json() if resp.status == 200 else {}

    if not players_data:
        logger.error("Failed to fetch Sleeper data. Aborting.")
        return

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        updated_count = 0
        update_query = "UPDATE player_ti SET player_name = $1 WHERE player_id = $2;"

        for sleeper_id, p in players_data.items():
            gsis_id = p.get("gsis_id")
            full_name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            
            if not gsis_id or not full_name:
                continue

            result = await conn.execute(update_query, full_name, gsis_id)
            if result != "UPDATE 0":
                updated_count += 1

        logger.info(f"Successfully converted {updated_count} players to full names in PostgreSQL.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_names_to_full())