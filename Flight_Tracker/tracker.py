import json
import time
import requests
import psycopg2
from datetime import datetime, date
import math
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Configuration ---
HOME_LAT = 28.679885  
HOME_LON = -81.368495

JSON_URL = "http://localhost:8085/data/aircraft.json"
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL" 

# PostgreSQL Settings
DB_HOST = "localhost" 
DB_NAME = "piccolo"
DB_USER = "YOUR_DB_USER"
DB_PASS = "YOUR_DB_PASSWORD"

# InfluxDB 2.x Settings
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "YOUR_NEW_INFLUX_TOKEN"  # Update with your new token if recreated
INFLUX_ORG = "YOUR_INFLUX_ORG"
INFLUX_BUCKET = "piccolo"

# --- Distance Calculation ---
def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 3958.8  # Miles

# --- Database Initialization ---
def init_db():
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
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

# --- InfluxDB Client ---
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# --- Data Processing and Storage ---
def process_aircraft(conn, cur, data):
    influx_points = []
    
    for aircraft in data.get("aircraft", []):
        hex_code = aircraft.get("hex")
        lat = aircraft.get("lat")
        lon = aircraft.get("lon")
        
        if not lat or not lon:
            continue
            
        distance = calculate_distance(HOME_LAT, HOME_LON, lat, lon)
        
        # Determine Category
        is_military = False
        is_leo = False
        category_name = "Civilian"
        db_flags = aircraft.get("dbFlags", 0)
        
        if db_flags & 1:
            is_military = True
            category_name = "Military"
        elif db_flags & 2:
            is_leo = True
            category_name = "LEO"

        # 1. Discord Alerts (within 4 miles)
        if (is_military or is_leo) and distance <= 4.0:
            alert_special_aircraft(aircraft, distance, category_name)

        flight = aircraft.get("flight", "").strip()
        registration = aircraft.get("r", "")
        ac_type = aircraft.get("t", "")
        desc = aircraft.get("desc", "")
        operator = aircraft.get("ownOp", "")
        alt = aircraft.get("alt_baro")
        speed = aircraft.get("gs")
        track = aircraft.get("track", 0.0)

        if not isinstance(alt, (int, float)) or not isinstance(speed, (int, float)):
            continue

        # 2. InfluxDB Time-Series Metric (Point-in-Time Telemetry)
        p = Point("flights_overhead") \
            .tag("hex", hex_code) \
            .tag("flight", flight or "UNKNOWN") \
            .tag("type", ac_type or "UNKNOWN") \
            .tag("category", category_name) \
            .field("altitude", float(alt)) \
            .field("speed", float(speed)) \
            .field("heading", float(track)) \
            .field("distance_miles", float(distance)) \
            .field("latitude", float(lat)) \
            .field("longitude", float(lon))
        
        influx_points.append(p)

        # 3. PostgreSQL Aggregations (Only for local radius tracking <= 20 miles)
        if distance <= 20: 
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

    # Batch write points to InfluxDB
    if influx_points:
        try:
            write_api.write(bucket=INFLUX_BUCKET, record=influx_points)
        except Exception as e:
            print(f"Failed to write to InfluxDB: {e}")

# --- Discord Alerts & Digest ---
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
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")

def send_daily_digest(cur):
    print("Generating Daily Digest...")
    
    cur.execute("""
        SELECT operator, COUNT(*) as count 
        FROM daily_flights 
        WHERE operator != '' AND is_military = FALSE AND is_leo = FALSE
        GROUP BY operator ORDER BY count DESC LIMIT 5
    """)
    top_airlines = cur.fetchall()

    cur.execute("""
        SELECT type, description, COUNT(*) as count 
        FROM daily_flights 
        WHERE type != ''
        GROUP BY type, description ORDER BY count DESC LIMIT 5
    """)
    top_types = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM daily_flights WHERE is_leo = TRUE")
    leo_visits = cur.fetchone()[0]

    cur.execute("SELECT flight, type, description FROM daily_flights WHERE is_military = TRUE")
    mil_flights = cur.fetchall()

    cur.execute("SELECT MAX(max_altitude) FROM daily_flights")
    max_alt = cur.fetchone()[0]

    cur.execute("SELECT MIN(min_altitude) FROM daily_flights WHERE closest_distance <= 3.0")
    min_alt_3m = cur.fetchone()[0]
    
    cur.execute("""
        SELECT flight, registration, type, closest_distance 
        FROM daily_flights WHERE closest_distance IS NOT NULL
        ORDER BY closest_distance ASC LIMIT 1
    """)
    closest_ac = cur.fetchone()

    cur.execute("SELECT MAX(max_speed) FROM daily_flights")
    max_spd = cur.fetchone()[0]

    cur.execute("SELECT MIN(min_speed) FROM daily_flights WHERE closest_distance <= 3.0")
    min_spd_3m = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM daily_flights WHERE closest_distance <= 3.0")
    count_3m = cur.fetchone()[0]

    embed = {
        "title": f"📊 Daily Airspace Digest: {date.today()}",
        "color": 3447003,
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
        cur.execute("TRUNCATE TABLE daily_flights")
        alerted_aircraft.clear()
    except Exception as e:
        print(f"Failed to send digest: {e}")

# --- Main Loop ---
if __name__ == "__main__":
    conn, cur = init_db()
    last_digest_date = datetime.now().date()
    
    print("Starting native SDR tracker loop (PostgreSQL + InfluxDB)...")
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
            
        time.sleep(5)