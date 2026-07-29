from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import errors
import os
from google.genai import Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Drive database paths via environmental flags for clean volume persistence
DB_NAME = os.getenv("DB_PATH", "database.db")
RAWG_API_KEY = os.getenv("RAWG_API_KEY")
client = Client()

class NewGameRequest(BaseModel):
    title: str
    platform: str
class UpdateDateRequest(BaseModel):
    release_date: str
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    title TEXT UNIQUE,
                    igdb_id TEXT,
                    rawg_id TEXT,
                    youtube_channel_id TEXT,
                    release_date TEXT,
                    last_scanned TIMESTAMP
                 )''')
    conn.commit()
    conn.close()
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres_db"),
        database=os.getenv("POSTGRES_DB", "game_scanner_db"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )
@app.on_event("startup")
def startup_event():
    init_db()

def call_gemini_with_retry(contents, model='gemini-3.5-flash', max_retries=3, initial_delay=60):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except APIError as e:
            if e.code in [503, 429] and attempt < max_retries - 1:
                print(f"Gemini API busy ({e.code}). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise e

def search_rawg(query):
    if not RAWG_API_KEY:
        return []
    url = "https://api.rawg.io/api/games"
    payload = {"search": query, "key": RAWG_API_KEY}
    response = requests.get(url, params=payload)
    if response.status_code == 200:
        return response.json().get("results", [])[:5]
    return []

def agentic_metadata_extraction(target_game, target_platform, search_results):
    prompt = f"""
    You are an intelligent data extraction agent. 
    The user wants to track the game "{target_game}" specifically for the "{target_platform}" platform.
    
    Here are the top 5 search results from the RAWG API:
    {json.dumps(search_results, indent=2)}
    
    STRICT RULES:
    1. Look for a strong semantic match. Subtitles, missing colons, or minor variations are acceptable.
    2. Do NOT match completely unrelated games.
    3. PLATFORM VETO: If the user requested a modern console (e.g., Switch 2) and the search result is clearly an older, unrelated game exclusive to a different platform (like an old PC-only game with a similar name), you MUST REJECT IT.
    4. If it is a valid match, extract it. If rejected or missing entirely, return a null match.
    
    Output ONLY a valid JSON object:
    {{
       "matched": true or false,
       "title": "The exact title from the data if matched, otherwise null",
       "rawg_id": integer ID if matched, otherwise null,
       "release_date": "YYYY-MM-DD if available, otherwise null"
    }}
    """
    
    response = call_gemini_with_retry(contents=prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except (json.JSONDecodeError, AttributeError):
        return {"matched": False, "title": None, "rawg_id": None, "release_date": None}

@app.get("/games")
def get_games():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, rawg_id, release_date FROM games")
    games = [{"id": row[0], "title": row[1], "rawg_id": row[2], "release_date": row[3]} for row in c.fetchall()]
    conn.close()
    return games

@app.delete("/games/{game_id}")
def delete_game(game_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM games WHERE id = %s", (game_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Target terminated."}

@app.post("/games/add")
def add_game(request: NewGameRequest):
    print(f"\n--- NEW TRACKING REQUEST ---")
    print(f"Target: {request.title} | Platform: {request.platform}")
    
    raw_results = search_rawg(request.title)
    metadata = agentic_metadata_extraction(request.title, request.platform, raw_results)
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        if metadata and metadata.get("matched"):
            c.execute(
                "INSERT INTO games (title, rawg_id, release_date, igdb_id, youtube_channel_id) VALUES (%s, %s, %s, %s, %s)",
                (metadata['title'], metadata['rawg_id'], metadata['release_date'], "", "")
            )
            message = f"Successfully tracked: {metadata['title']}"
        else:
            c.execute(
                "INSERT INTO games (title, rawg_id, release_date, igdb_id, youtube_channel_id) VALUES (%s, %s, %s, %s, %s)",
                (request.title, "custom_search", "Upcoming / TBD", "", "")
            )
            message = f"RAWG entry missing/rejected. Saved '{request.title}' as Custom Search."
        conn.commit()
        return {"status": "success", "message": message}
    except psycopg2.errors.UniqueViolation:
        conn.rollback() # Critical for Postgres to reset the transaction block
        return {"status": "error", "message": f"'{request.title}' is already active."}
    finally:
        conn.close()

@app.get("/games/upcoming")
def get_upcoming_games():
    """
    Returns a list of tracked games releasing within the next 7 days.
    Accessible internally by other microservices on the Docker network.
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    # Calculate today and exactly 7 days from now
    today = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Query logic: 
    # 1. length(release_date) = 10 ensures we only check valid YYYY-MM-DD strings 
    #    (ignoring "Upcoming / TBD").
    # 2. String comparison efficiently filters the timeframe.
    query = """
        SELECT id, title, rawg_id, release_date 
        FROM games 
        WHERE length(release_date) = 10 
          AND release_date >= %s 
          AND release_date <= %s
        ORDER BY release_date ASC
    """
    
    c.execute(query, (today, next_week))
    
    games = [
        {"id": row[0], "title": row[1], "rawg_id": row[2], "release_date": row[3]} 
        for row in c.fetchall()
    ]
    
    conn.close()
    return games

@app.put("/games/{game_id}/date")
def update_game_date(game_id: int, request: UpdateDateRequest):
    """Allows manual updating of the release date for off-grid games."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE games SET release_date = %s WHERE id = %s", 
        (request.release_date, game_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Date manually overridden."}