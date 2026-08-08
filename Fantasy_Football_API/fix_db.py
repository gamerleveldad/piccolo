import os
import asyncpg
import asyncio

async def fix_db():
    db_url = f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:{os.getenv('POSTGRES_PASSWORD', 'password')}@{os.getenv('POSTGRES_HOST', 'postgres_db')}:5432/{os.getenv('POSTGRES_DB', 'postgres')}"
    conn = await asyncpg.connect(db_url)
    
    # PostgreSQL explicitly supports 'NaN' strings to match NaN float values
    result = await conn.execute("UPDATE player_ti SET projected_points = 0.0 WHERE projected_points = 'NaN'")
    print(f"Cleanup complete: {result}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_db())