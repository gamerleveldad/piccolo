# Fantasy_Football_API/ingest_nfl_data.py

import os
import asyncpg
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nfl_ingest")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

async def fetch_and_process_historical_data(seasons=[2023, 2024, 2025]):
    """
    Downloads weekly NFL player data directly from the nflverse GitHub releases.
    Computes averages, CV, and extracts the most recent team and position.
    """
    logger.info(f"Downloading weekly data for seasons: {seasons}")
    
    dfs = []
    for year in seasons:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_{year}.parquet"
        try:
            logger.info(f"Fetching {year} data...")
            df_year = pd.read_parquet(url, engine='auto')
            dfs.append(df_year)
        except Exception as e:
            logger.error(f"Failed to fetch {year} data: {e}")
            
    if not dfs:
        raise ValueError("Could not fetch any historical data.")

    weekly_df = pd.concat(dfs, ignore_index=True)
    weekly_df = weekly_df[weekly_df['fantasy_points_ppr'] > 0]

    if 'player_name' not in weekly_df.columns and 'player_display_name' in weekly_df.columns:
        weekly_df['player_name'] = weekly_df['player_display_name']

    # --- NEW: Extract the most recent team and position for each player ---
    # Sort chronologically to ensure the 'last' record is their most recent team
    weekly_df = weekly_df.sort_values(by=['season', 'week'])
    latest_info = weekly_df.drop_duplicates(subset=['player_id'], keep='last')[['player_id', 'recent_team', 'position']]

    # Group by player to compute mathematical averages
    player_stats = weekly_df.groupby(['player_id', 'player_name']).agg(
        total_games=('fantasy_points_ppr', 'count'),
        avg_ppg=('fantasy_points_ppr', 'mean'),
        std_dev=('fantasy_points_ppr', 'std')
    ).reset_index()

    # Calculate Coefficient of Variation (std_dev / mean)
    player_stats['cv'] = player_stats['std_dev'] / player_stats['avg_ppg']
    player_stats['cv'] = player_stats['cv'].fillna(0.40)

    # --- NEW: Merge the recent team and position back into the final dataframe ---
    player_stats = player_stats.merge(latest_info, on='player_id', how='left')

    logger.info(f"Processed {len(player_stats)} historical player records.")
    return player_stats

async def sync_historicals_to_db():
    """Connects to PostgreSQL and upserts calculated stats and metadata."""
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)
    
    try:
        stats_df = await fetch_and_process_historical_data()
        
        # --- NEW: Added position and team_abbr to the UPSERT query ---
        upsert_query = """
            INSERT INTO player_ti (
                player_id, player_name, position, team_abbr, historical_avg_points, consistency_score
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (player_id) DO UPDATE SET
                position = EXCLUDED.position,
                team_abbr = EXCLUDED.team_abbr,
                historical_avg_points = EXCLUDED.historical_avg_points,
                consistency_score = EXCLUDED.consistency_score,
                updated_at = CURRENT_TIMESTAMP;
        """

        for _, row in stats_df.iterrows():
            await conn.execute(
                upsert_query,
                str(row['player_id']),
                str(row['player_name']),
                str(row['position']) if pd.notna(row['position']) else 'UNK',
                str(row['recent_team']) if pd.notna(row['recent_team']) else 'FA',
                float(row['avg_ppg']),
                float(row['cv'])
            )
        logger.info("Database historical sync complete.")
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(sync_historicals_to_db())