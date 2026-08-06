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
    Downloads weekly NFL player data directly from the nflverse GitHub releases,
    computes 1-3 year average PPG, and calculates CV for the consistency score.
    """
    logger.info(f"Downloading weekly data for seasons: {seasons}")
    
    dfs = []
    for year in seasons:
        # Direct URL to the nflverse data release, bypassing the broken library
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
    
    # Filter out low snap / low target outlier games
    weekly_df = weekly_df[weekly_df['fantasy_points_ppr'] > 0]

    # Handle naming discrepancies across seasons (player_name vs player_display_name)
    if 'player_name' not in weekly_df.columns and 'player_display_name' in weekly_df.columns:
        weekly_df['player_name'] = weekly_df['player_display_name']

    # Group by player to compute average points and consistency (CV)
    player_stats = weekly_df.groupby(['player_id', 'player_name']).agg(
        total_games=('fantasy_points_ppr', 'count'),
        avg_ppg=('fantasy_points_ppr', 'mean'),
        std_dev=('fantasy_points_ppr', 'std')
    ).reset_index()

    # Calculate Coefficient of Variation (std_dev / mean)
    player_stats['cv'] = player_stats['std_dev'] / player_stats['avg_ppg']
    # Fill missing or NaN values for single-game samples
    player_stats['cv'] = player_stats['cv'].fillna(0.40)

    logger.info(f"Processed {len(player_stats)} historical player records.")
    return player_stats

async def sync_historicals_to_db():
    """Connects to PostgreSQL and upserts calculated historical stats."""
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)
    
    try:
        stats_df = await fetch_and_process_historical_data()
        
        upsert_query = """
            INSERT INTO player_ti (player_id, player_name, historical_avg_points, consistency_score)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (player_id) DO UPDATE SET
                historical_avg_points = EXCLUDED.historical_avg_points,
                consistency_score = EXCLUDED.consistency_score,
                updated_at = CURRENT_TIMESTAMP;
        """

        for _, row in stats_df.iterrows():
            await conn.execute(
                upsert_query,
                str(row['player_id']),
                str(row['player_name']),
                float(row['avg_ppg']),
                float(row['cv'])
            )
        logger.info("Database historical sync complete.")
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(sync_historicals_to_db())