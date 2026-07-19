import sqlite3
import requests
import json
import os
import time
import schedule
import threading
import sys
from google.genai import Client
from google.genai.errors import APIError
from dotenv import load_dotenv

DB_NAME = "database.db"
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
client = Client()
BATCH_SIZE = 10

def call_gemini_with_retry(contents, model='gemini-3.5-flash', max_retries=6, initial_delay=60):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception as e:
            # Safely extract the status code whether it's an APIError or a generic web exception
            error_code = getattr(e, 'code', None)
            
            # 503 (Unavailable), 500 (Server Error), 429 (Rate Limit), 504 (Gateway Timeout)
            if error_code in [503, 500, 429, 504] and attempt < max_retries - 1:
                print(f"Gemini API blocked (Error {error_code}). Retrying in {int(delay)}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                # Multiply by 1.5 instead of 2 so we don't end up waiting 20+ minutes on the last attempt
                delay *= 1.5 
            else:
                print(f"FATAL: Gemini API failed after {max_retries} attempts.")
                raise e

def get_rawg_data(rawg_id):
    if not rawg_id or rawg_id == "custom_search":
        return None
    api_key = os.getenv("RAWG_API_KEY")
    url = "https://api.rawg.io/api/games"
    response = requests.get(f"{url}/{rawg_id}", params={"key": api_key})
    if response.status_code == 200:
        data = response.json()
        return {
            "name": data.get("name"),
            "released": data.get("released"),
            "metacritic": data.get("metacritic"),
            "updated": data.get("updated"),
            "description": data.get("description_raw", "")[:800]
        }
    return None

def get_youtube_data(channel_id):
    if not channel_id:
        return None
    api_key = os.getenv("YOUTUBE_API_KEY")
    url = "https://www.googleapis.com/youtube/v3/search"
    # Query for the two most recently uploaded videos on the official channel
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "order": "date", 
        "maxResults": 2,
        "type": "video",
        "key": api_key
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        videos = []
        for item in response.json().get("items", []):
            snippet = item.get("snippet", {})
            videos.append({
                "video_title": snippet.get("title"),
                "published_at": snippet.get("publishedAt"),
                "video_url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
        return videos
    return None

def evaluate_game_batch(batch_data, scan_type):
    from datetime import datetime
    
    # Give the AI an anchor for time so it can calculate "this week" or "this month"
    today_date = datetime.now().strftime("%B %d, %Y")
    
    # Dynamically change the AI's objective based on the cron schedule
    if scan_type == "monthly":
        cadence_rules = "MONTHLY REPORT: Your primary goal is to check the 'released' date. If the game is releasing in the upcoming month, explicitly highlight it! Summarize any major overarching news from the past 30 days."
    elif scan_type == "weekly":
        cadence_rules = "WEEKLY REPORT: Your primary goal is to check the 'released' date. If the game is releasing within the next 7 days, explicitly highlight it! Summarize major news or patch notes from the past week."
    else:
        cadence_rules = "DAILY REPORT: Focus STRICTLY on breaking news for the target game. For YouTube, ONLY include videos if their 'published_at' timestamp is within the last 24 hours AND the video is explicitly about the targeted game."

    prompt = f"""
    You are a professional video game industry scanning agent. 
    Today's Date: {today_date}
    Scan Cadence: {scan_type.upper()}
    
    Data Context:
    {json.dumps(batch_data, indent=2)}
    
    Instructions:
    1. Evaluate EACH game individually against today's date.
    2. {cadence_rules}
    3. CRITICAL RELEVANCE VETO: Publisher channels (like Nintendo or EA) upload videos for dozens of different games. You MUST verify that the YouTube video title or description is actually about the specific game you are evaluating. If a video is about a completely different game, IGNORE IT entirely.
    4. Ignore noisy data (like minor timestamp updates) or old YouTube videos that do not fit the timeframes above.
    
    Output Format:
    You MUST output ONLY a valid JSON array of objects for the games that HAVE updates or impending releases.
    If no games fit the criteria (or if the only recent videos are about different games), output an empty array: []
    
    Example format:
    [
      {{"title": "Game A", "update": "Releasing this week on Friday! Here is the latest launch trailer..."}}
    ]
    """
    
    response = call_gemini_with_retry(contents=prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except json.JSONDecodeError:
        print("Failed to parse Gemini batch response. Ensure prompt rules are strict.")
        return []

def run_scan(scan_type="daily"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Now pulling the youtube_channel_id from the database
    c.execute("SELECT title, igdb_id, rawg_id, youtube_channel_id FROM games")
    all_games = c.fetchall()
    conn.close()

    for i in range(0, len(all_games), BATCH_SIZE):
        batch = all_games[i:i + BATCH_SIZE]
        print(f"\nProcessing batch {i // BATCH_SIZE + 1} ({len(batch)} games)...")
        
        batch_payload = []
        for game in batch:
            title, igdb_id, rawg_id, yt_id = game
            
            raw_data = {}
            if rawg_id != "custom_search":
                raw_data["rawg"] = get_rawg_data(rawg_id)
            if yt_id:
                raw_data["youtube"] = get_youtube_data(yt_id)
                
            if not raw_data:
                 raw_data = {"note": "Custom search target. Awaiting manual updates or web-scraping logic."}
                 
            batch_payload.append({
                "title": title,
                "data": raw_data
            })
            
        updates = evaluate_game_batch(batch_payload, scan_type)
        
        if not updates:
            print("No updates found in this batch.")
            continue
            
        for update in updates:
            title = update.get("title")
            message = update.get("update")
            if title and message:
                payload = {"content": f"**{scan_type.upper()} UPDATE - {title}**\n{message}"}
                if DISCORD_WEBHOOK_URL:
                    requests.post(DISCORD_WEBHOOK_URL, json=payload)
                print(f"Update posted to Discord for {title}.")

if __name__ == "__main__":
    from datetime import datetime
    import sys
    
    def is_within_run_window():
        current_hour = datetime.now().hour
        # Allows execution anytime between 6:00 AM (6) and 11:59 PM (23)
        return current_hour >= 1

    scan_type = sys.argv[1] if len(sys.argv) > 1 else "daily"
    
    if scan_type == "daily":
        if is_within_run_window():
            run_scan("daily")
        else:
            print("Outside of the 6 PM - 1 AM window. Skipping daily scan.")
    else:
        run_scan(scan_type)

def schedule_worker():
    # Execute daily logic exactly at 7:00 AM
    schedule.every().day.at("07:00").do(run_scan, scan_type="daily")
    
    # Execute weekly and monthly summaries slightly offset to avoid API collisions
    schedule.every().monday.at("07:05").do(run_scan, scan_type="weekly")
    schedule.every().month.at("07:10").do(run_scan, scan_type="monthly")
    
    print("Video Game Scanner Daemon online. Awaiting 07:00 AM window...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_scan(sys.argv[1])
    else:
        t = threading.Thread(target=schedule_worker, daemon=True)
        t.start()
        t.join()