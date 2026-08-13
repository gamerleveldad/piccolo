import json
import os
import time
from datetime import datetime, timedelta, timezone

import feedparser
import psycopg2
import requests
import schedule
from google import genai
from influxdb_client import InfluxDBClient

# --- Environment Variables ---
WEBHOOK_URL = os.environ.get("WEATHER_DISCORD_WEBHOOK")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WU_API_KEY = os.environ.get("WU_API_KEY")
LAT = os.environ.get("LATITUDE", "28.6611")
LON = os.environ.get("LONGITUDE", "-81.3656")

INFLUX_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = os.environ.get("INFLUXDB_ORG")
INFLUX_BUCKET = os.environ.get("INFLUXDB_BUCKET")

XWEATHER_ID = os.environ.get("XWEATHER_CLIENT_ID")
XWEATHER_SECRET = os.environ.get("XWEATHER_CLIENT_SECRET")

PG_HOST = os.environ.get("POSTGRES_HOST", "postgres_db")
PG_DB = os.environ.get("POSTGRES_DB")
PG_USER = os.environ.get("POSTGRES_USER")
PG_PASS = os.environ.get("POSTGRES_PASSWORD")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# --- State Variables ---
STORM_NEARBY = False
ACTIVE_HURRICANE = False
LAST_STORM_CHECK = datetime.min.replace(tzinfo=timezone.utc)
LAST_TROPICS_CHECK = datetime.min.replace(tzinfo=timezone.utc)


def get_db_connection():
    return psycopg2.connect(
        host=PG_HOST, database=PG_DB, user=PG_USER, password=PG_PASS
    )


def setup_database():
    print(f"[{datetime.now(timezone.utc)}] Verifying database tables...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create storm_cells table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS storm_cells (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            cell_id VARCHAR(50),
            lat NUMERIC,
            lon NUMERIC,
            heading_deg NUMERIC,
            speed_kts NUMERIC,
            tvs BOOLEAN,
            mda NUMERIC,
            vil NUMERIC,
            height_ft NUMERIC,
            top_ft NUMERIC,
            hail_prob NUMERIC,
            hail_prob_severe NUMERIC,
            hail_max_size_in NUMERIC,
            forecast_cone_narrow JSONB,
            forecast_cone_wide JSONB,
            traits JSONB
        );
        """)

        # Create lightning_strikes table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lightning_strikes (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            lat NUMERIC,
            lon NUMERIC
        );
        """)

        # Create tropical_storms table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tropical_storms (
            id VARCHAR(20) PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            name VARCHAR(50),
            category VARCHAR(10),
            is_active BOOLEAN,
            lat NUMERIC,
            lon NUMERIC,
            wind_speed_mph NUMERIC,
            gust_speed_mph NUMERIC,
            pressure_mb NUMERIC,
            advisory_number VARCHAR(10),
            movement_dir_deg NUMERIC,
            movement_speed_mph NUMERIC,
            wind_radii JSONB,
            forecast_track JSONB,
            breakpoint_alerts JSONB,
            atlantic_favor VARCHAR(20),
            carrib_favor VARCHAR(20),
            gulf_favor VARCHAR(20),
            outlook_2day_pct INT,
            outlook_7day_pct INT
        );
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Database tables verified successfully.")
    except Exception as e:
        print(f"Error setting up database tables: {e}")


# --- Data Collection Functions for Discord Brief ---
def get_influx_data():
    try:
        client_influx = InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
        )
        query_api = client_influx.query_api()
        query = f'''
            from(bucket: "{INFLUX_BUCKET}")
            |> range(start: -24h)
            |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast")
            |> last()
        '''
        tables = query_api.query(query)
        data = {}
        for table in tables:
            for record in table.records:
                data[record.get_field()] = record.get_value()
        client_influx.close()
        return data
    except Exception as e:
        return f"InfluxDB Error: {e}"


def get_wu_data():
    try:
        url = f"https://api.weather.com/v3/wx/forecast/daily/5day?geocode={LAT},{LON}&format=json&units=e&language=en-US&apiKey={WU_API_KEY}"
        resp = requests.get(url, timeout=10)
        return resp.json()
    except Exception as e:
        return f"WU Error: {e}"


def get_nws_data():
    try:
        headers = {"User-Agent": "PersonalWeatherDaemon/1.0"}
        points_url = f"https://api.weather.gov/points/{LAT},{LON}"
        points_resp = requests.get(points_url, headers=headers, timeout=10).json()
        forecast_url = points_resp["properties"]["forecast"]
        return requests.get(forecast_url, headers=headers, timeout=10).json()
    except Exception as e:
        return f"NWS Error: {e}"


def get_open_meteo_data(model_type):
    try:
        url = f"https://api.open-meteo.com/v1/{model_type}?latitude={LAT}&longitude={LON}&daily=temperature_2m_max,precipitation_probability_max,apparent_temperature_max&temperature_unit=fahrenheit&timezone=America/New_York"
        resp = requests.get(url, timeout=10)
        return resp.json()
    except Exception as e:
        return f"Open-Meteo Error: {e}"


def get_nhc_data():
    try:
        # Fetch the feed using requests to enforce a strict 10-second timeout
        resp = requests.get("https://www.nhc.noaa.gov/index-at.xml", timeout=10)
        resp.raise_for_status()

        # Parse the raw content locally so feedparser doesn't touch the network
        feed = feedparser.parse(resp.content)

        entries = []
        for entry in feed.entries[:5]:
            entries.append(entry.title + ": " + entry.summary)
        return entries
    except Exception as e:
        return f"NHC Error: {e}"


def get_metar_data():
    try:
        url = "https://aviationweather.gov/api/data/metar?ids=KSFB,KORL,KMCO&format=raw"
        resp = requests.get(url, timeout=10)
        return resp.text
    except Exception as e:
        return f"METAR Error: {e}"


# --- Xweather and Tropical Processing ---
def fetch_and_store_storm_data():
    global STORM_NEARBY
    print(f"[{datetime.now(timezone.utc)}] Running Storm and Lightning Check...")

    if not XWEATHER_ID or not XWEATHER_SECRET:
        print("Xweather credentials missing. Skipping storm check.")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        cells_found = False

        # 1. Fetch Storm Cells within 20 nautical miles
        cells_url = f"https://api.aerisapi.com/stormcells/closest?p={LAT},{LON}&radius=20nm&client_id={XWEATHER_ID}&client_secret={XWEATHER_SECRET}"
        cells_resp = requests.get(cells_url, timeout=10).json()

        if cells_resp.get("success") and cells_resp.get("response"):
            cells_found = True
            for cell in cells_resp["response"]:
                ob = cell.get("ob", {})
                movement = ob.get("movement", {})
                hail = ob.get("hail", {})
                forecast = cell.get("forecast", {})

                cursor.execute(
                    """
                    INSERT INTO storm_cells (
                        timestamp, cell_id, lat, lon, heading_deg, speed_kts, 
                        tvs, mda, vil, height_ft, top_ft, hail_prob, 
                        hail_prob_severe, hail_max_size_in, forecast_cone_narrow, 
                        forecast_cone_wide, traits
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        now,
                        cell.get("id"),
                        ob.get("cpos", {}).get("lat"),
                        ob.get("cpos", {}).get("long"),
                        movement.get("dirDEG"),
                        movement.get("speedKTS"),
                        bool(ob.get("tvs", 0)),
                        ob.get("mda"),
                        ob.get("vil"),
                        ob.get("htFT"),
                        ob.get("topFT"),  # <--- Updated this line
                        hail.get("prob"),
                        hail.get("probSevere"),
                        hail.get("maxSizeIN"),
                        json.dumps(forecast.get("cone", {}).get("narrow")),
                        json.dumps(forecast.get("cone", {}).get("wide")),
                        json.dumps(cell.get("traits", {})),
                    ),
                )

        # 2. Fetch Lightning Flashes within 20 nautical miles
        lightning_url = f"https://api.aerisapi.com/lightning/flash/closest?p={LAT},{LON}&radius=20nm&limit=50&client_id={XWEATHER_ID}&client_secret={XWEATHER_SECRET}"
        light_resp = requests.get(lightning_url, timeout=10).json()

        if light_resp.get("success") and light_resp.get("response"):
            cells_found = True
            for strike in light_resp["response"]:
                strike_ts = strike.get("ob", {}).get("timestamp")
                strike_time = (
                    datetime.fromtimestamp(strike_ts, tz=timezone.utc)
                    if strike_ts
                    else now
                )
                cursor.execute(
                    """
                    INSERT INTO lightning_strikes (timestamp, lat, lon)
                    VALUES (%s, %s, %s)
                """,
                    (
                        strike_time,
                        strike.get("loc", {}).get("lat"),
                        strike.get("loc", {}).get("long"),
                    ),
                )

        conn.commit()
        cursor.close()
        conn.close()
        # Transition state: We went from clear skies to storms nearby
        if cells_found and not STORM_NEARBY:
            alert_msg = "⚠️ **Storm Alert: Convective Activity Within 20 Miles**\n"

            # If the trigger was a cell, grab the closest one for details
            if cells_resp.get("success") and cells_resp.get("response"):
                cell = cells_resp["response"][0]
                dist = cell.get("relativeTo", {}).get("distanceMI", "Unknown")
                bearing = cell.get("relativeTo", {}).get("bearing", "Unknown")

                # Fix: Target the correct stormcell movement keys and convert KTS to MPH
                movement = cell.get("ob", {}).get("movement", {})
                speed_kts = movement.get("speedKTS")
                speed_mph = (
                    round(speed_kts * 1.15078, 1)
                    if speed_kts is not None
                    else "Unknown"
                )
                dir_deg = movement.get("dirDEG", "Unknown")

                # Clarify the severity definitions
                is_severe = cell.get("traits", {}).get("isSevere", False)
                severity_text = (
                    "🔴 **SEVERE Thunderstorm/Cell**"
                    if is_severe
                    else "🟡 General Thunderstorm"
                )

                alert_msg += f"- **Type:** {severity_text}\n"
                alert_msg += f"- **Location:** {dist} miles away at direction of {bearing} degrees.\n"
                alert_msg += (
                    f"- **Movement:** Moving {dir_deg} degrees at {speed_mph} mph.\n"
                )
            else:
                alert_msg += "- **Type:** Lightning strikes detected in the immediate vicinity.\n"

            try:
                requests.post(WEBHOOK_URL, json={"content": alert_msg}, timeout=10)
            except Exception as e:
                print(f"Discord webhook failed: {e}")

        STORM_NEARBY = cells_found
        status_str = (
            "Active storm/lightning nearby. Polling set to 3 min."
            if STORM_NEARBY
            else "No local storms. Polling set to 15 min."
        )
        print(f"[{datetime.now(timezone.utc)}] Storm check complete. {status_str}")

    except Exception as e:
        print(f"Error fetching storm data: {e}")


def parse_nhc_outlook_with_gemini(raw_nhc_text):
    """Uses Gemini to extract structured regional favorability and development percentages from raw NHC text."""
    prompt = f"""
    Analyze the following National Hurricane Center text feed and extract regional development favorability.
    
    Output ONLY a valid JSON object matching this exact structure:
    {{
        "atlantic_favor": "Low", 
        "carrib_favor": "Low",
        "gulf_favor": "Low",
        "outlook_2day_pct": 0,
        "outlook_7day_pct": 0
    }}
    
    Rules:
    - Favorability must be one of: "Low", "Moderate", "High"
    - If multiple areas exist in a region, take the highest probability.
    - Percentages must be integers (0 to 100).
    - Do not include markdown code block backticks or extra conversational text.
    
    Raw NHC Feed:
    {raw_nhc_text}
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash", contents=prompt
        )
        text_resp = response.text.strip()
        # Clean JSON if backticks were returned
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:]
        if text_resp.startswith("```"):
            text_resp = text_resp[3:]
        if text_resp.endswith("```"):
            text_resp = text_resp[:-3]
        return json.loads(text_resp.strip())
    except Exception as e:
        print(f"Error parsing NHC text with Gemini: {e}")
        return {
            "atlantic_favor": "Low",
            "carrib_favor": "Low",
            "gulf_favor": "Low",
            "outlook_2day_pct": 0,
            "outlook_7day_pct": 0,
        }


def fetch_and_store_tropics():
    global ACTIVE_HURRICANE
    print(f"[{datetime.now(timezone.utc)}] Running Tropics Check...")

    if not XWEATHER_ID or not XWEATHER_SECRET:
        print("Xweather credentials missing. Skipping tropics check.")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        has_atlantic_storm = False

        # 1. Extract regional favorability using Gemini and raw NHC data
        nhc_entries = get_nhc_data()
        regional_outlook = parse_nhc_outlook_with_gemini("\n".join(nhc_entries))

        # Sanitize percentage inputs to guarantee strict integers for Postgres
        try:
            p_2day = int(
                str(regional_outlook.get("outlook_2day_pct", 0))
                .replace("%", "")
                .strip()
            )
        except Exception:
            p_2day = 0

        try:
            p_7day = int(
                str(regional_outlook.get("outlook_7day_pct", 0))
                .replace("%", "")
                .strip()
            )
        except Exception:
            p_7day = 0

        # 2. ALWAYS insert/update the system outlook record first (guarantees data exists even with 0 active storms)
        cursor.execute(
            """
            INSERT INTO tropical_storms (
                id, timestamp, is_active, 
                atlantic_favor, carrib_favor, gulf_favor, 
                outlook_2day_pct, outlook_7day_pct
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET 
                timestamp = EXCLUDED.timestamp, 
                atlantic_favor = EXCLUDED.atlantic_favor,
                carrib_favor = EXCLUDED.carrib_favor,
                gulf_favor = EXCLUDED.gulf_favor,
                outlook_2day_pct = EXCLUDED.outlook_2day_pct,
                outlook_7day_pct = EXCLUDED.outlook_7day_pct
        """,
            (
                "SYSTEM_OUTLOOK",
                now,
                False,
                regional_outlook.get("atlantic_favor", "Low"),
                regional_outlook.get("carrib_favor", "Low"),
                regional_outlook.get("gulf_favor", "Low"),
                p_2day,
                p_7day,
            ),
        )

        # 3. Fetch Active Cyclones from Xweather
        trop_url = f"https://api.aerisapi.com/tropicalcyclones?client_id={XWEATHER_ID}&client_secret={XWEATHER_SECRET}"
        trop_resp = requests.get(trop_url, timeout=10).json()

        if trop_resp.get("success") and trop_resp.get("response"):
            for storm in trop_resp["response"]:
                profile = storm.get("profile", {})
                storm_id = profile.get("id", "")

                # Filter specifically for Atlantic basin storms
                if not storm_id.startswith("AL"):
                    continue

                has_atlantic_storm = True
                position = storm.get("position", {})
                details = position.get("details", {})
                movement = details.get("movement", {})

                # Format future track array
                track_points = []
                for point in storm.get("forecast", []):
                    point_details = point.get("details", {})
                    track_points.append(
                        {
                            "lead_hours": point.get("profile", {}).get("forecastHour"),
                            "lat": point.get("location", {}).get("coordinates", [0, 0])[
                                1
                            ],
                            "lon": point.get("location", {}).get("coordinates", [0, 0])[
                                0
                            ],
                            "wind_mph": point_details.get("windSpeedMPH"),
                            "category": point_details.get("stormCat"),
                        }
                    )

                cursor.execute(
                    """
                    INSERT INTO tropical_storms (
                        id, timestamp, name, category, is_active, lat, lon, 
                        wind_speed_mph, gust_speed_mph, pressure_mb, advisory_number, 
                        movement_dir_deg, movement_speed_mph, wind_radii, 
                        forecast_track, breakpoint_alerts, atlantic_favor, 
                        carrib_favor, gulf_favor, outlook_2day_pct, outlook_7day_pct
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET 
                        timestamp = EXCLUDED.timestamp, 
                        category = EXCLUDED.category,
                        is_active = EXCLUDED.is_active,
                        lat = EXCLUDED.lat, 
                        lon = EXCLUDED.lon, 
                        wind_speed_mph = EXCLUDED.wind_speed_mph,
                        gust_speed_mph = EXCLUDED.gust_speed_mph,
                        pressure_mb = EXCLUDED.pressure_mb, 
                        advisory_number = EXCLUDED.advisory_number,
                        movement_dir_deg = EXCLUDED.movement_dir_deg,
                        movement_speed_mph = EXCLUDED.movement_speed_mph,
                        wind_radii = EXCLUDED.wind_radii,
                        forecast_track = EXCLUDED.forecast_track,
                        breakpoint_alerts = EXCLUDED.breakpoint_alerts,
                        atlantic_favor = EXCLUDED.atlantic_favor,
                        carrib_favor = EXCLUDED.carrib_favor,
                        gulf_favor = EXCLUDED.gulf_favor,
                        outlook_2day_pct = EXCLUDED.outlook_2day_pct,
                        outlook_7day_pct = EXCLUDED.outlook_7day_pct
                """,
                    (
                        storm_id,
                        now,
                        profile.get("name"),
                        details.get("stormCat"),
                        profile.get("isActive", True),
                        position.get("location", {}).get("coordinates", [0, 0])[1],
                        position.get("location", {}).get("coordinates", [0, 0])[0],
                        details.get("windSpeedMPH"),
                        details.get("gustSpeedMPH"),
                        details.get("pressureMB"),
                        details.get("advisoryNumber"),
                        movement.get("directionDEG"),
                        movement.get("speedMPH"),
                        json.dumps(details.get("windRadii")),
                        json.dumps(track_points),
                        json.dumps(storm.get("breakPointAlerts")),
                        regional_outlook.get("atlantic_favor"),
                        regional_outlook.get("carrib_favor"),
                        regional_outlook.get("gulf_favor"),
                        p_2day,
                        p_7day,
                    ),
                )

        conn.commit()
        cursor.close()
        conn.close()

        ACTIVE_HURRICANE = has_atlantic_storm
        status_str = (
            "Active Atlantic storm. Polling set to 3 hours."
            if ACTIVE_HURRICANE
            else "No active Atlantic storms. Polling set to 6 hours."
        )
        print(f"[{datetime.now(timezone.utc)}] Tropics check complete. {status_str}")

    except Exception as e:
        print(f"Error fetching tropics data: {e}")


# --- Discord Brief Generation ---
def build_discord_message():
    print(f"[{datetime.now()}] Gathering weather data for Altamonte Springs...")

    influx_data = get_influx_data()
    wu_data = get_wu_data()
    nws_data = get_nws_data()
    gfs_data = get_open_meteo_data("gfs")
    euro_data = get_open_meteo_data("ecmwf")
    nhc_data = get_nhc_data()
    metar_data = get_metar_data()

    today_date = datetime.now().strftime("%B %d, %Y")

    prompt = f"""
    You are an analytical meteorological assistant. Your task is to fill out the provided Discord markdown template using the raw data supplied below.
    
    CRITICAL INSTRUCTIONS: 
    1. Do not include ANY emojis in your output. 
    2. Do not include any conversational filler. 
    3. Output ONLY the filled-in markdown text.
    4. Location context is Altamonte Springs, Florida.
    5. Tables MUST be wrapped inside monospaced code blocks (```) and padded with spaces so every column pipe (|) aligns vertically.
    
    Raw Data:
    Tempest (InfluxDB): {influx_data}
    Weather Underground: {wu_data}
    NWS: {nws_data}
    Euro (ECMWF): {euro_data}
    GFS: {gfs_data}
    Tropics (NHC RSS): {nhc_data}
    METARs: {metar_data}
    
    Template to fill out:
    # Daily Weather Update
    -# _{today_date}_
    ## Today's Forecast
    
    ### Forecast Comparisons
    ```
    | Stat       | Tmpst | WxUG  | NWS   | Euro  | GFS   | Avg   |
    |------------|-------|-------|-------|-------|-------|-------|
    | High       | [fill]| [fill]| [fill]| [fill]| [fill]| [avg] |
    | PoP        | [fill]| [fill]| [fill]| [fill]| [fill]| [avg] |
    | Heat Index | [fill]| [fill]| [fill]| [fill]| [fill]| [avg] |
    ```
    
    ### Today's Forecast Discussion
    [Write a 1-2 sentence discussion comparing the GFS and Euro expectations for the day based on the data provided.]
    
    ### Future Forecast
    ```
    |     | [Date 1] | [Date 2] | [Date 3] | [Date 4] | [Date 5] | [Date 6] | [Date 7] | [Date 8] | [Date 9] | [Date 10] |
    |-----|----------|----------|----------|----------|----------|----------|----------|----------|----------|-----------|
    | Hi  | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]    |
    | Lo  | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]    |
    | PoP | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]   | [fill]    |
    ```
    
    ## Tropics Update
    ### Current Storms
    [List active storms from NHC data with estimated movement and intensity. If none, write "No active storms".]
    
    ### Areas of Interest
    [List areas of interest and their development probabilities from NHC data. If none, write "No areas of interest at this time".]
    
    ### Favorability of development
    * Gulf: [Determine from NHC outlook: High/Moderate/Low]
    * Caribbean: [Determine from NHC outlook: High/Moderate/Low]
    * Atlantic: [Determine from NHC outlook: High/Moderate/Low]
    
    ## Aviation Update
    ### METAR
    * ``` [Insert exact KSFB METAR raw text string from the METAR data] ```
    * ``` [Insert exact KORL METAR raw text string from the METAR data] ```
    * ``` [Insert exact KMCO METAR raw text string from the METAR data] ```
    """

    print(f"[{datetime.now()}] Sending payload to Gemini...")
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash", contents=prompt
        )
        final_message = response.text.strip()
    except Exception as e:
        print(f"Error communicating with Gemini: {e}")
        return

    print(f"[{datetime.now()}] Posting payload to Discord Webhook...")
    payload = {"content": final_message}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print(f"[{datetime.now()}] Success!")
    except Exception as e:
        print(f"Error posting to Discord: {e}")


# --- Main Loop ---
if __name__ == "__main__":
    print("Weather and Storm Tracking Daemon started.")

    # Initialize PostgreSQL tables automatically
    setup_database()

    # Schedule Daily Brief
    schedule.every().day.at("06:00").do(build_discord_message)

    while True:
        now = datetime.now(timezone.utc)
        schedule.run_pending()

        # Dynamic Polling: Local Storms (3 min if active storm/lightning near, else 15 min)
        storm_interval = timedelta(minutes=3) if STORM_NEARBY else timedelta(minutes=15)
        if now - LAST_STORM_CHECK >= storm_interval:
            fetch_and_store_storm_data()
            LAST_STORM_CHECK = now

        # Dynamic Polling: Tropics (3 hours if active hurricane, else 6 hours)
        tropics_interval = (
            timedelta(hours=3) if ACTIVE_HURRICANE else timedelta(hours=6)
        )
        if now - LAST_TROPICS_CHECK >= tropics_interval:
            fetch_and_store_tropics()
            LAST_TROPICS_CHECK = now

        time.sleep(10)
