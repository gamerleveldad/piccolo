import json
import time
import requests
import psycopg2
from datetime import datetime, date
import math

# --- Configuration ---
# Your Home Coordinates (Replace with your actual coordinates)
HOME_LAT = 28.679885  
HOME_LON = -81.368495

# SDR JSON URL (Assuming ultrafeeder is running locally on port 8085)
JSON_URL = "http://localhost:8085/data/aircraft.json"

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL" 

# Database Connection (Adjust as needed)
DB_HOST = "localhost" 
DB_NAME = "piccolo"
DB_USER = "YOUR_DB_USER"
DB_PASS = "YOUR_DB_PASSWORD"

# --- Distance Calculation (Haversine Formula) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two points in miles."""
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Calculate the differences
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of Earth in miles
    r = 3958.8 
    
    # Return distance
    return c * r

# --- Database Initialization ---
def init_db():
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    
    # Create the main tracking table (dropping if exists for a clean slate, adjust if you want to keep old data)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_flights (
            hex VARCHAR(10) PRIMARY KEY,
            flight VARCHAR(10),
            registration VARCHAR(10),
            type VARCHAR(10),
            description TEXT,
            operator TEXT,
            category VARCHAR(50),
            max_altitude INT,
            min_altitude INT,
            max_speed INT,
            min_speed INT,
            closest_distance FLOAT,
            last_seen TIMESTAMP,
            is_military BOOLEAN,
            is_leo BOOLEAN
        )
    """)
    conn.commit()
    return conn, cur

# --- Data Processing and Storage ---
def process_aircraft(conn, cur, data):
    for aircraft in data.get("aircraft", []):
        hex_code = aircraft.get("hex")
        lat = aircraft.get("lat")
        lon = aircraft.get("lon")
        
        # Skip if no position data
        if not lat or not lon:
            continue
            
        distance = calculate_distance(HOME_LAT, HOME_LON, lat, lon)
        
        # Determine Category using dbFlags
        is_military = False
        is_leo = False
        category_name = "Civilian"
        db_flags = aircraft.get("dbFlags", 0)
        
        if db_flags & 1:  # Military flag
            is_military = True
            category_name = "Military"
        elif db_flags & 2:  # LEO / Interesting flag
            is_leo = True
            category_name = "LEO"

        # Check for immediate Discord Alerts (within 4 miles)
        if (is_military or is_leo) and distance <= 4.0:
            alert_special_aircraft(aircraft, distance, category_name)

        # We only want to track data for the digest if it's within a reasonable radius (e.g., 20 miles) to save DB space,
        # but we'll apply the 3-mile filter during the digest generation.
        if distance <= 20: 
            # Extract data
            flight = aircraft.get("flight", "").strip()
            registration = aircraft.get("r", "")
            ac_type = aircraft.get("t", "")
            desc = aircraft.get("desc", "")
            operator = aircraft.get("ownOp", "")
            alt = aircraft.get("alt_baro")
            speed = aircraft.get("gs")
            
            # Skip if alt or speed are missing or invalid
            if not isinstance(alt, (int, float)) or not isinstance(speed, (int, float)):
                continue

            # Upsert into database
            cur.execute("""
                INSERT INTO daily_flights (
                    hex, flight, registration, type, description, operator, category, 
                    max_altitude, min_altitude, max_speed, min_speed, closest_distance, 
                    last_seen, is_military, is_leo
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s
                ) ON CONFLICT (hex) DO UPDATE SET
                    max_altitude = GREATEST(daily_flights.max_altitude, EXCLUDED.max_altitude),
                    min_altitude = LEAST(daily_flights.min_altitude, EXCLUDED.min_altitude),
                    max_speed = GREATEST(daily_flights.max_speed, EXCLUDED.max_speed),
                    min_speed = LEAST(daily_flights.min_speed, EXCLUDED.min_speed),
                    closest_distance = LEAST(daily_flights.closest_distance, EXCLUDED.closest_distance),
                    last_seen = EXCLUDED.last_seen
            """, (
                hex_code, flight, registration, ac_type, desc, operator, category_name,
                alt, alt, speed, speed, distance, is_military, is_leo
            ))
            conn.commit()

# --- Discord Alerts ---

# Global set to track alerted hex codes to prevent spamming
alerted_aircraft = set()

def alert_special_aircraft(aircraft, distance, category):
    hex_code = aircraft.get("hex")
    
    if hex_code in alerted_aircraft:
        return
        
    flight_id = aircraft.get("flight", "").strip() or aircraft.get("r", "Unknown")
    ac_type = aircraft.get("desc") or aircraft.get("t", "Unknown Type")
    
    message = {
        "content": f"🚨 **{category} Aircraft Alert!** 🚨\n"
                   f"**{flight_id}** ({ac_type}) is currently **{distance:.1f} miles** away."
    }
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=message)
        alerted_aircraft.add(hex_code)
        print(f"Alerted for {hex_code}")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")

def send_daily_digest(cur):
    print("Generating Daily Digest...")
    
    # 1. Top 5 Airlines (Operators)
    cur.execute("""
        SELECT operator, COUNT(*) as count 
        FROM daily_flights 
        WHERE operator != '' AND is_military = FALSE AND is_leo = FALSE
        GROUP BY operator 
        ORDER BY count DESC 
        LIMIT 5
    """)
    top_airlines = cur.fetchall()

    # 2. Top 5 Airplane Types
    cur.execute("""
        SELECT type, description, COUNT(*) as count 
        FROM daily_flights 
        WHERE type != ''
        GROUP BY type, description 
        ORDER BY count DESC 
        LIMIT 5
    """)
    top_types = cur.fetchall()

    # 3. LEO Visits
    cur.execute("SELECT COUNT(*) FROM daily_flights WHERE is_leo = TRUE")
    leo_visits = cur.fetchone()[0]

    # 4. Military Aircraft Detected (with types)
    cur.execute("SELECT flight, type, description FROM daily_flights WHERE is_military = TRUE")
    mil_flights = cur.fetchall()

    # 5. Highest Altitude (Overall)
    cur.execute("SELECT MAX(max_altitude) FROM daily_flights")
    max_alt = cur.fetchone()[0]

    # 6. Lowest Altitude (Within 3 miles)
    cur.execute("SELECT MIN(min_altitude) FROM daily_flights WHERE closest_distance <= 3.0")
    min_alt_3m = cur.fetchone()[0]
    
    # 7. Closest Aircraft
    cur.execute("""
        SELECT flight, registration, type, closest_distance 
        FROM daily_flights 
        WHERE closest_distance IS NOT NULL
        ORDER BY closest_distance ASC 
        LIMIT 1
    """)
    closest_ac = cur.fetchone()

    # 8. Fastest Speed (Overall)
    cur.execute("SELECT MAX(max_speed) FROM daily_flights")
    max_spd = cur.fetchone()[0]

    # 9. Lowest Speed (Within 3 miles)
    cur.execute("SELECT MIN(min_speed) FROM daily_flights WHERE closest_distance <= 3.0")
    min_spd_3m = cur.fetchone()[0]

    # 10. Total Count (Within 3 miles)
    cur.execute("SELECT COUNT(*) FROM daily_flights WHERE closest_distance <= 3.0")
    count_3m = cur.fetchone()[0]

    # --- Constructing the Embed Message ---
    embed = {
        "title": f"📊 Daily Airspace Digest: {date.today()}",
        "color": 3447003, # A nice blue color
        "fields": []
    }

    if top_airlines:
        embed["fields"].append({"name": "Top 5 Airlines", "value": "\n".join([f"{row[0]} ({row[1]})" for row in top_airlines]), "inline": False})
    if top_types:
        embed["fields"].append({"name": "Top 5 Aircraft Types", "value": "\n".join([f"{row[1] or row[0]} ({row[2]})" for row in top_types]), "inline": False})
    
    embed["fields"].append({"name": "LEO Activity", "value": f"{leo_visits} LEO aircraft detected", "inline": True})
    
    mil_text = "\n".join([f"{row[0] or 'Unknown'} - {row[2] or row[1]}" for row in mil_flights]) if mil_flights else "None"
    embed["fields"].append({"name": "Military Activity", "value": mil_text, "inline": False})
    
    embed["fields"].append({"name": "Highest Altitude (Overall)", "value": f"{max_alt or 'N/A'} ft", "inline": True})
    embed["fields"].append({"name": "Lowest Altitude (<3mi)", "value": f"{min_alt_3m or 'N/A'} ft", "inline": True})
    
    closest_text = f"{closest_ac[0] or closest_ac[1]} ({closest_ac[2]}) at {closest_ac[3]:.2f} miles" if closest_ac else "N/A"
    embed["fields"].append({"name": "Closest Approach", "value": closest_text, "inline": False})
    
    embed["fields"].append({"name": "Fastest Speed (Overall)", "value": f"{max_spd or 'N/A'} kts", "inline": True})
    embed["fields"].append({"name": "Slowest Speed (<3mi)", "value": f"{min_spd_3m or 'N/A'} kts", "inline": True})
    embed["fields"].append({"name": "Total Flights (<3mi)", "value": str(count_3m), "inline": True})


    message = {"embeds": [embed]}

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=message)
        print("Daily digest sent successfully.")
        
        # Clear the database for the next day
        cur.execute("TRUNCATE TABLE daily_flights")
        alerted_aircraft.clear()
        
    except Exception as e:
        print(f"Failed to send digest: {e}")

# --- Main Loop ---
if __name__ == "__main__":
    conn, cur = init_db()
    last_digest_date = datetime.now().date()
    
    print("Starting native SDR tracker loop...")
    while True:
        try:
            current_date = datetime.now().date()
            if current_date != last_digest_date:
                send_daily_digest(cur)
                last_digest_date = current_date

            response = requests.get(JSON_URL, timeout=5)
            if response.status_code == 200:
                data = response.json()
                process_aircraft(conn, cur, data)
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching JSON: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            
        time.sleep(5) # Poll every 5 seconds