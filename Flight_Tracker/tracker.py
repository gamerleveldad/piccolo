import os
import time
import requests
import psycopg2
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from haversine import haversine, Unit
from datetime import datetime

# --- Configuration ---
LATITUDE = float(os.getenv("HOME_LATITUDE", "0.0"))
LONGITUDE = float(os.getenv("HOME_LONGITUDE", "0.0"))
RADIUS_NM = 5
POLL_INTERVAL = 30 
FLIGHT_DISCORD_WEBHOOK = os.getenv("FLIGHT_DISCORD_WEBHOOK")

# Common local sheriff aviation callsigns or N-numbers
LEO_IDENTIFIERS = ["ALERT", "CHASE"] 

# PostgreSQL config
PG_HOST = os.getenv("POSTGRES_HOST", "postgres_db")
PG_USER = os.getenv("POSTGRES_USER")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD")
PG_DB = os.getenv("POSTGRES_DB")

# InfluxDB config
INFLUX_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUX_ORG = os.getenv("INFLUXDB_ORG")
INFLUX_BUCKET = os.getenv("FLIGHT_TRACKER_BUCKET", "flight_data")

API_URL = f"https://api.adsb.lol/v2/point/{LATITUDE}/{LONGITUDE}/{RADIUS_NM}"
HOME_COORDS = (LATITUDE, LONGITUDE)

def init_postgres():
    conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS flights_overhead (
            icao_hex VARCHAR(10) PRIMARY KEY,
            registration VARCHAR(15),
            callsign VARCHAR(20),
            aircraft_type VARCHAR(20),
            emitter_category VARCHAR(10),
            altitude_ft INTEGER,
            vertical_rate INTEGER,
            ground_speed_kts INTEGER,
            heading NUMERIC,
            distance_nm NUMERIC,
            squawk VARCHAR(10),
            emergency VARCHAR(20),
            is_military BOOLEAN,
            is_leo BOOLEAN,
            first_seen TIMESTAMP DEFAULT NOW(),
            last_seen TIMESTAMP DEFAULT NOW(),
            ping_count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn, cur

def send_discord_alert(title, color, fields):
    if not FLIGHT_DISCORD_WEBHOOK:
        return
    payload = {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    try:
        requests.post(FLIGHT_DISCORD_WEBHOOK, json=payload, timeout=5)
    except Exception as e:
        print(f"Discord error: {e}")

def send_midnight_digest(pg_cur, sheriff_visits, sheriff_seconds):
    # Top 5 Types
    pg_cur.execute("SELECT aircraft_type, COUNT(*) as c FROM flights_overhead WHERE aircraft_type NOT IN ('Unknown', '') GROUP BY aircraft_type ORDER BY c DESC LIMIT 5")
    types = "\n".join([f"{row[0]}: {row[1]}" for row in pg_cur.fetchall()]) or "None"
    
    # Top 5 Airlines (Extracting the first 3 ICAO characters)
    pg_cur.execute("SELECT SUBSTRING(callsign FROM '^[A-Z]{3}') as airline, COUNT(*) as c FROM flights_overhead WHERE callsign ~ '^[A-Z]{3}[0-9]' GROUP BY airline ORDER BY c DESC LIMIT 5")
    airlines = "\n".join([f"{row[0]}: {row[1]}" for row in pg_cur.fetchall()]) or "None"
    
    # Military List
    pg_cur.execute("SELECT registration, callsign, aircraft_type FROM flights_overhead WHERE is_military = TRUE")
    mil = "\n".join([f"{row[1]} ({row[0]}) - {row[2]}" for row in pg_cur.fetchall()]) or "None"
    
    minutes_in_range = sheriff_seconds // 60
    fields = [
        {"name": "Top 5 Types", "value": types, "inline": True},
        {"name": "Top 5 Airlines", "value": airlines, "inline": True},
        {"name": "Sheriff Stats", "value": f"Unique Visits: {sheriff_visits}\nTime in Range: {minutes_in_range} mins", "inline": False},
        {"name": "Military Aircraft Detected", "value": mil, "inline": False},
    ]
    send_discord_alert("Daily Flight Tracking Digest", 3447003, fields)

def main():
    print(f"Starting ADS-B Tracker for {LATITUDE}, {LONGITUDE} ({RADIUS_NM}nm radius)")
    pg_conn, pg_cur = init_postgres()
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    # State Variables
    alerted_aircraft = {}
    active_leo_tracking = {}
    sheriff_visits_today = 0
    sheriff_seconds_in_range = 0
    last_digest_date = datetime.now().date()

    while True:
        try:
            current_time = time.time()
            current_date = datetime.now().date()
            
            # Trigger Midnight Digest
            if current_date != last_digest_date:
                send_midnight_digest(pg_cur, sheriff_visits_today, sheriff_seconds_in_range)
                sheriff_visits_today = 0
                sheriff_seconds_in_range = 0
                alerted_aircraft.clear()
                active_leo_tracking.clear()
                last_digest_date = current_date

            response = requests.get(API_URL, timeout=30)
            response.raise_for_status()
            aircraft_list = response.json().get("ac", [])

            for ac in aircraft_list:
                icao_hex = ac.get("hex", "Unknown")
                registration = str(ac.get("r", "Unknown")).strip()
                callsign = str(ac.get("flight", "N/A")).strip()
                ac_type = ac.get("t", "Unknown")
                emitter_cat = ac.get("category", "Unknown")
                lat = ac.get("lat")
                lon = ac.get("lon")
                
                squawk = str(ac.get("squawk", "")).strip()
                emergency = str(ac.get("emergency", "none")).strip()
                vertical_rate = int(ac.get("baro_rate", 0))
                heading = float(ac.get("trk", 0.0)) if ac.get("trk") is not None else 0.0
                alt_raw = ac.get("alt_baro", 0)
                altitude_ft = 0 if alt_raw == "ground" else int(alt_raw or 0)
                ground_speed_kts = int(ac.get("gs", 0))

                if lat is None or lon is None:
                    continue

                distance_nm = round(haversine(HOME_COORDS, (lat, lon), unit=Unit.NAUTICAL_MILES), 2)

                # Flag Parsing
                is_military = ac.get("mil", False) == True or (ac.get("dbFlags", 0) & 1) == 1 
                is_leo = any(ident in registration for ident in LEO_IDENTIFIERS) or any(ident in callsign for ident in LEO_IDENTIFIERS)
                is_emergency = squawk in ["7500", "7600", "7700"] or (emergency.lower() not in ["none", ""])

                # --- DISCORD ALERT LOGIC ---
                if is_emergency or is_leo or is_military:
                    last_alert = alerted_aircraft.get(icao_hex, 0)
                    # Block repeat alerts for the same airframe for 4 hours
                    if current_time - last_alert > 14400: 
                        alert_type = "Emergency Squawk Detected!" if is_emergency else "LEO / Military Aircraft Overhead"
                        color = 16711680 if is_emergency else 3447003
                        fields = [
                            {"name": "Callsign / Reg", "value": f"{callsign} / {registration}", "inline": True},
                            {"name": "Type", "value": ac_type, "inline": True},
                            {"name": "Distance", "value": f"{distance_nm} nm", "inline": True},
                            {"name": "Altitude", "value": f"{altitude_ft} ft", "inline": True},
                            {"name": "Squawk", "value": f"{squawk} ({emergency})", "inline": True}
                        ]
                        send_discord_alert(alert_type, color, fields)
                        alerted_aircraft[icao_hex] = current_time

                # --- LEO STAT TRACKING ---
                if is_leo:
                    sheriff_seconds_in_range += POLL_INTERVAL
                    last_leo_ping = active_leo_tracking.get(icao_hex, 0)
                    # If we haven't seen this hex in 20 minutes, count it as a new distinct flyover
                    if current_time - last_leo_ping > 1200: 
                        sheriff_visits_today += 1
                    active_leo_tracking[icao_hex] = current_time

                # 1. Write to InfluxDB
                point = Point("flight_tracking") \
                    .tag("icao_hex", icao_hex) \
                    .tag("callsign", callsign) \
                    .tag("aircraft_type", ac_type) \
                    .tag("squawk", squawk) \
                    .field("altitude_ft", altitude_ft) \
                    .field("distance_nm", float(distance_nm)) \
                    .field("lat", float(lat)) \
                    .field("lon", float(lon))
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

                # 2. Upsert to PostgreSQL
                pg_cur.execute("""
                    INSERT INTO flights_overhead (
                        icao_hex, registration, callsign, aircraft_type, emitter_category, 
                        altitude_ft, vertical_rate, ground_speed_kts, heading, distance_nm, 
                        squawk, emergency, is_military, is_leo, first_seen, last_seen, ping_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), 1)
                    ON CONFLICT (icao_hex) DO UPDATE SET
                        registration = EXCLUDED.registration,
                        callsign = EXCLUDED.callsign,
                        altitude_ft = EXCLUDED.altitude_ft,
                        vertical_rate = EXCLUDED.vertical_rate,
                        ground_speed_kts = EXCLUDED.ground_speed_kts,
                        heading = EXCLUDED.heading,
                        distance_nm = EXCLUDED.distance_nm,
                        squawk = EXCLUDED.squawk,
                        emergency = EXCLUDED.emergency,
                        is_military = EXCLUDED.is_military,
                        is_leo = EXCLUDED.is_leo,
                        last_seen = NOW(),
                        ping_count = flights_overhead.ping_count + 1;
                """, (icao_hex, registration, callsign, ac_type, emitter_cat, altitude_ft, 
                      vertical_rate, ground_speed_kts, heading, distance_nm, squawk, emergency, is_military, is_leo))

            # Prune aircraft not seen in 24 hours
            pg_cur.execute("DELETE FROM flights_overhead WHERE last_seen < NOW() - INTERVAL '24 hours';")
            pg_conn.commit()
            
            print(f"[{time.strftime('%X')}] Tracked {len(aircraft_list)} aircraft.")

        except Exception as e:
            print(f"Error: {e}")
            if pg_conn.closed:
                pg_conn, pg_cur = init_postgres()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()