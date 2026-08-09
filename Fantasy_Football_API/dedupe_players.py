import os
import asyncpg
import asyncio

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def deduplicate_database():
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)
    try:
        # Find all names and positions that have more than 1 entry
        duplicates = await conn.fetch("""
            SELECT LOWER(player_name) as clean_name, position, COUNT(*) 
            FROM player_ti 
            GROUP BY LOWER(player_name), position 
            HAVING COUNT(*) > 1;
        """)

        deleted_count = 0
        for d in duplicates:
            c_name = d["clean_name"]
            pos = d["position"]

            rows = await conn.fetch("""
                SELECT player_id, sleeper_id, projected_points, age, depth_chart_order 
                FROM player_ti 
                WHERE LOWER(player_name) = $1 AND position = $2
                ORDER BY sleeper_id NULLS LAST, projected_points DESC NULLS LAST;
            """, c_name, pos)

            # Keep the first row (most populated record) and remove the rest
            keep_id = rows[0]["player_id"]
            remove_ids = [r["player_id"] for r in rows[1:]]

            for r_id in remove_ids:
                await conn.execute("DELETE FROM player_ti WHERE player_id = $1;", r_id)
                deleted_count += 1

        print(f"Deduplication complete. Removed {deleted_count} duplicate player records.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(deduplicate_database())