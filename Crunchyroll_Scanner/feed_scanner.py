import os
import re
import psycopg2
import requests
import time
import schedule
import threading
import sys
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google import genai

# ─── CONFIGURATION & GLOBALS ──────────────────────────────────────────────────
CALENDAR_URL = "https://www.crunchyroll.com/simulcastcalendar?filter=premium"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "anime_tracker.db"

# Master list used to safely seed your database on its initial setup run
SEED_WATCHLIST = [
    "The Beginning After the End",
    "Classroom of the Elite",
    "MARRIAGETOXIN",
    "Witch Hat Atelier",
    "The Klutzy Class Monitor and the Girl with the Short Skirt",
    "Wistoria: Wand and Sword",
    "Snowball Earth",
    "That Time I Got Reincarnated as a Slime",
    "The Warrior Princess and the Barbaric King",
    "Reborn as a Vending Machine, I Now Wander the Dungeon",
    "Daemons of the Shadow Realm"
]

# ─── DATABASE OPERATIONS ──────────────────────────────────────────────────────
def get_db_connection():
    """Attempts to connect to PostgreSQL, retrying if the database is still booting up."""
    retries = 5
    delay = 3
    
    for i in range(retries):
        try:
            return psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST"),
                database=os.environ.get("POSTGRES_DB"),
                user=os.environ.get("POSTGRES_USER"),
                password=os.environ.get("POSTGRES_PASSWORD")
            )
        except psycopg2.OperationalError as e:
            if i < retries - 1:
                print(f"⏳ PostgreSQL isn't ready yet (Attempt {i+1}/{retries}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                # Out of retries, raise the original error
                raise e
def init_db():
    """Initializes the tracking database with support for active tracking, history, and recommendations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Feature #1: Schedule Tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_schedule (
            anime_name TEXT PRIMARY KEY,
            expected_weekday INTEGER,
            last_seen_date TEXT
        )
    ''')
    
    # Feature #2: Watch History Core
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_history (
            anime_name TEXT PRIMARY KEY,
            status TEXT,               -- 'Watching', 'Dormant', 'Completed', 'Dropped'
            user_rating TEXT           -- 'Liked', 'Disliked', 'Neutral'
        )
    ''')
    
    # NEW FOR FEATURE #2: The pool of candidate shows available for suggestions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendation_pool (
            anime_name TEXT PRIMARY KEY,
            genre TEXT,
            description TEXT
        )
    ''')
    
    # ─── SEED WATCH HISTORY ─────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM watch_history")
    if cursor.fetchone()[0] == 0:
        print("🌱 Seeding watch_history table...")
        for anime in SEED_WATCHLIST:
            cursor.execute('''
                INSERT INTO watch_history (anime_name, status, user_rating)
                VALUES (%s, 'Watching', 'Liked')
                ON CONFLICT (anime_name) DO NOTHING
            ''', (anime,))
            
    # ─── SEED RECOMMENDATION POOL (TEST SHOWS) ──────────────────────────────
    # We will seed 3 shows. One of these we will deliberately mark as 'Disliked' 
    # in your history later to prove our exclusion filter works perfectly!
    cursor.execute("SELECT COUNT(*) FROM recommendation_pool")
    if cursor.fetchone()[0] == 0:
        print("🌱 Seeding recommendation pool with test candidates...")
        test_recommendations = [
            ("Solo Leveling", "Action", "A world-renowned hunter progression system."),
            ("Kaiju No. 8", "Action/Sci-Fi", "A monster cleaner gets infected with powers."),
            ("Boring Filler Show", "Comedy", "A placeholder show to test our dislike filter.")
        ]
        for name, genre, desc in test_recommendations:
            cursor.execute('''
                INSERT INTO recommendation_pool (anime_name, genre, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (anime_name) DO NOTHING
            ''', (name, genre, desc))
            
    conn.commit()
    conn.close()
    print("💾 Database initialized and synced successfully.")

def get_scan_targets():
    """Fetches all anime names from the database that require active scraping ('Watching' + 'Dormant')."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anime_name FROM watch_history WHERE status IN ('Watching', 'Dormant')")
    scan_shows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return scan_shows

def get_active_watching_list():
    """Fetches ONLY the shows you are currently watching to run missing schedule verification against."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anime_name FROM watch_history WHERE status = 'Watching'")
    active_shows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return active_shows

def update_show_schedule(anime_name, weekday_idx, date_str):
    """Saves or updates a show's expected release day index in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO watchlist_schedule (anime_name, expected_weekday, last_seen_date)
        VALUES (%s, %s, %s)
        ON CONFLICT(anime_name) DO UPDATE SET
            expected_weekday = excluded.expected_weekday,
            last_seen_date = excluded.last_seen_date
    ''', (anime_name, weekday_idx, date_str))
    conn.commit()
    conn.close()

def check_missing_schedules(found_titles, current_weekday):
    """Compares database schedules against what actually aired today to detect anomalies."""
    active_watchlist = get_active_watching_list()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anime_name FROM watchlist_schedule WHERE expected_weekday = %s", (current_weekday,))
    scheduled_shows = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    missing_alerts = []
    for show in scheduled_shows:
        # Dormant or Dropped shows will not be in active_watchlist, protecting them from alerts
        if show not in found_titles and show in active_watchlist:
            missing_alerts.append(f"- {show} was scheduled to have an episode today but no episodes found.")
            
    return missing_alerts

def get_smart_recommendation(active_drops):
    """
    Checks if a recommendation is needed based on active drops and pending queue.
    If needed, queries Gemini and automatically inserts the suggestion into the database.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("⚠️ Warning: Skipping AI recommendation. Missing GEMINI_API_KEY.")
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Check the Pending Queue limit
    cursor.execute("SELECT COUNT(*) FROM watch_history WHERE status = 'Pending'")
    pending_count = cursor.fetchone()[0]
    
    if active_drops >= 2 or pending_count >= 3:
        conn.close()
        return None # We have enough to watch, skip the AI query!
        
    print(f"Quiet night and only {pending_count} pending shows. Asking Gemini...")

    # 2. Gather preferences for the AI
    cursor.execute("SELECT anime_name FROM watch_history WHERE status IN ('Watching', 'Dormant', 'Completed') OR user_rating = 'Liked'")
    liked_shows = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT anime_name FROM watch_history WHERE user_rating = 'Disliked' OR status = 'Pending'")
    excluded_shows = [row[0] for row in cursor.fetchall()]

    user_style_prompt = (
        "I enjoy action, fantasy, progression systems, and well-animated combat. "
        "I prefer anime that has comedy mixed in. "
        "I do not like anime that has strong mature themes. "
        "I only want age range 16+ and under via the German rating system. "
        "I like any anime with aviation mixed in. "
        "I do not like anime with a lot of gore. "
        "I do not like bittersweet anime. "
        "I do like rom com but it has to lean more on the comedy. "
        "I do not like shows with excessive fan service. "
        "I do not like shows that lean heavy on the harem story type. "
        "I will tolerate shows with very mild fan service or harem elements, especially if they are for comedic effect."
    )

    prompt = f"""
    You are an expert anime recommendation engine.
    My preferences: {user_style_prompt}
    Shows I like/know: {', '.join(liked_shows) if liked_shows else 'None'}
    DO NOT SUGGEST THESE: {', '.join(excluded_shows) if excluded_shows else 'None'}
    
    Recommend exactly ONE English-dubbed anime on Crunchyroll I haven't watched.
    Your response must be ONLY the exact title of the anime. No formatting, no quotes, no explanations.
    """

    try:
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
        suggested_title = response.text.strip()
        
        if suggested_title:
            print(f"🧠 Gemini suggested: {suggested_title}. Adding to Pending queue...")
            
            # 3. Automatically add the new suggestion to the database
            cursor.execute('''
                INSERT INTO watch_history (anime_name, status, user_rating, current_episode, total_episodes)
                VALUES (%s, 'Pending', 'Neutral', 0, 0)
                ON CONFLICT (anime_name) DO NOTHING
            ''', (suggested_title,))
            conn.commit()
            
            conn.close()
            return f"**New Suggestion Added to Pending:** {suggested_title}"
            
    except Exception as e:
        print(f"Gemini AI Generation failed: {e}")
        conn.close()
        return None

# ─── PARSING & SCRAPING HELPERS ───────────────────────────────────────────────

def extract_episode_details(episode_item):
    """Scans the episode element to parse numbers, ranges, or special drops cleanly."""
    ep_element = episode_item.find(class_=lambda c: c and "episode" in c.lower())
    if not ep_element:
        return "New Drop"
        
    raw_text = ep_element.get_text(strip=True)
    match = re.search(r'(\d+(?:-\d+)?(?:\.\d+)?)', raw_text)
    
    if match:
        found_num = match.group(1)
        if "-" in found_num:
            return f"Episodes {found_num}"
        return f"Episode {found_num}"
        
    clean_fallback = re.sub(r'\s*available\s*', '', raw_text, flags=re.IGNORECASE).strip()
    return clean_fallback if clean_fallback else "New Drop"

def get_weekday_from_label(day_text, now_local):
    """Converts a calendar text label (like '5/29' or 'TODAY') into an integer weekday (0-6)."""
    day_clean = day_text.upper().strip()
    
    date_match = re.search(r'(\d+)/(\d+)', day_clean)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        try:
            target_date = datetime(year=now_local.year, month=month, day=day)
            return target_date.weekday()
        except ValueError:
            pass
            
    if "TODAY" in day_clean:
        return now_local.weekday()
        
    return now_local.weekday()

# ─── MAIN SCRAPER ENGINE ──────────────────────────────────────────────────────

def scan_live_calendar():
    init_db()
    
    # Pull fresh scan configurations right out of SQLite
    scan_watchlist = get_scan_targets()
    active_watching = get_active_watching_list()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    cookies = {"locale": "en-US"}
    
    print("🛰️ Connecting to Crunchyroll Premium Simulcast Calendar...")
    response = requests.get(CALENDAR_URL, headers=headers, cookies=cookies)
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch calendar. Status Code: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    matched_drops = []
    found_titles_today = set()

    # ─── TIME WINDOW TARGETS ──────────────────────────────────────────────────
    now_local = datetime.now(ZoneInfo("America/New_York"))
    
    # Changed to days=0 for your focused 11:15 AM single-day tracking operation
    yesterday = now_local - timedelta(days=0) # This could be set to 1 if needed to see yesterdays
    
    target_labels = [
        f"{yesterday.month}/{yesterday.day}",
        f"{now_local.month}/{now_local.day}",
        "TODAY"
    ]
    print(f"📅 Scanning calendar columns matching window: {target_labels}\n")
    
    day_blocks = soup.find_all("li", class_="day")

    for day_block in day_blocks:
        day_header = day_block.find("time")
        if not day_header:
            continue
            
        day_text = day_header.get_text(strip=True)
        is_target = any(target.upper() in day_text.upper() for target in target_labels)
        
        if not is_target:
            continue

        print(f"==== Processing Column: {day_text} ====")
        weekday_idx = get_weekday_from_label(day_text, now_local)
        
        episodes = day_block.find_all(["article", "div"], class_=lambda c: c and "release" in c.lower())
        
        for episode in episodes:
            title_element = episode.find(["h1", "cite", "span"], class_=lambda c: c and "title" in c.lower() or "name" in c.lower())
            if not title_element:
                title_element = episode.find(["h1", "cite"])
                
            show_title = title_element.get_text(strip=True) if title_element else "Unknown Title"
            
            lang_element = episode.find(class_=lambda c: c and ("type" in c.lower() or "lang" in c.lower() or "subtitle" in c.lower()))
            lang_text = lang_element.get_text(strip=True) if lang_element else "Subbed"

            if "dub" in lang_text.lower() or "english" in lang_text.lower() or "english" in show_title.lower():
                # Locate if the item belongs to your combined active or dormant scanning collection
                matched_watchlist_name = next((anime for anime in scan_watchlist if anime.lower() in show_title.lower()), None)
                
                if matched_watchlist_name:
                    episode_string = extract_episode_details(episode)
                    
                    # Update or learn schedule parameters
                    update_show_schedule(matched_watchlist_name, weekday_idx, day_text)
                    
                    # Log finding only if the show is actively in your 'Watching' list
                    if weekday_idx == now_local.weekday() and matched_watchlist_name in active_watching:
                        found_titles_today.add(matched_watchlist_name)
                    
                    clean_entry = (show_title, episode_string)
                    if clean_entry not in matched_drops:
                        print(f"   🎯 MATCH: {show_title} ({episode_string})")
                        matched_drops.append(clean_entry)

    print("\n" + "="*50 + "\n")
    
    # 1. Process schedule anomalies for the day
    missing_alerts = check_missing_schedules(found_titles_today, now_local.weekday())
    
    # 2. FEATURE #2 TRIGGER: If fewer than 2 episodes aired tonight, grab a recommendation
    recommendation_line = get_smart_recommendation(len(matched_drops))
    if len(matched_drops) < 2:
        print("Quiet night detected (fewer than 2 active drops). Querying engine for a suggestion...")
        recommendation_line = get_smart_recommendation(len(matched_drops))
    
    # 3. Deliver structured message out to Discord
    if matched_drops or missing_alerts or recommendation_line:
        print("Updates detected. Routing to Discord...")
        # Updated to include our new recommendation string parameter
        send_discord_notification(matched_drops, missing_alerts, recommendation_line)
    else:
        print("Scan complete. No active drops, alerts, or suggestions today.")

# ─── NOTIFICATION DISPATCH ────────────────────────────────────────────────────

def send_discord_notification(matches_list, alerts_list, recommendation_str=None):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Warning: Discord notification skipped. Missing DISCORD_WEBHOOK variable.")
        return

    message_lines = []
    
    # Section 1: Active releases
    if matches_list:
        message_lines.append("Daily Dub Anime Drops")
        for title, episode in matches_list:
            message_lines.append(f"- {title}: {episode}")
            
    # Section 2: Missing schedule anomaly logs
    if alerts_list:
        if message_lines:
            message_lines.append("") 
        message_lines.append("⚠️ Missed Schedule Alerts")
        message_lines.extend(alerts_list)
        
    # Section 3: Feature #2 Smart Recommendation Line
    if recommendation_str:
        if message_lines:
            message_lines.append("") # Clean double space layout break
        message_lines.append(recommendation_str)
        
    message_content = "\n".join(message_lines)
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message_content})
        if response.status_code == 204:
            print("Discord message delivered successfully!")
        else:
            print(f"Discord returned error status code: {response.status_code}")
    except Exception as e:
        print(f"Failed to dispatch web request to Discord: {e}")

if __name__ == "__main__":
    scan_live_calendar()

def run_anime_pipeline():
    print("🚀 Initiating Crunchyroll schedule evaluation...")
    scan_live_calendar()

def anime_scheduler_worker():
    # Execute daily sweep at 1:15 PM
    schedule.every().day.at("13:15").do(run_anime_pipeline)
    
    print("⏰ Crunchyroll Tracker online. Awaiting 13:15 PM window...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 or os.environ.get("MANUAL_TRIGGER") == "true":
        scan_live_calendar()
    else:
        t = threading.Thread(target=anime_scheduler_worker, daemon=True)
        t.start()
        t.join()