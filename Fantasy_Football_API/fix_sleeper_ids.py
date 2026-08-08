# Fantasy_Football_API/fix_sleeper_ids.py
import os
import asyncpg
import aiohttp
import asyncio

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def fix_sleeper_ids():
    url = "https://api.sleeper.app/v1/players/nfl"
    print("Fetching full Sleeper player database...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            players_data = await resp.json() if resp.status == 200 else {}

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        updated = 0
        update_query = "UPDATE player_ti SET sleeper_id = $1 WHERE player_id = $2 OR LOWER(player_name) = LOWER($3);"

        for sleeper_id, p in players_data.items():
            full_name = p.get("full_name") or f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip()
            gsis_id = str(p.get("gsis_id")) if p.get("gsis_id") else None

            if not full_name:
                continue

            res = await conn.execute(update_query, str(sleeper_id), gsis_id, full_name)
            if res != "UPDATE 0":
                updated += 1

        print(f"Successfully mapped Sleeper IDs for {updated} records.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_sleeper_ids())