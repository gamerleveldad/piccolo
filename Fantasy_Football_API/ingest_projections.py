import os
import asyncpg
import requests
import io
import pandas as pd
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("projections_ingest")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")

# Headers required to fetch projection pages cleanly
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

POSITIONS = ["qb", "rb", "wr", "te"]

def calculate_ppr_points(row, position):
    """
    Calculates PPR projected fantasy points from raw statistical projections.
    """
    pts = 0.0
    try:
        if position == "qb":
            passing_yds = float(str(row.get("YDS", 0)).replace(",", ""))
            passing_tds = float(row.get("TDS", 0)) if "TDS" in row else 0.0
            ints = float(row.get("INTS", 0)) if "INTS" in row else 0.0
            rushing_yds = float(str(row.get("ATT", 0)).replace(",", "")) if "ATT" in row else 0.0 # Note: handling table column alignment
            
            # Standard scoring: 1pt / 25 pass yds, 4pt pass TD, -2pt INT, 1pt / 10 rush yds, 6pt rush TD
            pts += (passing_yds / 25.0) + (passing_tds * 4.0) - (ints * 2.0)
            
        elif position in ["rb", "wr", "te"]:
            rush_yds = float(str(row.get("YDS", 0)).replace(",", "")) if "YDS" in row else 0.0
            rush_tds = float(row.get("TDS", 0)) if "TDS" in row else 0.0
            rec = float(row.get("REC", 0)) if "REC" in row else 0.0
            rec_yds = float(str(row.get("YDS.1", row.get("YDS", 0))).replace(",", ""))
            rec_tds = float(row.get("TDS.1", row.get("TDS", 0)))

            # PPR scoring: 1pt / 10 rush yds, 6pt rush TD, 1pt / rec, 1pt / 10 rec yds, 6pt rec TD
            pts += (rush_yds / 10.0) + (rush_tds * 6.0) + (rec * 1.0) + (rec_yds / 10.0) + (rec_tds * 6.0)
            
    except Exception as e:
        logger.warning(f"Error parsing row points for {position}: {e}")
        
    return round(pts, 2)


def fetch_fantasypros_projections():
    """
    Scrapes consensus projections from FantasyPros for all primary skill positions.
    """
    all_projections = []

    for pos in POSITIONS:
        url = f"https://www.fantasypros.com/nfl/projections/{pos}.php?max-results=all"
        logger.info(f"Fetching consensus projections for {pos.upper()}...")
        
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            logger.error(f"Failed to fetch projections for {pos}: HTTP {response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"id": "data"})
        
        if not table:
            logger.warning(f"No data table found for position {pos}")
            continue

        # Parse HTML table into pandas DataFrame using StringIO
        dfs = pd.read_html(io.StringIO(str(table)))
        if not dfs:
            continue
        df = dfs[0]
        
        # Flatten multi-level column headers if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                f"{col[0]}_{col[1]}" if ("Unnamed" not in str(col[0]) and str(col[0]) != "") else str(col[1])
                for col in df.columns
            ]

        # Standardize column headers
        df.columns = [str(c).upper() for c in df.columns]

        for _, row in df.iterrows():
            # Get first cell string containing player name and team
            raw_player_val = str(row.iloc[0]) if len(row) > 0 else ""
            
            if not raw_player_val or raw_player_val == "nan":
                continue

            # Extract player name (e.g., "Jalen Hurts PHI" -> "Jalen Hurts")
            name_parts = raw_player_val.split("(")[0].strip().split()
            if len(name_parts) > 1 and len(name_parts[-1]) in [2, 3] and name_parts[-1].isupper():
                player_name = " ".join(name_parts[:-1])
            else:
                player_name = " ".join(name_parts)

            # Check for fantasy points column or fallback to calculation
            proj_pts = 0.0
            found_pts = False
            for col_name in row.index:
                if "FPTS" in str(col_name).upper():
                    try:
                        proj_pts = float(row[col_name])
                        found_pts = True
                        break
                    except (ValueError, TypeError):
                        pass

            if not found_pts:
                proj_pts = calculate_ppr_points(row, pos)

            all_projections.append({
                "player_name": player_name,
                "position": pos.upper(),
                "projected_points": proj_pts
            })

    logger.info(f"Successfully scraped {len(all_projections)} player projections.")
    return all_projections


async def sync_projections_to_db():
    """
    Updates player_ti table in PostgreSQL with current season projections.
    Matches primarily on cleaned player name and position.
    """
    projections = fetch_fantasypros_projections()
    if not projections:
        logger.error("No projections were scraped. Aborting DB sync.")
        return

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    conn = await asyncpg.connect(db_url)

    try:
        # Match by player_name and position to update projected_points
        update_query = """
            UPDATE player_ti 
            SET projected_points = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE LOWER(player_name) LIKE LOWER($2)
              AND position = $3;
        """

        updated_count = 0
        for p in projections:
            # Format name pattern to handle initial formats (e.g. "J.Allen" vs "Josh Allen")
            clean_name = p["player_name"]
            name_parts = clean_name.split()
            
            if len(name_parts) >= 2:
                # Match format like "J.Allen" or full name
                short_name = f"{name_parts[0][0]}.%{name_parts[-1]}"
            else:
                short_name = f"%{clean_name}%"

            result = await conn.execute(
                update_query,
                float(p["projected_points"]),
                short_name,
                p["position"]
            )

            if result != "UPDATE 0":
                updated_count += 1

        logger.info(f"Updated projected points for {updated_count} players in database.")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(sync_projections_to_db())