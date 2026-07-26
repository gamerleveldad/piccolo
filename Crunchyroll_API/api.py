from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST"),
        database=os.environ.get("POSTGRES_DB"),
        user=os.environ.get("POSTGRES_USER"),
        password=os.environ.get("POSTGRES_PASSWORD")
    )

# --- Pydantic Models for Data Validation ---
class HistoryItem(BaseModel):
    anime_name: str
    status: str
    user_rating: str
    current_episode: int = 0
    total_episodes: int = 0

class HistoryUpdate(BaseModel):
    status: str
    user_rating: str
    current_episode: int
    total_episodes: int

# --- Schedule Routes (Read-Only) ---
@app.get("/api/schedule")
def get_schedule():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anime_name, expected_weekday, last_seen_date FROM watchlist_schedule")
    schedule = [{"name": row[0], "weekday": row[1], "last_seen": row[2]} for row in cursor.fetchall()]
    conn.close()
    return schedule

# --- History Routes (CRUD) ---
@app.get("/api/history")
def get_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anime_name, status, user_rating FROM watch_history ORDER BY anime_name")
    history = [{"name": row[0], "status": row[1], "rating": row[2]} for row in cursor.fetchall()]
    conn.close()
    return history

@app.post("/api/history")
def add_history(item: HistoryItem):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO watch_history (anime_name, status, user_rating, current_episode, total_episodes)
            VALUES (%s, %s, %s, %s, %s)
        ''', (item.anime_name, item.status, item.user_rating, item.current_episode, item.total_episodes))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Anime already exists in history.")
    finally:
        conn.close()
    return {"message": "Added successfully"}

@app.put("/api/history/{anime_name}")
def update_history(anime_name: str, item: HistoryUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE watch_history 
        SET status = %s, user_rating = %s, current_episode = %s, total_episodes = %s
        WHERE anime_name = %s
    ''', (item.status, item.user_rating, item.current_episode, item.total_episodes, anime_name))
    conn.commit()
    conn.close()
    return {"message": "Updated successfully"}

@app.delete("/api/history/{anime_name}")
def delete_history(anime_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watch_history WHERE anime_name = %s", (anime_name,))
    conn.commit()
    conn.close()
    return {"message": "Deleted successfully"}

@app.get("/api/progress")
def get_progress():
    """Dedicated endpoint for rendering dashboard progress bars."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT anime_name, current_episode, total_episodes 
        FROM watch_history 
        WHERE status = 'Watching' 
        ORDER BY anime_name
    ''')
    progress = [{"name": row[0], "current": row[1], "total": row[2]} for row in cursor.fetchall()]
    conn.close()
    return progress