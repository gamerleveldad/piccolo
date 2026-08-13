import argparse
import asyncio
import datetime
import html
import io
import json
import logging
import math
import os
import random
import re
import socket
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

import aiohttp
import aiomqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("dashboard_api")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- COMMAND LINE & ENVIRONMENT CONFIGURATION ---
parser = argparse.ArgumentParser(description="Tactical Weather Dashboard Backend API")
parser.add_argument(
    "--simulate",
    action="store_true",
    help="Run telemetry simulator instead of live hardware feeds.",
)
args, _ = parser.parse_known_args()

SIMULATION_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true" or args.simulate

# Internal Microservice Endpoint Definitions
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather_api:8000")
FLIGHT_API_URL = os.getenv("FLIGHT_API_URL", "http://flight_api:8000")
CRUNCHYROLL_API_URL = os.getenv("CRUNCHYROLL_API_URL", "http://crunchyroll_api:8000")
FANTASY_API_URL = os.getenv("FANTASY_API_URL", "http://fantasy_football_api:8000")

API_TOKEN_BIBLE = os.getenv("BIBLE_API_TOKEN")
LATITUDE = float(os.getenv("LATITUDE", 28.66))
LONGITUDE = float(os.getenv("LONGITUDE", -81.36))

if not SIMULATION_MODE and (not API_TOKEN_BIBLE):
    logger.warning(
        "CRITICAL: API Tokens are missing from the environment configuration."
    )

# In-memory REST cache
rest_cache = {
    "weather": {},
    "forecast_daily": [],
    "alerts": [],
    "daily_verse": {
        "reference": "Psalm 119:105",
        "text": "Your word is a lamp to guide my feet and a light for my path.",
    },
    "anime_progress": [],
    "active_flights": [],
    "sleeper": {"mode": "disabled"},
}

# --- BUSINESS LOGIC & CALCULATION ENGINE ---


def calculate_comfort_level(dew_point_f: float) -> dict:
    if dew_point_f is None or dew_point_f == "--.-":
        return {"text": "Analyzing Air...", "color": "text-slate-500"}
    dp = float(dew_point_f)
    if dp < 30:
        return {"text": "L1: Desert Conditions", "color": "text-cyan-300"}
    if dp < 40:
        return {"text": "L2: Low Moisture", "color": "text-teal-400"}
    if dp < 50:
        return {"text": "L3: Comfortable", "color": "text-emerald-400"}
    if dp < 55:
        return {"text": "L4: Pleasant", "color": "text-green-400"}
    if dp < 60:
        return {"text": "L5: Moderate Humidity", "color": "text-yellow-300"}
    if dp < 65:
        return {"text": "L6: Humid", "color": "text-amber-400"}
    if dp < 70:
        return {"text": "L7: Typical Florida", "color": "text-orange-400"}
    if dp < 75:
        return {"text": "L8: High Humidity", "color": "text-orange-600"}
    if dp < 80:
        return {"text": "L9: Very Humid", "color": "text-red-500"}
    return {
        "text": "L10: Extreme Humidity",
        "color": "text-purple-500 font-extrabold animate-pulse",
    }


def calculate_pressure_diagnostics(pressure_inhg: float) -> dict:
    if pressure_inhg is None:
        return {"tier": "Unknown", "tierColor": "text-slate-500"}
    p_val = float(pressure_inhg)
    if p_val >= 30.20:
        return {"tier": "High System", "tierColor": "text-cyan-400"}
    elif p_val < 29.80:
        if p_val < 28.94:
            return {
                "tier": "Major Hurricane",
                "tierColor": "text-red-500 font-black animate-pulse",
            }
        if p_val < 29.23:
            return {
                "tier": "Hurricane Depression",
                "tierColor": "text-orange-500 font-extrabold",
            }
        if p_val < 29.53:
            return {"tier": "Tropical Storm", "tierColor": "text-amber-500 font-bold"}
        if p_val < 29.71:
            return {"tier": "Tropical Depression", "tierColor": "text-yellow-400"}
        return {"tier": "Low Pressure", "tierColor": "text-purple-400"}
    return {"tier": "Normal Range", "tierColor": "text-slate-300"}


def calculate_rain_status(rain_rate_in_hr: float) -> dict:
    r = float(rain_rate_in_hr or 0.0)
    if r == 0:
        return {"text": "Not Raining", "color": "text-emerald-500"}
    if r < 0.1:
        return {"text": "Light Rain", "color": "text-blue-300"}
    if r < 0.3:
        return {"text": "Moderate Rain", "color": "text-blue-400"}
    return {"text": "Heavy Rain", "color": "text-blue-500 font-bold animate-pulse"}


def calculate_activity_ratings(weather_data: dict, daily_forecast: list) -> list:
    temp = float(weather_data.get("temperature_f", 72.0))
    feels = float(weather_data.get("feels_like_f", temp))
    humidity = float(weather_data.get("humidity_pct", 50.0))
    wind = float(weather_data.get("wind_speed_mph", 0.0))
    gust = float(weather_data.get("wind_gust_mph", 0.0))
    rain_accum = float(weather_data.get("rain_accumulation_day_in", 0.0))
    rain_rate = float(weather_data.get("rain_rate_in_hr", 0.0))
    lightning_dist = float(weather_data.get("last_strike_distance") or 999.0)

    fc_day = daily_forecast[0] if daily_forecast else {}
    fc_temp = (float(fc_day.get("high", temp)) + float(fc_day.get("low", temp))) / 2.0
    fc_rain_chance = int(fc_day.get("rain_pct", 0))

    def evaluate(t, f, h, w, g, r_accum, r_rate, l_dist, is_forecast=False):
        scores = {
            "Walking": 10,
            "Airbrushing": 10,
            "Yard Work": 10,
            "Video Games": 5,
            "Basketball": 10,
            "Football": 10,
            "Swimming": 10,
            "Driving": 10,
        }

        if t < 65:
            scores["Football"] -= min((65 - t) / 4, 3)
        if t > 75:
            scores["Football"] -= min((t - 75) / 3, 4)
        if f > 100:
            scores["Football"] = 0
        if w > 15 or g > 22:
            scores["Football"] -= 3
        if r_accum > 0.15:
            scores["Football"] -= 2.5
        if is_forecast and fc_rain_chance > 60:
            scores["Football"] -= fc_rain_chance / 20

        if t < 62:
            scores["Basketball"] -= min((62 - t) / 3, 4)
        if t > 75:
            scores["Basketball"] -= min((t - 75) / 3, 4)
        if f > 98:
            scores["Basketball"] = 0
        if w > 8:
            scores["Basketball"] -= 2
        if r_accum > 0.30:
            scores["Basketball"] = 0

        if t > 90:
            scores["Yard Work"] -= 4
        if f > 102:
            scores["Yard Work"] = 0
        if w > 25:
            scores["Yard Work"] -= 3
        if r_accum > 0.15:
            scores["Yard Work"] -= 3

        if t < 60 or t > 75:
            scores["Airbrushing"] -= min(abs(t - 67) / 3, 4)
        if h > 65:
            scores["Airbrushing"] -= 2
        if h > 75:
            scores["Airbrushing"] -= 3.5
        if w > 5 or g > 8:
            scores["Airbrushing"] = 0

        if t > 85 or t < 50:
            scores["Walking"] -= min(abs(t - 70) / 3, 5)
        if h > 85:
            scores["Walking"] -= 2
        if r_accum > 0.02:
            scores["Walking"] = 0

        if t < 70 or l_dist <= 20:
            scores["Swimming"] = 0
        else:
            scores["Swimming"] = min(2 + ((t - 70) * 0.4), 10)

        vg = 5
        if r_rate > 0 or f >= 95 or f <= 35:
            vg = 10
        elif t >= 80:
            vg += (t - 80) * 0.2
        elif t <= 60:
            vg += (60 - t) * 0.2
        if is_forecast and fc_rain_chance > 20:
            vg += fc_rain_chance / 15
        scores["Video Games"] = vg

        dr = 10
        if r_rate > 0:
            if r_rate < 0.1:
                dr -= 2
            elif r_rate < 0.5:
                dr -= 5
            else:
                dr -= 9
        if is_forecast and fc_rain_chance > 20:
            dr -= fc_rain_chance / 15
        scores["Driving"] = dr

        return {k: min(max(round(v), 0), 10) for k, v in scores.items()}

    current_scores = evaluate(
        temp, feels, humidity, wind, gust, rain_accum, rain_rate, lightning_dist, False
    )
    forecast_scores = evaluate(
        fc_temp,
        fc_temp,
        humidity,
        wind,
        gust,
        rain_accum,
        rain_rate,
        lightning_dist,
        True,
    )

    return [
        {
            "name": name,
            "currentScore": current_scores[name],
            "forecastScore": forecast_scores[name],
        }
        for name in current_scores
    ]


MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")


async def listen_to_mqtt():
    logger.info("MQTT Subscriber Thread starting...")
    while True:
        try:
            async with aiomqtt.Client(MQTT_BROKER) as client:
                await client.subscribe("weather/tempest/live")
                logger.info("Subscribed to MQTT stream: weather/tempest/live")

                async for message in client.messages:
                    payload_str = message.payload.decode()
                    # Instantly push the MQTT message down to the frontend WebSockets
                    await manager.broadcast(payload_str)

        except Exception as e:
            logger.error(f"MQTT Connection Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


async def simulate_weather_stream():
    logger.info("Simulation Matrix Engine online: 100% Mock Data Generation Active")
    sim_heading = 270

    while True:
        try:
            sim_heading = (sim_heading + random.randint(-40, 40)) % 360
            base_wind = round(random.uniform(5.0, 20.0), 1)

            sim_wind = {
                "update_type": "rapid_wind",
                "wind_speed_mph": base_wind,
                "wind_direction_deg": int(sim_heading),
                "icon_api": "clear-day",
                "conditions": "Clear",
            }
            await manager.broadcast(json.dumps(sim_wind))
            await asyncio.sleep(3.0)

            if random.random() < 0.20:
                sim_strike = {
                    "update_type": "lightning_strike",
                    "distance_miles": round(random.uniform(2.0, 25.0), 1),
                    "energy": random.randint(1000, 15000),
                    "timestamp": int(datetime.datetime.now().timestamp()),
                }
                await manager.broadcast(json.dumps(sim_strike))
            await asyncio.sleep(2.5)

        except Exception as e:
            logger.error(f"Simulator Engine Crash: {e}", exc_info=True)
            await asyncio.sleep(2)


# --- GOOGLE OAUTH & WORKERS ---

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.readonly",
]

CALENDAR_TARGETS = {
    "display_board": "810d2e7891b3be1da204c04a0959229aa41467ae7b110d83f72343ec7b1490e0@group.calendar.google.com",
    "family": "family08995171228833928146@group.calendar.google.com",
    "holidays": "en.usa#holiday@group.v.calendar.google.com",
}

GOOGLE_COLOR_MAP = {
    "1": "#a4bdfc",
    "2": "#7ae7bf",
    "3": "#dbadff",
    "4": "#ff887c",
    "5": "#fbd75b",
    "6": "#ffb878",
    "7": "#46d6db",
    "8": "#e1e1e1",
    "9": "#5484ed",
    "10": "#51b749",
    "11": "#dc2127",
}


def match_event_weather(event_start_iso, hourly_periods):
    if not hourly_periods:
        return None
    try:
        event_dt = datetime.datetime.fromisoformat(
            event_start_iso.replace("Z", "+00:00")
        )
        event_ts = int(event_dt.timestamp())
    except Exception:
        return None

    for period in hourly_periods:
        try:
            p_time = int(
                datetime.datetime.fromisoformat(
                    period["time"].replace("Z", "+00:00")
                ).timestamp()
            )
            # Check if the event falls within this specific forecasted hour
            if p_time <= event_ts < (p_time + 3600):
                return {
                    "temp": int(period.get("temp_f", 72)),
                    "icon": period.get("icon", "clear-day"),
                    "rain_pct": int(period.get("precip_probability", 0)),
                }
        except Exception:
            continue
    return None


def get_calendar_credentials():
    creds = None
    token_path = os.path.join(BASE_DIR, "token.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as token:
                token.write(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as token:
                token.write(creds.to_json())
    return creds


async def poll_daily_verse():
    logger.info("YouVersion + NLT Daily Verse sync worker online.")
    while True:
        try:
            # use timezone-aware datetime to avoid naive datetime usage
            day_of_year = datetime.datetime.now(tz=datetime.timezone.utc).timetuple().tm_yday

            async with aiohttp.ClientSession() as session:
                # 1. Fetch the Human Reference from YouVersion
                yv_url = f"https://developers.youversionapi.com/1.0/verse_of_the_day/{day_of_year}?version_id=1"
                headers = {
                    "X-YouVersion-Developer-Token": API_TOKEN_BIBLE,
                    "Accept": "application/json",
                }

                ref_string = None
                async with session.get(yv_url, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        yv_data = await resp.json()
                        ref_string = yv_data.get("verse", {}).get("human_reference")

                if ref_string:
                    # 2. Fetch the full NLT HTML payload
                    nlt_ref = ref_string.replace(" ", ".")
                    nlt_url = f"https://api.nlt.to/api/passages?ref={nlt_ref}"
                    async with session.get(nlt_url, timeout=5) as nlt_resp:
                        if nlt_resp.status == 200:
                            nlt_html = await nlt_resp.text()

                            # Isolate the core verse HTML for the frontend modal
                            match = re.search(
                                r'<div id="bibletext".*?>(.*?)</div></body>',
                                nlt_html,
                                re.IGNORECASE | re.DOTALL,
                            )
                            inner_html = match.group(1) if match else nlt_html

                            # Strip tags to create clean text for the truncated top bar
                            clean_text = re.sub(
                                r'<span class="vn">.*?</span>', "", inner_html
                            )
                            clean_text = re.sub(r"<h2.*?>.*?</h2>", "", clean_text)
                            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
                            clean_text = re.sub(r"\s+", " ", clean_text).strip()

                            rest_cache["daily_verse"] = {
                                "reference": ref_string,
                                "text": clean_text,
                                "html": inner_html,
                            }
        except Exception as e:
            logger.error(f"Failed to fetch 2-API daily verse: {e}")

        await asyncio.sleep(43200)  # Refresh every 12 hours


async def poll_calendar_events():
    logger.info("Calendar synchronization worker online.")
    while True:
        try:
            creds = get_calendar_credentials()
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            now = datetime.datetime.now(datetime.timezone.utc)
            time_min = now.isoformat()
            time_max = (now + datetime.timedelta(days=28)).isoformat()

            aggregated_events = []
            for source_tag, cal_id in CALENDAR_TARGETS.items():
                events_result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                for e in events_result.get("items", []):
                    start_data = e["start"].get("dateTime", e["start"].get("date"))
                    is_all_day = "date" in e["start"] and "dateTime" not in e["start"]

                    event_forecast = None
                    if not is_all_day and start_data:
                        hourly_data = rest_cache.get("forecast_hourly", [])
                        event_forecast = match_event_weather(start_data, hourly_data)

                    raw_color_id = str(e.get("colorId", ""))
                    event_color = e.get(
                        "backgroundColor", GOOGLE_COLOR_MAP.get(raw_color_id, "#38bdf8")
                    )

                    aggregated_events.append(
                        {
                            "id": e.get("id"),
                            "summary": e.get("summary", "Untitled Event"),
                            "start": start_data,
                            "location": e.get("location"),
                            "is_all_day": is_all_day,
                            "color": event_color,
                            "source": source_tag,
                            "forecast": event_forecast,
                        }
                    )

            await manager.broadcast(
                json.dumps(
                    {"update_type": "calendar_sync", "events": aggregated_events}
                )
            )
        except Exception as err:
            logger.error(f"Calendar Thread Error: {err}")
        await asyncio.sleep(300)


async def poll_google_drive_photos():
    logger.info("Google Drive Photo sync worker online.")
    photo_dir = os.path.join(BASE_DIR, "assets", "photos")
    os.makedirs(photo_dir, exist_ok=True)
    MIME_MAP = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }

    def sync_logic():
        creds = get_calendar_credentials()
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        results = (
            service.files()
            .list(
                q="mimeType='application/vnd.google-apps.folder' and name='DisplayBoard' and trashed=false",
                fields="files(id, name)",
            )
            .execute()
        )
        folders = results.get("files", [])
        if not folders:
            return

        folder_id = folders[0]["id"]
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false",
                fields="files(id, name, mimeType)",
            )
            .execute()
        )
        cloud_images = results.get("files", [])

        cloud_safe_names = {}
        for img in cloud_images:
            original_name = img["name"]
            ext = os.path.splitext(original_name)[1].lower()
            if not ext:
                inferred_ext = MIME_MAP.get(img.get("mimeType", ""), ".png")
                safe_name = f"{original_name}{inferred_ext}"
            else:
                safe_name = original_name
            cloud_safe_names[safe_name] = img

        local_filenames = set(
            [f for f in os.listdir(photo_dir) if not f.startswith(".")]
        )
        for local_file in local_filenames:
            if local_file not in cloud_safe_names:
                os.remove(os.path.join(photo_dir, local_file))

        for safe_name, img in cloud_safe_names.items():
            if safe_name not in local_filenames:
                request = service.files().get_media(fileId=img["id"])
                # FIX: Wrap the file IO in a 'with' context manager to guarantee it closes
                with io.FileIO(os.path.join(photo_dir, safe_name), "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()

    while True:
        try:
            await asyncio.to_thread(sync_logic)
        except Exception as e:
            logger.error(f"Drive Sync error: {e}", exc_info=True)
        await asyncio.sleep(3600)


async def poll_local_microservices():
    logger.info("Local microservice aggregation loop online.")
    # Create the session ONCE outside the loop
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Current Weather
                try:
                    async with session.get(
                        f"{WEATHER_API_URL}/api/weather/current", timeout=5
                    ) as resp:
                        if resp.status == 200:
                            # Use .update() so we don't erase the hourly rain buckets!
                            current_data = await resp.json()
                            if "weather" not in rest_cache:
                                rest_cache["weather"] = {}
                            rest_cache["weather"].update(current_data)
                except Exception:
                    pass

                # 2. Daily Forecast
                try:
                    async with session.get(
                        f"{WEATHER_API_URL}/api/weather/forecast/daily", timeout=5
                    ) as resp:
                        if resp.status == 200:
                            rest_cache["forecast_daily"] = await resp.json()
                except Exception:
                    pass

                # 3. Extended Hourly Forecast
                try:
                    async with session.get(
                        f"{WEATHER_API_URL}/api/weather/forecast/hourly?hours=240",
                        timeout=10,
                    ) as resp:
                        if resp.status == 200:
                            hourly = await resp.json()
                            rest_cache["forecast_hourly"] = hourly

                            buckets = {
                                "morning": [],
                                "afternoon": [],
                                "evening": [],
                                "overnight": [],
                            }
                            local_tz = ZoneInfo("America/New_York")
                            now_ts = datetime.datetime.now(
                                datetime.timezone.utc
                            ).timestamp()

                            for h in hourly:
                                try:
                                    dt_utc = datetime.datetime.fromisoformat(
                                        h["time"].replace("Z", "+00:00")
                                    )
                                    if dt_utc.timestamp() > now_ts + 86400:
                                        continue

                                    dt_local = dt_utc.astimezone(local_tz)
                                    hr = dt_local.hour
                                    prob = int(h.get("precip_probability", 0))

                                    if 6 <= hr < 12:
                                        buckets["morning"].append(prob)
                                    elif 12 <= hr < 18:
                                        buckets["afternoon"].append(prob)
                                    elif 18 <= hr <= 23:
                                        buckets["evening"].append(prob)
                                    else:
                                        buckets["overnight"].append(prob)
                                except Exception:
                                    pass

                            w_cache = rest_cache.get("weather", {})
                            w_cache["rain_chance_morning"] = (
                                max(buckets["morning"]) if buckets["morning"] else 0
                            )
                            w_cache["rain_chance_afternoon"] = (
                                max(buckets["afternoon"]) if buckets["afternoon"] else 0
                            )
                            w_cache["rain_chance_evening"] = (
                                max(buckets["evening"]) if buckets["evening"] else 0
                            )
                            w_cache["rain_chance_overnight"] = (
                                max(buckets["overnight"]) if buckets["overnight"] else 0
                            )
                            rest_cache["weather"] = w_cache
                except Exception as h_err:
                    logger.error(f"Failed fetching hourly blocks: {h_err}")

                # 4. Crunchyroll Progress
                try:
                    async with session.get(
                        f"{CRUNCHYROLL_API_URL}/api/progress", timeout=5
                    ) as resp:
                        if resp.status == 200:
                            rest_cache["anime_progress"] = await resp.json()
                except Exception:
                    pass

                # 5. Active Flights
                try:
                    async with session.get(
                        f"{FLIGHT_API_URL}/api/flights/active", timeout=5
                    ) as resp:
                        if resp.status == 200:
                            rest_cache["active_flights"] = await resp.json()
                except Exception:
                    pass

                # 6. Sleeper Fantasy Football
                try:
                    async with session.get(
                        f"{FANTASY_API_URL}/api/sleeper", timeout=5
                    ) as resp:
                        if resp.status == 200:
                            rest_cache["sleeper"] = await resp.json()
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Microservice aggregation error: {e}")

            await asyncio.sleep(30)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing family_dashboard_api service stack...")
    sim_task = None
    cal_task = None
    microservice_task = None
    photo_task = None
    mqtt_task = None  # Replaced udp_task

    if SIMULATION_MODE:
        sim_task = asyncio.create_task(simulate_weather_stream())
        photo_task = asyncio.create_task(poll_google_drive_photos())
    else:
        cal_task = asyncio.create_task(poll_calendar_events())
        microservice_task = asyncio.create_task(poll_local_microservices())
        photo_task = asyncio.create_task(poll_google_drive_photos())
        mqtt_task = asyncio.create_task(listen_to_mqtt())  # New MQTT listener

    yield

    if sim_task:
        sim_task.cancel()
    if cal_task:
        cal_task.cancel()
    if microservice_task:
        microservice_task.cancel()
    if photo_task:
        photo_task.cancel()
    if mqtt_task:
        mqtt_task.cancel()  # Cancel MQTT on shutdown


app = FastAPI(title="Family Tactical Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
assets_path = os.path.join(BASE_DIR, "assets")
os.makedirs(assets_path, exist_ok=True)

# This exposes the assets folder to the UI container
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


@app.get("/api/dashboard/state")
async def get_dashboard_state():
    w = rest_cache.get("weather", {})
    daily = rest_cache.get("forecast_daily", [])
    dew_point = w.get("dew_point_f")
    pressure = w.get("sea_level_pressure_inhg")
    rain_rate = w.get("precip_in", 0.0)

    return {
        "weather": w,
        "comfort": calculate_comfort_level(dew_point),
        "pressure_diag": calculate_pressure_diagnostics(pressure),
        "rain_status": calculate_rain_status(rain_rate),
        "activities": calculate_activity_ratings(w, daily),
        "forecast_daily": daily,
        "anime_progress": rest_cache.get("anime_progress", []),
        "active_flights": rest_cache.get("active_flights", []),
        "daily_verse": rest_cache.get("daily_verse", {}),
    }


import datetime


@app.get("/api/tasks")
async def get_tasks():
    try:
        creds = get_calendar_credentials()
        from googleapiclient.discovery import build as tasks_build

        service = tasks_build("tasks", "v1", credentials=creds, cache_discovery=False)

        # 1. Fetch all task lists to find the internal ID for "Family"
        lists = service.tasklists().list().execute().get("items", [])
        target_id = "@default"
        for tl in lists:
            if tl["title"].strip().lower() == "family":
                target_id = tl["id"]
                break

        # 2. Fetch the tasks using the correct target ID
        tasks_result = (
            service.tasks().list(tasklist=target_id, showCompleted=False).execute()
        )
        raw_tasks = tasks_result.get("items", [])

        # 3. Format the dates so the frontend tags them correctly
        processed = []
        for t in raw_tasks:
            due_str = t.get("due")
            due_day = None
            if due_str:
                due_day = datetime.datetime.fromisoformat(due_str.split("T")[0]).date()

            processed.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title", "Unnamed Task"),
                    "notes": t.get("notes", ""),
                    "due_date_str": due_day.isoformat() if due_day else None,
                }
            )

        # Sort by due date (tasks with no due date go to the bottom)
        processed.sort(
            key=lambda x: x["due_date_str"] if x["due_date_str"] else "9999-12-31"
        )
        return processed

    except Exception as e:
        logger.error(f"Google Tasks endpoint error: {e}")
        return []


@app.get("/api/photos")
async def get_photos():
    photo_dir = os.path.join(BASE_DIR, "assets", "photos")
    if not os.path.exists(photo_dir):
        os.makedirs(photo_dir)
    files_on_disk = [f for f in os.listdir(photo_dir) if not f.startswith(".")]
    urls = [f"/assets/photos/{f}" for f in files_on_disk]
    return {"urls": urls}


@app.get("/api/sleeper")
async def get_sleeper_node_data():
    return rest_cache.get("sleeper", {"mode": "disabled"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
