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
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DB_NAME = "database.db"

def call_gemini_with_retry(contents, model='gemini-3.5-flash', max_retries=3, initial_delay=60):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except APIError as e:
            if e.code in [503, 429] and attempt < max_retries - 1:
                print(f"API busy ({e.code}). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise e

def search_youtube_trailers(game_title):
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY missing.")
        return []
        
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": f"{game_title} official trailer",
        "type": "video",
        "maxResults": 5,
        "key": YOUTUBE_API_KEY
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = []
        for item in response.json().get("items", []):
            snippet = item.get("snippet", {})
            results.append({
                "video_title": snippet.get("title"),
                "channel_name": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId")
            })
        return results
    else:
        print(f"YouTube API Error: {response.status_code}")
        return []

def agentic_channel_extraction(game_title, search_results):
    prompt = f"""
    You are a video game industry data agent.
    The user wants to track official YouTube updates for the game "{game_title}".
    
    Here are the top 5 search results for trailers:
    {json.dumps(search_results, indent=2)}
    
    Your Task:
    Identify the official publisher or developer channel from this list. 
    - Favor channels owned by the publisher (e.g., Nintendo, PlayStation, Square Enix, EA) or the specific development studio.
    - REJECT press channels (e.g., IGN, GameSpot), reaction channels, or fan uploads.
    - If no official channel is in the list, return null.
    
    Output ONLY a valid JSON object:
    {{
       "official_channel_found": true or false,
       "channel_name": "The name of the official channel, or null",
       "channel_id": "The exact channel_id, or null"
    }}
    """
    
    response = call_gemini_with_retry(contents=prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except (json.JSONDecodeError, AttributeError):
        return {"official_channel_found": False, "channel_name": None, "channel_id": None}

def update_database():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, title FROM games WHERE youtube_channel_id IS NULL OR youtube_channel_id = ''")
    games_to_update = c.fetchall()
    
    if not games_to_update:
        print("All games already have YouTube channels assigned.")
        conn.close()
        return

    for game_id, title in games_to_update:
        print(f"Hunting for official channel: {title}...")
        video_results = search_youtube_trailers(title)
        
        if not video_results:
            print("No video results found. Skipping.")
            continue
            
        metadata = agentic_channel_extraction(title, video_results)
        
        if metadata and metadata.get("official_channel_found"):
            c.execute(
                "UPDATE games SET youtube_channel_id = ? WHERE id = ?",
                (metadata['channel_id'], game_id)
            )
            conn.commit()
            print(f"  -> Linked to: {metadata['channel_name']} ({metadata['channel_id']})")
        else:
            print(f"  -> No official publisher channel identified in top results.")
            
    conn.close()
    print("\nDatabase update complete.")

if __name__ == "__main__":
    update_database()