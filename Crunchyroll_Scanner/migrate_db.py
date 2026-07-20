import sqlite3
import psycopg2
import os

print("🚀 Starting Database Migration...")

# Connect to your old local SQLite file (Mapped via Docker Volume)
sqlite_conn = sqlite3.connect('/app/anime_tracker.db')
sqlite_cursor = sqlite_conn.cursor()

# Connect to your new PostgreSQL Container
pg_conn = psycopg2.connect(
    host=os.environ.get("POSTGRES_HOST", "postgres_db"),
    database=os.environ.get("POSTGRES_DB", "crunchyroll_db"),
    user=os.environ.get("POSTGRES_USER"),
    password=os.environ.get("POSTGRES_PASSWORD")
)
pg_cursor = pg_conn.cursor()

# Migrate the watch_history table
print("📦 Moving watch_history data...")
sqlite_cursor.execute("SELECT anime_name, status, user_rating FROM watch_history")
for row in sqlite_cursor.fetchall():
    pg_cursor.execute('''
        INSERT INTO watch_history (anime_name, status, user_rating)
        VALUES (%s, %s, %s)
        ON CONFLICT (anime_name) DO NOTHING
    ''', row)

# Migrate the watchlist_schedule table
print("📅 Moving watchlist_schedule data...")
sqlite_cursor.execute("SELECT anime_name, expected_weekday, last_seen_date FROM watchlist_schedule")
for row in sqlite_cursor.fetchall():
    pg_cursor.execute('''
        INSERT INTO watchlist_schedule (anime_name, expected_weekday, last_seen_date)
        VALUES (%s, %s, %s)
        ON CONFLICT (anime_name) DO NOTHING
    ''', row)

# Save changes and close out
pg_conn.commit()
sqlite_conn.close()
pg_conn.close()

print("✅ Migration Complete!")