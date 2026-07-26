import os
import time
import requests
import feedparser
import schedule
from datetime import datetime
from google import genai
from influxdb_client import InfluxDBClient

# Configuration from environment variables
WEBHOOK_URL = os.environ.get("WEATHER_DISCORD_WEBHOOK")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WU_API_KEY = os.environ.get("WU_API_KEY")
LAT = os.environ.get("LATITUDE", "28.6611")
LON = os.environ.get("LONGITUDE", "-81.3656")

INFLUX_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = os.environ.get("INFLUXDB_ORG")
INFLUX_BUCKET = os.environ.get("INFLUXDB_BUCKET")

# Initialize Gemini (Using 1.5-flash for speed and optimal rate limit preservation)
client = genai.Client(api_key=GEMINI_API_KEY)

def get_influx_data():
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        query_api = client.query_api()
        # Grabbing the latest forecast push from the weatherflow collector
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
        forecast_url = points_resp['properties']['forecast']
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
        feed = feedparser.parse("https://www.nhc.noaa.gov/index-at.xml")
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

def build_discord_message():
    print(f"[{datetime.now()}] Gathering weather data for Altamonte Springs...")
    
    influx_data = get_influx_data()
    wu_data = get_wu_data()
    nws_data = get_nws_data()
    gfs_data = get_open_meteo_data('gfs')
    euro_data = get_open_meteo_data('ecmwf')
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
    | Stat       | Tmpst | WxUG | NWS | Euro | GFS | Avg |
    |------------|-------|------|-----|------|-----|-----|
    | High       | [fill]| [fill]| [fill]| [fill]| [fill]| [avg]|
    | PoP        | [fill]| [fill]| [fill]| [fill]| [fill]| [avg]|
    | Heat Index | [fill]| [fill]| [fill]| [fill]| [fill]| [avg]|
    
    ### Today's Forecast Discussion
    [Write a 1-2 sentence discussion comparing the GFS and Euro expectations for the day based on the data provided.]
    
    ### Future Forecast
    [Provide the 10-day forecast table, or as many days as the data supports, using a consensus of NWS and WU data. Format exactly like the example table, using actual upcoming dates in MM/DD format.]
    |     | [Date 1] | [Date 2] | [Date 3] | [Date 4] | [Date 5] | [Date 6] | [Date 7] | [Date 8] | [Date 9] | [Date 10] |
    |-----|---|---|---|---|---|---|---|---|---|---|
    | Hi  | | | | | | | | | | |
    | Lo  | | | | | | | | | | |
    | PoP | | | | | | | | | | |
    
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
            model='gemini-3.6-flash',
            contents=prompt
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

if __name__ == "__main__":
    print("Weather Brief Daemon started.")
    
    # Run once immediately on startup for testing
    build_discord_message()
    
    # Schedule to run every morning at 6:00 AM
    schedule.every().day.at("06:00").do(build_discord_message)
    
    while True:
        schedule.run_pending()
        time.sleep(60)