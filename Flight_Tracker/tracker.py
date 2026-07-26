import os
import time
import requests
import psycopg2
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from haversine import haversine, Unit

# --- Configuration ---
LATITUDE = float(os.getenv("HOME_LATITUDE", "0.0"))
LONGITUDE = float(os.getenv("HOME_LONGITUDE", "0.0"))
RADIUS_NM = 10
POLL_INTERVAL = 30  # 30 seconds is safe for adsb.lol

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
    """Ensure the dashboard state table exists with the expanded schema."""
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
            last_seen TIMESTAMP
        )
    """)
    conn.commit()
    return conn, cur

def main():
    print(f"Starting ADS-B Tracker for {LATITUDE}, {LONGITUDE} ({RADIUS_NM}nm radius)")
    pg_conn, pg_cur = init_postgres()
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    while True:
        try:
            response = requests.get(API_URL, timeout=30)
            response.raise_for_status()
            data = response.json()
            aircraft_list = data.get("ac", [])

            for ac in aircraft_list:
                # Extract basic data
                icao_hex = ac.get("hex", "Unknown")
                registration = str(ac.get("r", "Unknown")).strip()
                callsign = str(ac.get("flight", "N/A")).strip()
                ac_type = ac.get("t", "Unknown")
                emitter_cat = ac.get("category", "Unknown")
                lat = ac.get("lat")
                lon = ac.get("lon")
                
                # Handling specialized fields
                squawk = str(ac.get("squawk", "")).strip()
                emergency = str(ac.get("emergency", "none")).strip()
                vertical_rate = int(ac.get("baro_rate", 0))
                heading = float(ac.get("trk", 0.0)) if ac.get("trk") is not None else 0.0

                # Handle altitude formatting (can return "ground" when landed)
                alt_raw = ac.get("alt_baro", 0)
                altitude_ft = 0 if alt_raw == "ground" else int(alt_raw or 0)
                ground_speed_kts = int(ac.get("gs", 0))

                if lat is None or lon is None:
                    continue

                # Calculate true distance from home
                distance_nm = round(haversine(HOME_COORDS, (lat, lon), unit=Unit.NAUTICAL_MILES), 2)

                # 1. Write to InfluxDB for Grafana
                point = Point("flight_tracking") \
                    .tag("icao_hex", icao_hex) \
                    .tag("registration", registration) \
                    .tag("callsign", callsign) \
                    .tag("aircraft_type", ac_type) \
                    .tag("emitter_category", emitter_cat) \
                    .tag("squawk", squawk) \
                    .tag("emergency", emergency) \
                    .field("altitude_ft", altitude_ft) \
                    .field("vertical_rate", vertical_rate) \
                    .field("ground_speed_kts", ground_speed_kts) \
                    .field("heading", heading) \
                    .field("distance_nm", float(distance_nm)) \
                    .field("lat", float(lat)) \
                    .field("lon", float(lon))
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

                # 2. Upsert into PostgreSQL for Family Dashboard
                pg_cur.execute("""
                    INSERT INTO flights_overhead (
                        icao_hex, registration, callsign, aircraft_type, emitter_category, 
                        altitude_ft, vertical_rate, ground_speed_kts, heading, distance_nm, 
                        squawk, emergency, last_seen
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (icao_hex) DO UPDATE SET
                        registration = EXCLUDED.registration,
                        callsign = EXCLUDED.callsign,
                        aircraft_type = EXCLUDED.aircraft_type,
                        emitter_category = EXCLUDED.emitter_category,
                        altitude_ft = EXCLUDED.altitude_ft,
                        vertical_rate = EXCLUDED.vertical_rate,
                        ground_speed_kts = EXCLUDED.ground_speed_kts,
                        heading = EXCLUDED.heading,
                        distance_nm = EXCLUDED.distance_nm,
                        squawk = EXCLUDED.squawk,
                        emergency = EXCLUDED.emergency,
                        last_seen = NOW();
                """, (icao_hex, registration, callsign, ac_type, emitter_cat, altitude_ft, 
                      vertical_rate, ground_speed_kts, heading, distance_nm, squawk, emergency))

            # Prune stale flights (older than 24 hours) from Postgres
            pg_cur.execute("DELETE FROM flights_overhead WHERE last_seen < NOW() - INTERVAL '24 hours';")
            pg_conn.commit()
            
            print(f"[{time.strftime('%X')}] Tracked {len(aircraft_list)} aircraft around {LATITUDE}, {LONGITUDE} ({RADIUS_NM}nm radius).")

        except Exception as e:
            print(f"Error fetching/saving flight data: {e}")
            if pg_conn.closed:
                pg_conn, pg_cur = init_postgres() # Attempt to reconnect if DB dropped

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()