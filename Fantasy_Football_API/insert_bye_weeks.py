import os
import asyncpg
import asyncio

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

# 2026 NFL Bye Weeks mapped by official team abbreviations
BYE_WEEKS = {
    5: ['KC', 'CAR'],
    6: ['CIN', 'MIA', 'DET', 'MIN'],
    7: ['BUF', 'JAX', 'LAC', 'WAS'],
    8: ['HOU', 'NO', 'NYG', 'SF'],
    9: ['PIT', 'TEN'],
    10: ['CHI', 'DEN', 'PHI', 'TB'],
    11: ['ATL', 'CLE', 'GB', 'LAR', 'NE', 'SEA'],
    13: ['BAL', 'IND', 'LV', 'NYJ'],
    14: ['ARI', 'DAL']
}

async def update_bye_weeks():
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)
    try:
        updated = 0
        for week, teams in BYE_WEEKS.items():
            for team in teams:
                # Update all players matching the team abbreviation
                res = await conn.execute(
                    "UPDATE player_ti SET bye_week = $1 WHERE team_abbr = $2", 
                    week, team
                )
                if res.startswith("UPDATE"):
                    count = int(res.split(" ")[1])
                    updated += count
                    
        print(f"Successfully mapped {updated} players to their 2026 bye weeks.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_bye_weeks())