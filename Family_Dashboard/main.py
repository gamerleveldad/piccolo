import argparse
import asyncio
import socket
import json
import math
import random
import os
import datetime
import logging
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import io
import html
import re
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from googleapiclient.http import MediaIoBaseDownload
from google.genai import Client
from google.genai.errors import APIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dashboard")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="Tactical Weather Dashboard Backend")
parser.add_argument('--simulate', action='store_true', help="Run the telemetry simulator instead of live UDP.")
args, _ = parser.parse_known_args()

SIMULATION_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true" or args.simulate

STATION_ID = int(os.getenv("STATION_ID", 222180))
API_TOKEN = os.getenv("WEATHER_API_TOKEN")
API_TOKEN_BIBLE = os.getenv("BIBLE_API_TOKEN")
LATITUDE = float(os.getenv("LATITUDE", 28.66))
LONGITUDE = float(os.getenv("LONGITUDE", -81.36))

if not SIMULATION_MODE and (not API_TOKEN or not API_TOKEN_BIBLE):
    logger.warning("CRITICAL: API Tokens are missing from the environment configuration.")

rest_cache = {
    "pressure_trend": "Steady",
    "rain_accumulation_day_in": 0.0,
    "rain_rate_in_hr": 0.0,
    "forecast_daily_api": None,
    "icon_api": "clear-day",  
    "conditions": "Clear",
    "alerts": [],
    "display_photos": [],
    "rain_chance_current": 0,
    "rain_chance_morning": 0,
    "rain_chance_afternoon": 0,
    "rain_chance_evening": 0,
    "rain_chance_overnight": 0,
    "daily_verse": {
        "reference": "Psalm 119:105",
        "text": "Your word is a lamp to guide my feet and a light for my path."
    }
}

TEMPEST_FORECAST_CACHE = {}

async def fetch_nws_alerts(session: aiohttp.ClientSession) -> list:
    headers = {'User-Agent': '(MyTacticalWeatherDashboard, admin@domain.com)'}
    url = f"https://api.weather.gov/alerts/active?point={LATITUDE},{LONGITUDE}"
    try:
        async with session.get(url, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                features = data.get("features", [])
                ui_alerts = []
                for feature in features:
                    props = feature.get("properties", {})
                    ui_alerts.append({
                        "id": props.get("id"),
                        "event": props.get("event"),
                        "severity": props.get("severity"),
                        "urgency": props.get("urgency"),
                        "description": props.get("description"),
                        "senderName": props.get("senderName"),
                        "ends": props.get("ends")
                    })
                return ui_alerts
    except Exception as e:
        logger.error(f"Failed to reach NWS active hazard registry: {e}")
    return []

async def get_tempest_hourly_forecast(location_string=None):
    cache_key = "home_station_forecast"
    if cache_key in TEMPEST_FORECAST_CACHE:
        timestamp, cached_periods = TEMPEST_FORECAST_CACHE[cache_key]
        if (datetime.datetime.now() - timestamp).total_seconds() < 1800:
            return cached_periods

    url = "https://swd.weatherflow.com/swd/rest/better_forecast"
    params = {"station_id": STATION_ID, "token": API_TOKEN, "units_temp": "f", "units_precip": "in"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=6) as response:
                if response.status == 200:
                    data = await response.json()
                    hourly_periods = data.get("forecast", {}).get("hourly", [])
                    TEMPEST_FORECAST_CACHE[cache_key] = (datetime.datetime.now(), hourly_periods)
                    return hourly_periods
    except Exception as e:
        logger.error(f"Tempest Forecast API Fetch Error: {e}")
    return None

def match_tempest_weather(event_start_iso, hourly_periods):
    if not hourly_periods: return None
    try:
        event_dt = datetime.datetime.fromisoformat(event_start_iso.replace('Z', '+00:00'))
        event_ts = int(event_dt.timestamp())
    except Exception:
        return None

    for period in hourly_periods:
        p_time_raw = period.get("time")
        if p_time_raw is not None:
            try:
                p_time = int(p_time_raw)
                if p_time <= event_ts < (p_time + 3600):
                    return {
                        "temp": int(period.get("air_temperature", 72)),
                        "condition": period.get("conditions", "Clear"),
                        "icon": period.get("icon", "clear-day"), 
                        "rain_pct": int(period.get("precip_probability", 0))
                    }
            except (ValueError, TypeError):
                continue
    return None

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/tasks', 'https://www.googleapis.com/auth/drive.readonly']

GOOGLE_COLOR_MAP = {
    "1": "#a4bdfc", "2": "#7ae7bf", "3": "#dbadff", "4": "#ff887c",
    "5": "#fbd75b", "6": "#ffb878", "7": "#46d6db", "8": "#e1e1e1",
    "9": "#5484ed", "10": "#51b749", "11": "#dc2127"
}

CALENDAR_TARGETS = {
    "display_board": "810d2e7891b3be1da204c04a0959229aa41467ae7b110d83f72343ec7b1490e0@group.calendar.google.com",
    "family": "family08995171228833928146@group.calendar.google.com",
    "holidays": "en.usa#holiday@group.v.calendar.google.com"
}

def get_calendar_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

async def poll_calendar_events():
    logger.info("Calendar synchronization worker spawned.")
    while True:
        try:
            creds = get_calendar_credentials()
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
            now = datetime.datetime.now(datetime.timezone.utc)
            time_min = now.isoformat()
            time_max = (now + datetime.timedelta(days=28)).isoformat()
            
            aggregated_events = []
            for source_tag, cal_id in CALENDAR_TARGETS.items():
                events_result = service.events().list(
                    calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                for e in events:
                    start_data = e['start'].get('dateTime', e['start'].get('date'))
                    is_all_day = 'date' in e['start'] and 'dateTime' not in e['start']
                    location = e.get('location')
                    
                    event_forecast = None
                    if not is_all_day and start_data:
                        hourly_data = await get_tempest_hourly_forecast(location)
                        event_forecast = match_tempest_weather(start_data, hourly_data)
                    
                    raw_color_id = e.get('colorId')
                    event_color = e.get('backgroundColor', GOOGLE_COLOR_MAP.get(raw_color_id, "#38bdf8"))
                    
                    aggregated_events.append({
                        "id": e.get('id'),
                        "summary": e.get('summary', 'Untitled Event'),
                        "start": start_data,
                        "location": location,
                        "is_all_day": is_all_day,
                        "color": event_color,
                        "source": source_tag,
                        "forecast": event_forecast
                    })
            
            await manager.broadcast(json.dumps({
                "update_type": "calendar_sync",
                "events": aggregated_events
            }))
        except Exception as err:
            logger.error(f"Calendar Thread Error: {err}")
        await asyncio.sleep(300)

async def poll_google_drive_photos():
    logger.info("Google Drive Photo sync worker spawned.")
    photo_dir = os.path.join(BASE_DIR, "assets", "photos")
    os.makedirs(photo_dir, exist_ok=True)
    MIME_MAP = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}
    
    while True:
        try:
            def sync_logic():
                creds = get_calendar_credentials()
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                
                service = build('drive', 'v3', credentials=creds, cache_discovery=False)
                results = service.files().list(q="mimeType='application/vnd.google-apps.folder' and name='DisplayBoard' and trashed=false", fields="files(id, name)").execute()
                folders = results.get('files', [])
                if not folders: return
                    
                folder_id = folders[0]['id']
                results = service.files().list(q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false", fields="files(id, name, mimeType)").execute()
                cloud_images = results.get('files', [])
                
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
                
                local_filenames = set([f for f in os.listdir(photo_dir) if not f.startswith('.')])
                for local_file in local_filenames:
                    if local_file not in cloud_safe_names:
                        os.remove(os.path.join(photo_dir, local_file))
                        
                for safe_name, img in cloud_safe_names.items():
                    if safe_name not in local_filenames:
                        request = service.files().get_media(fileId=img['id'])
                        fh = io.FileIO(os.path.join(photo_dir, safe_name), 'wb')
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while done is False:
                            status, done = downloader.next_chunk()
            await asyncio.to_thread(sync_logic)
        except Exception as e:
            logger.error(f"Drive Sync error: {e}", exc_info=True)
        await asyncio.sleep(3600)

TASK_LIST_NAME = "Family"
def get_target_tasklist_id(service):
    lists = service.tasklists().list().execute().get('items', [])
    for tl in lists:
        if tl['title'].strip().lower() == TASK_LIST_NAME.lower():
            return tl['id']
    return '@default'

async def fetch_active_chores():
    if SIMULATION_MODE:
        return [
            {"id": "1", "title": "Mock: Wash car", "notes": "", "due_date_str": datetime.date.today().isoformat(), "is_today": True},
            {"id": "2", "title": "Mock: Buy groceries", "notes": "", "due_date_str": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(), "is_today": False}
        ]
        
    try:
        creds = get_calendar_credentials()
        from googleapiclient.discovery import build as tasks_build
        service = tasks_build('tasks', 'v1', credentials=creds, cache_discovery=False)
        list_id = get_target_tasklist_id(service)
        tasks_result = service.tasks().list(tasklist=list_id, showCompleted=False).execute()
        raw_tasks = tasks_result.get('items', [])
        
        processed_tasks = []
        now_date = datetime.date.today()
        horizon_date = now_date + datetime.timedelta(days=2) 
        
        for t in raw_tasks:
            due_str = t.get('due')
            due_day = None
            if due_str:
                due_day = datetime.date.fromisoformat(due_str.split('T')[0])
            
            if not due_day or due_day <= horizon_date:
                processed_tasks.append({
                    "id": t.get('id'),
                    "title": t.get('title', 'Unnamed Task'),
                    "notes": t.get('notes', ''),
                    "due": due_str,
                    "due_date_str": due_day.isoformat() if due_day else None,
                    "is_today": due_day == now_date if due_day else False,
                    "is_tomorrow": due_day == (now_date + datetime.timedelta(days=1)) if due_day else False
                })
        processed_tasks.sort(key=lambda x: x["due_date_str"] if x["due_date_str"] is not None else "9999-12-31")
        return processed_tasks
    except Exception as e:
        logger.error(f"Tasks Module Fetch Error: {e}")
        return []

SLEEPER_LEAGUE_ID = "1360812344053071872"
async def get_sleeper_dashboard_payload():
    if SIMULATION_MODE:
        return {"mode": "disabled"}

    url_league = f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url_league) as resp:
            if resp.status != 200: return {"mode": "disabled"}
            league_data = await resp.json()
            
        if league_data.get("status") == "pre_draft":
            url_drafts = f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/drafts"
            async with session.get(url_drafts) as d_resp:
                drafts = await d_resp.json()
                if drafts:
                    return {
                        "mode": "draft",
                        "name": league_data.get("name"),
                        "draft_start": drafts[0].get("start_time")
                    }

        current_week = league_data.get("settings", {}).get("leg", 1)
        async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/users") as u_resp:
            users = await u_resp.json()
            user_map = {u['user_id']: u.get('metadata', {}).get('team_name', u['display_name']) for u in users}
            
        async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/rosters") as r_resp:
            rosters = await r_resp.json()
            roster_to_owner = {r['roster_id']: user_map.get(r['owner_id'], f"Team {r['roster_id']}") for r in rosters}

        async with session.get(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/matchups/{current_week}") as m_resp:
            matchups_raw = await m_resp.json()

        match_groups = {}
        for team in matchups_raw:
            m_id = team.get("matchup_id")
            if m_id not in match_groups: match_groups[m_id] = []
            match_groups[m_id].append({
                "owner_name": roster_to_owner.get(team['roster_id'], "Unknown"),
                "points": team.get("points", 0.0),
                "projected_points": sum(team.get("starters_points", [0])),
                "starters": team.get("starters", []),
                "players": team.get("players", []),
                "custom_roster_points_map": team.get("players_points", {})
            })

        return {"mode": "matchups", "week": current_week, "matchups": list(match_groups.values())}

async def poll_daily_bible_verse():
    while True:
        global rest_cache
        yday = datetime.datetime.now().timetuple().tm_yday
        url_votd = f"https://api.youversion.com/v1/verse_of_the_days/{yday}"
        headers_yv = {"X-YVP-App-Key": API_TOKEN_BIBLE, "x-youversion-developer-token": API_TOKEN_BIBLE, "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_votd, headers=headers_yv, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        passage_id = data.get("passage_id") 
                        if passage_id:
                            nlt_url = "https://api.nlt.to/api/passages"
                            nlt_params = {"ref": passage_id, "version": "NLT", "key": "TEST"}
                            async with session.get(nlt_url, params=nlt_params, timeout=10) as nlt_resp:
                                if nlt_resp.status == 200:
                                    html_content = await nlt_resp.text()
                                    title_match = re.search(r'<h2.*?>(.*?)</h2>', html_content)
                                    clean_ref = html.unescape(title_match.group(1)).replace(', NLT', '') if title_match else passage_id
                                    html_content = re.sub(r'<h2.*?</h2>', '', html_content)
                                    html_content = re.sub(r'<span class="vn">.*?</span>', '', html_content)
                                    html_content = re.sub(r'<br\s*/?>', ' ', html_content)
                                    clean_text = re.sub(r'<[^>]+>', '', html_content)
                                    clean_text = html.unescape(clean_text).strip()
                                    clean_text = re.sub(r'\s+', ' ', clean_text) 
                                    clean_text = re.sub(r'^NLT API\s*', '', clean_text).strip()
                                    rest_cache["daily_verse"] = {"reference": clean_ref, "text": clean_text}
        except Exception as e:
            logger.error(f"Error fetching Daily Verse: {e}", exc_info=True)    
        await asyncio.sleep(14400)

async def poll_tempest_rest_api():
    url = f"https://swd.weatherflow.com/swd/rest/better_forecast"
    params = {"station_id": STATION_ID, "token": API_TOKEN, "units_temp": "f", "units_wind": "mph", "units_pressure": "inhg", "units_precip": "in"}
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                nws_alerts = await fetch_nws_alerts(session)
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        current = data.get("current_conditions", {})
                        global rest_cache
                        rest_cache["alerts"] = nws_alerts
                        rest_cache["pressure_trend"] = current.get("pressure_trend", "Steady")
                        rest_cache["rain_accumulation_day_in"] = float(current.get("precip_accum_local_day", 0.0))
                        
                        rest_cache["icon_api"] = current.get("icon", "clear-day")
                        rest_cache["conditions"] = current.get("conditions", "Clear")
                        
                        hourly = data.get("forecast", {}).get("hourly", [])
                        if hourly:
                            rest_cache["rain_chance_current"] = hourly[0].get("precip_probability", 0)
                            buckets = {"morning": [], "afternoon": [], "evening": [], "overnight": []}
                            now_ts = datetime.datetime.now().timestamp()
                            for h in hourly:
                                if h["time"] > now_ts + 86400: continue 
                                dt = datetime.datetime.fromtimestamp(h["time"])
                                hr = dt.hour
                                prob = h.get("precip_probability", 0)
                                if 6 <= hr < 12: buckets["morning"].append(prob)
                                elif 12 <= hr < 18: buckets["afternoon"].append(prob)
                                elif 18 <= hr <= 23: buckets["evening"].append(prob)
                                else: buckets["overnight"].append(prob)
                            rest_cache["rain_chance_morning"] = max(buckets["morning"]) if buckets["morning"] else 0
                            rest_cache["rain_chance_afternoon"] = max(buckets["afternoon"]) if buckets["afternoon"] else 0
                            rest_cache["rain_chance_evening"] = max(buckets["evening"]) if buckets["evening"] else 0
                            rest_cache["rain_chance_overnight"] = max(buckets["overnight"]) if buckets["overnight"] else 0

                        raw_days = data.get("forecast", {}).get("daily", [])
                        parsed_days = []
                        for day in raw_days:
                            parsed_days.append({
                                "day_name": day.get("day_start_local", "Day"),
                                "icon": day.get("icon", "clear-day"),
                                "high": int(day.get("air_temp_high", 75)),
                                "low": int(day.get("air_temp_low", 60)),
                                "rain_pct": int(day.get("precip_probability", 0)),
                                "sunrise": day.get("sunrise"),
                                "sunset": day.get("sunset")
                            })
                        if parsed_days:
                            rest_cache["forecast_daily_api"] = parsed_days
                        await asyncio.sleep(300)
                    elif response.status == 429:
                        await asyncio.sleep(60)
                    else:
                        await asyncio.sleep(60)
        except Exception as e:
            await asyncio.sleep(10)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

def c_to_f(c_temp: float) -> float: return round((c_temp * 9/5) + 32, 1)
def mps_to_mph(mps_speed: float) -> float: return round(mps_speed * 2.23694, 1)
def mb_to_inhg(mb_pressure: float) -> float: return round(mb_pressure * 0.02953, 2)
def mm_to_inches(mm_rain: float) -> float: return round(mm_rain * 0.0393701, 2)

def calculate_dew_point(temp_c: float, rh: float) -> float:
    a = 17.625
    b = 243.04
    alpha = ((a * temp_c) / (b + temp_c)) + math.log(rh / 100.0)
    dew_point_c = (b * alpha) / (a - alpha)
    return c_to_f(dew_point_c)

def calculate_feels_like(temp_f: float, rh: float, wind_mph: float) -> float:
    if temp_f >= 80.0:
        hi = (-42.379 + 2.04901523 * temp_f + 10.14333127 * rh - 0.22475541 * temp_f * rh -
              6.83783e-3 * temp_f**2 - 5.481717e-2 * rh**2 + 1.22874e-3 * temp_f**2 * rh +
              8.5282e-4 * temp_f * rh**2 - 1.99e-6 * temp_f**2 * rh**2)
        if rh < 13 and 80 <= temp_f <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(temp_f - 95)) / 17)
        elif rh > 85 and 80 <= temp_f <= 87:
            hi += ((rh - 85) / 10) * ((87 - temp_f) / 5)
        return round(hi, 1)
    elif temp_f <= 50.0 and wind_mph > 3.0:
        wc = 35.74 + (0.6215 * temp_f) - (35.75 * (wind_mph**0.16)) + (0.4275 * temp_f * (wind_mph**0.16))
        return round(wc, 1)
    return round(temp_f, 1)

def parse_tempest_packet(raw_packet: dict) -> dict | None:
    packet_type = raw_packet.get("type")
    if packet_type == "rapid_wind":
        ob = raw_packet.get("ob", [])
        if not ob: return None
        return {
            "update_type": "rapid_wind",
            "wind_speed_mph": mps_to_mph(ob[1]),
            "wind_direction_deg": ob[2],
            "icon_api": rest_cache["icon_api"],
            "conditions": rest_cache["conditions"]
        }
    elif packet_type == "evt_strike":
        evt = raw_packet.get("evt", [])
        if not evt: return None
        distance_km = float(evt[1])
        distance_miles = round(distance_km * 0.621371, 1)
        return {
            "update_type": "lightning_strike",
            "distance_miles": distance_miles,
            "energy": evt[2],
            "timestamp": raw_packet.get("timestamp")
        }
    elif packet_type == "obs_st":
        obs_list = raw_packet.get("obs", [])
        if not obs_list or not obs_list[0]: return None
        obs = obs_list[0]
        temp_c = obs[7]
        rh = obs[8]
        
        rain_min_mm = obs[12]
        rain_rate_in_hr = round(mm_to_inches(rain_min_mm) * 60, 2)
        rest_cache["rain_rate_in_hr"] = rain_rate_in_hr

        return {
            "update_type": "sensor_snapshot",
            "wind_lull_mph": mps_to_mph(obs[1]),
            "wind_avg_mph": mps_to_mph(obs[2]),
            "wind_gust_mph": mps_to_mph(obs[3]),
            "wind_direction_deg": obs[4],
            "pressure_inhg": mb_to_inhg(obs[6]),
            "temperature_f": c_to_f(temp_c),
            "feels_like_f": calculate_feels_like(c_to_f(temp_c), rh, mps_to_mph(obs[2])),
            "humidity_pct": rh,
            "dew_point_f": calculate_dew_point(temp_c, rh),
            "uv_index": obs[10],
            "lightning_count": obs[15],
            
            "pressure_trend_api": rest_cache["pressure_trend"],
            "rain_accumulation_day_in": rest_cache["rain_accumulation_day_in"],
            "rain_rate_in_hr": rain_rate_in_hr,
            "rain_chance_current": rest_cache.get("rain_chance_current", 0),
            "rain_chance_morning": rest_cache.get("rain_chance_morning", 0),
            "rain_chance_afternoon": rest_cache.get("rain_chance_afternoon", 0),
            "rain_chance_evening": rest_cache.get("rain_chance_evening", 0),
            "rain_chance_overnight": rest_cache.get("rain_chance_overnight", 0),
            "icon_api": rest_cache["icon_api"],
            "conditions": rest_cache["conditions"],
            "alerts": rest_cache["alerts"],
            "daily_verse": rest_cache.get("daily_verse", {})  
        }
    return None

async def simulate_weather_stream():
    logger.info("Simulation Matrix Engine online: 100% Mock Data Generation Active")
    global rest_cache
    sim_temp = 74.5
    sim_rh = 72.0
    sim_heading = 270
    sim_pressure = 29.92
    sim_rain_accum = 0.5
    
    now = datetime.datetime.now()
    mock_events = [{
        "id": "mock1", "summary": "Mock: Pathfinder RPG", "start": (now + datetime.timedelta(hours=2)).isoformat(),
        "location": None, "is_all_day": False, "color": "#a4bdfc", "source": "family", "forecast": {"temp": 75, "icon": "clear-day", "rain_pct": 10}
    }]
    
    # Calculate mock sunrise/sunset to test driving glare logic
    sunrise_ts = int(now.replace(hour=6, minute=30, second=0).timestamp())
    sunset_ts = int(now.replace(hour=20, minute=0, second=0).timestamp())
    
    while True:
        try:
            sim_temp += random.uniform(-1.5, 1.5)
            sim_rh = max(min(sim_rh + random.uniform(-5.0, 5.0), 99.0), 15.0)
            sim_pressure += random.uniform(-0.04, 0.04)
            sim_heading = (sim_heading + random.randint(-40, 40)) % 360
            
            base_wind = round(random.uniform(5.0, 20.0), 1)
            gust_wind = round(base_wind * random.uniform(1.2, 2.0), 1)
            pressure_shift = random.choice(["Falling", "Rising", "Steady"])
            
            if random.random() < 0.25:
                sim_rain_rate = round(random.uniform(0.3, 2.5), 2)
            elif random.random() < 0.50:
                sim_rain_rate = round(random.uniform(0.01, 0.15), 2)
            else:
                sim_rain_rate = 0.0
                
            if sim_rain_rate > 0:
                sim_rain_accum += (sim_rain_rate / 3600) * 5.5

            if sim_rain_rate > 0.5:
                icon_api, conditions = "thunderstorm", "Thunderstorms"
            elif sim_rain_rate > 0:
                icon_api, conditions = "rainy", "Raining"
            elif sim_temp > 82.0:
                icon_api = random.choice(["clear-day", "partly-cloudy-day"])
                conditions = "Sunny" if icon_api == "clear-day" else "Partly Cloudy"
            else:
                icon_api = random.choice(["clear-day", "partly-cloudy-day", "cloudy"])
                conditions = "Mostly Clear" if icon_api == "clear-day" else "Overcast"

            temp_c_equivalent = (sim_temp - 32) * 5/9
            
            sim_payload = {
                "update_type": "sensor_snapshot",
                "temperature_f": round(sim_temp, 1),
                "humidity_pct": round(sim_rh),
                "dew_point_f": calculate_dew_point(temp_c_equivalent, sim_rh),
                "feels_like_f": calculate_feels_like(sim_temp, sim_rh, base_wind),
                "pressure_inhg": round(sim_pressure, 2),
                "wind_speed_mph": base_wind,
                "wind_direction_deg": int(sim_heading),
                "wind_gust_mph": gust_wind,
                "uv_index": 6 if sim_temp > 75 else 2,
                "lightning_count": random.randint(1, 5) if icon_api == "thunderstorm" else 0,
                
                "icon_api": icon_api,
                "conditions": conditions,
                "pressure_trend_api": pressure_shift,
                "rain_accumulation_day_in": round(sim_rain_accum, 2),
                "rain_rate_in_hr": sim_rain_rate,
                "rain_chance_current": random.randint(40, 95) if sim_rain_rate > 0 else random.randint(0, 15),
                "rain_chance_morning": random.randint(10, 80),
                "rain_chance_afternoon": random.randint(20, 95),
                "rain_chance_evening": random.randint(10, 90),
                "rain_chance_overnight": random.randint(0, 50),
                "alerts": rest_cache.get("alerts", []),
                "daily_verse": {"reference": "Simulation 1:1", "text": "This is simulated environment data generating actively."},
                "forecast_daily_api": [
                    {"day_name": "Mon", "icon": "clear-day", "high": 92, "low": 75, "rain_pct": 10, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Tue", "icon": "partly-cloudy-day", "high": 90, "low": 76, "rain_pct": 25, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Wed", "icon": "rainy", "high": 86, "low": 74, "rain_pct": 80, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Thu", "icon": "thunderstorm", "high": 85, "low": 73, "rain_pct": 95, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Fri", "icon": "partly-cloudy-day", "high": 89, "low": 75, "rain_pct": 40, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Sat", "icon": "clear-day", "high": 93, "low": 77, "rain_pct": 5, "sunrise": sunrise_ts, "sunset": sunset_ts},
                    {"day_name": "Sun", "icon": "clear-day", "high": 94, "low": 76, "rain_pct": 0, "sunrise": sunrise_ts, "sunset": sunset_ts}
                ]
            }
            
            rest_cache["pressure_trend"] = sim_payload["pressure_trend_api"]
            rest_cache["rain_accumulation_day_in"] = sim_payload["rain_accumulation_day_in"]
            rest_cache["rain_rate_in_hr"] = sim_payload["rain_rate_in_hr"]
            rest_cache["icon_api"] = icon_api
            rest_cache["conditions"] = conditions

            sim_wind = {
                "update_type": "rapid_wind",
                "wind_speed_mph": base_wind,
                "wind_direction_deg": int(sim_heading),
                "icon_api": icon_api,
                "conditions": conditions
            }
            
            await manager.broadcast(json.dumps({"update_type": "calendar_sync", "events": mock_events}))
            await manager.broadcast(json.dumps(sim_wind))
            await asyncio.sleep(3.0)
            
            if random.random() < 0.20:
                sim_strike = {
                    "update_type": "lightning_strike", 
                    "distance_miles": round(random.uniform(2.0, 25.0), 1), 
                    "energy": random.randint(1000, 15000), 
                    "timestamp": int(datetime.datetime.now().timestamp())
                }
                await manager.broadcast(json.dumps(sim_strike))

            await manager.broadcast(json.dumps(sim_payload))
            await asyncio.sleep(2.5)
            
        except Exception as e:
            logger.error(f"Simulator Engine Crash: {e}", exc_info=True)
            await asyncio.sleep(2)

async def listen_to_tempest_udp():
    UDP_IP = ""       
    UDP_PORT = 50222         
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)
    
    loop = asyncio.get_event_loop()
    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 1024)
            raw_str = data.decode('utf-8')
            raw_json = json.loads(raw_str)
            clean_data = parse_tempest_packet(raw_json)
            if clean_data:
                clean_data["forecast_daily_api"] = rest_cache["forecast_daily_api"]
                await manager.broadcast(json.dumps(clean_data))
        except Exception as e:
            logger.error(f"UDP Processing Error: {e}", exc_info=True)
            await asyncio.sleep(0.1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    sim_task = None
    if SIMULATION_MODE:
        logger.info("Local Simulator Active. External APIs halted.")
        sim_task = asyncio.create_task(simulate_weather_stream())
    else:
        udp_task = asyncio.create_task(listen_to_tempest_udp())
        rest_task = asyncio.create_task(poll_tempest_rest_api())
        cal_task = asyncio.create_task(poll_calendar_events())
        photo_task = asyncio.create_task(poll_google_drive_photos())
        verse_task = asyncio.create_task(poll_daily_bible_verse())
        
    yield
    
    if SIMULATION_MODE and sim_task:
        sim_task.cancel()
    elif not SIMULATION_MODE:
        udp_task.cancel()
        rest_task.cancel()
        cal_task.cancel()
        photo_task.cancel()
        verse_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/tasks")
async def get_tasks():
    chores = await fetch_active_chores()
    return chores

@app.get("/api/sleeper")
async def get_sleeper_node_data():
    payload = await get_sleeper_dashboard_payload()
    return payload

@app.get("/api/photos")
async def get_photos():
    if SIMULATION_MODE: return {"urls": []}
    photo_dir = os.path.join(BASE_DIR, "assets", "photos")
    if not os.path.exists(photo_dir): os.makedirs(photo_dir)
    files_on_disk = [f for f in os.listdir(photo_dir) if not f.startswith('.')]
    urls = [f"/assets/photos/{f}" for f in files_on_disk]
    return {"urls": urls}

@app.post("/api/tasks/complete/{task_id}")
async def complete_and_delete_task(task_id: str):
    if SIMULATION_MODE: return {"status": "success"}
    try:
        creds = get_calendar_credentials()
        from googleapiclient.discovery import build as tasks_build
        service = tasks_build('tasks', 'v1', credentials=creds, cache_discovery=False)
        list_id = get_target_tasklist_id(service)
        task = service.tasks().get(tasklist=list_id, task=task_id).execute()
        task['status'] = 'completed'
        service.tasks().update(tasklist=list_id, task=task_id, body=task).execute()
        service.tasks().delete(tasklist=list_id, task=task_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

assets_path = os.path.join(BASE_DIR, "assets")
static_path = os.path.join(BASE_DIR, "static")
os.makedirs(assets_path, exist_ok=True)
os.makedirs(os.path.join(assets_path, "photos"), exist_ok=True)
os.makedirs(static_path, exist_ok=True)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    if full_path.startswith("api/"): return {"error": "API Route Not Found"}
    static_file = os.path.join(static_path, full_path)
    if os.path.isfile(static_file): return FileResponse(static_file)
    if full_path.startswith("assets/"):
        backend_asset = os.path.join(assets_path, full_path.replace("assets/", "", 1))
        if os.path.isfile(backend_asset): return FileResponse(backend_asset)
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file): return FileResponse(index_file)
    return {"error": "React build not found. Run deploy.bat to compile."}