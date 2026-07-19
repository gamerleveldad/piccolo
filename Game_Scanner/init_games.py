import os
import sqlite3
import requests
import json
import time
from google.genai import Client
from google.genai.errors import APIError
from dotenv import load_dotenv

load_dotenv()
client = Client()
RAWG_API_KEY = os.getenv("RAWG_API_KEY")
DB_NAME = "database.db"

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
    # The params dictionary automatically handles URL encoding for spaces and special characters
    payload = {
        "search": query,
        "key": RAWG_API_KEY
    }
    
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
    1. Look for an exact semantic match. Do NOT assume a completely different game with a similar word is a match (e.g., Do NOT match "Brave New Wonders" to "Kaptain Brawe").
    2. If the game is an upcoming release, rumored, or missing entirely from the search results, you MUST return a null match.
    
    Output ONLY a valid JSON object (no markdown, no backticks):
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

def add_smart_game(game_name, platform):
    print(f"Searching RAWG for '{game_name}'...")
    raw_results = search_rawg(game_name)
    metadata = agentic_metadata_extraction(game_name, platform, raw_results)
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        if metadata and metadata.get("matched"):
            # Clean match found
            c.execute(
                "INSERT INTO games (title, rawg_id, release_date, igdb_id, youtube_channel_id) VALUES (?, ?, ?, ?, ?)",
                (metadata['title'], metadata['rawg_id'], metadata['release_date'], "", "")
            )
            print(f"Successfully tracked via RAWG: {metadata['title']} (ID: {metadata['rawg_id']})")
        else:
            # Fallback for upcoming/rumored games not yet indexed
            c.execute(
                "INSERT INTO games (title, rawg_id, release_date, igdb_id, youtube_channel_id) VALUES (?, ?, ?, ?, ?)",
                (game_name, "custom_search", "Upcoming / TBD", "", "")
            )
            print(f"RAWG entry missing. Saved '{game_name}' as a Custom Search fallback tracking target.")
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Error: '{game_name}' is already being tracked.")
    finally:
        conn.close()

if __name__ == "__main__":
    # Ensure updated schema exists
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY,
                    title TEXT UNIQUE,
                    igdb_id TEXT,
                    rawg_id TEXT,
                    youtube_channel_id TEXT,
                    release_date TEXT,
                    last_scanned TIMESTAMP
                 )''')
    conn.close()

    # Clear out any old bad data before running new ones
    # add_smart_game("Brave New Wonders", "PC")
    # Initialize your specific targets
    add_smart_game("Fire Emblem Fortunes Weave", "Nintendo Switch 2")
    add_smart_game("Brave New Wonders", "PC")
    add_smart_game("Orbitals", "Nintendo Switch 2")
    add_smart_game("Star Wars Zero Company", "Playstation 5")