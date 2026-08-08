import os
import asyncpg
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sleeper_ingest")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def fetch_sleeper_players():
    url = "https://api.sleeper.app/v1/players/nfl"
    logger.info("Fetching All Players from Sleeper API...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json() if resp.status == 200 else {}

async def sync_sleeper_to_db():
    players_data = await fetch_sleeper_players()
    if not players_data:
        return

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        # Guarantee all required metadata columns exist in player_ti
        await conn.execute("""
            ALTER TABLE player_ti 
            ADD COLUMN IF NOT EXISTS age INT,
            ADD COLUMN IF NOT EXISTS bye_week INT,
            ADD COLUMN IF NOT EXISTS practice_participation VARCHAR(50),
            ADD COLUMN IF NOT EXISTS depth_chart_position VARCHAR(20),
            ADD COLUMN IF NOT EXISTS status VARCHAR(50),
            ADD COLUMN IF NOT EXISTS depth_chart_order INT,
            ADD COLUMN IF NOT EXISTS years_exp INT,
            ADD COLUMN IF NOT EXISTS fantasy_positions VARCHAR(50),
            ADD COLUMN IF NOT EXISTS practice_description VARCHAR(255),
            ADD COLUMN IF NOT EXISTS injury_body_part VARCHAR(50),
            ADD COLUMN IF NOT EXISTS search_rank INT,
            ADD COLUMN IF NOT EXISTS sleeper_id VARCHAR(50);
        """)
        logger.info("Verified player_ti table schema for Sleeper metadata.")

        # Match by GSIS ID first
        update_by_id = """
            UPDATE player_ti SET
                age = $1,
                bye_week = $2,
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
                team_abbr = $13      -- NEW
            WHERE player_id = $14;   -- Shifted to 14
        """

        # Fallback match by Name + Position
        update_by_name = """
            UPDATE player_ti SET
                age = $1,
                bye_week = $2,
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
                team_abbr = $13      -- NEW
            WHERE LOWER(player_name) = LOWER($14) AND position = $15; -- Shifted to 14 & 15
        """

        updated_count = 0
        for sleeper_id, p in players_data.items():
            full_name = p.get("full_name") or f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip()
            pos = p.get("position")
            if not full_name:
                continue

            f_pos = p.get("fantasy_positions")
            fantasy_positions_str = ",".join(f_pos) if isinstance(f_pos, list) else None

            params = (
                p.get("age"),
                p.get("bye_week"),
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
                p.get("team")
            )

            # Attempt 1: Match by GSIS ID
            gsis_id = p.get("gsis_id")
            matched = False
            if gsis_id:
                res = await conn.execute(update_by_id, *params, str(gsis_id)) # str(gsis_id) is now $14
                if res != "UPDATE 0":
                    matched = True
                    updated_count += 1

            # Attempt 2: Fallback match by Name + Position
            if not matched and pos:
                res = await conn.execute(update_by_name, *params, full_name, pos) # full_name is $14, pos is $15
                if res != "UPDATE 0":
                    updated_count += 1

        logger.info(f"Enriched {updated_count} players with Sleeper metadata (ages, depth charts, status).")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(sync_sleeper_to_db())