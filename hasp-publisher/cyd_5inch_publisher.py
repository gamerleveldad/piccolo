#!/usr/bin/env python3
"""
openHASP 5-Inch (800x480) Telemetry Publisher for Piccolo (Raspberry Pi 5)
Mapped directly to Piccolo's Weather_API routes:
  - /api/weather/current
  - /api/weather/advanced/current
  - /api/weather/aviation
  - /api/weather/forecast/hourly
  - /api/weather/forecast/daily
Plus live MQTT rapid_wind/strike updates from tempest_bridge and ADS-B from ultrafeeder.
"""

import json
import math
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
HASP_NODE = os.getenv("HASP_NODE", "plate_5inch")

TEMPEST_MQTT_TOPIC = os.getenv("TEMPEST_MQTT_TOPIC", "tempest/#")

HOME_LAT = float(os.getenv("HOME_LATITUDE", "28.6611"))
HOME_LON = float(os.getenv("HOME_LONGITUDE", "-81.3656"))

AIRCRAFT_JSON_URL = os.getenv("AIRCRAFT_JSON_URL", "http://ultrafeeder:80/data/aircraft.json")
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather_api:8000").rstrip("/")
METAR_URL = "https://aviationweather.gov/api/data/metar?ids=KSFB,KORL&format=json"

PROXIMITY_RADIUS_NM = 3.0
ALERT_DISPLAY_SECONDS = 10
AIRCRAFT_COOLDOWN_SECONDS = 300

FLIGHT_CAT_COLORS = {
    "VFR": "#2dd4bf",   # Teal/Green
    "MVFR": "#38bdf8",  # Sky Blue
    "IFR": "#ef4444",   # Red
    "LIFR": "#e879f9",  # Magenta
}

# ==============================================================================
# LIVE TELEMETRY STATE
# ==============================================================================
weather_state = {
    # From /api/weather/current
    "temp_f": None,
    "feels_like_f": None,
    "dew_point_f": None,
    "relative_humidity": None,
    "wind_avg_mph": 0.0,
    "wind_gust_mph": 0.0,
    "wind_direction": "",
    "wind_deg": None,
    "precip_in": 0.0,
    "rain_rate_in_hr": 0.0,
    "sea_level_pressure_inhg": None,
    "uv_index": 0.0,
    "solar_radiation": 0,
    "lightning_strike_count": 0,
    "lightning_strike_last_distance": None,
    "lightning_last_time": "None",
    "conditions": "Loading...",
    "icon": "partly-cloudy-day",
    # From /api/weather/advanced/current
    "wbgt_f": None,
    "vpd_kpa": None,
    "delta_t_c": None,
    "air_density_kg_m3": None,
    "illuminance_lux": 0,
    # From /api/weather/aviation
    "density_altitude_ft": 0,
    "station_pressure_inhg": None,
    "station_pressure_mb": None,
    # Derived & Forecast
    "pressure_trend": "Steady",
    "hourly": [],
    "daily": [],
}

seen_close_aircraft = {}
revert_page_at = None
previous_page = 1
last_metar_fetch = 0
last_api_current_fetch = 0
last_api_forecast_fetch = 0
last_weather_push = 0
cached_metar_cmds = []
pressure_history = []  # [(timestamp, slp_inhg)]


# ==============================================================================
# ICON & GEOSPATIAL HELPERS
# ==============================================================================
def resolve_mdi_icon(icon_str: str) -> str:
    """Maps Tempest/WeatherFlow icon strings (e.g. 'possibly-thunderstorm-day') to openHASP MDI unicodes."""
    s = (icon_str or "").lower()
    if "thunder" in s or "lightning" in s or "tstorm" in s:
        return "\uF593"  # Thunderstorm
    if "rain" in s or "shower" in s or "drizzle" in s or "sleet" in s:
        return "\uF597"  # Rain
    if "wind" in s:
        return "\uF5A0"  # Windy
    if "partly-cloudy" in s:
        return "\uF595"  # Partly Cloudy
    if "cloudy" in s or "overcast" in s or "fog" in s:
        return "\uF590"  # Cloudy
    if "night" in s:
        return "\uF594"  # Clear Night (Moon)
    if "clear" in s or "sun" in s:
        return "\uF599"  # Clear Day (Sun)
    return "\uF595"


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * r_nm * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - (
        math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    )
    return int((math.degrees(math.atan2(x, y)) + 360) % 360)


def deg_to_cardinal(deg: float) -> str:
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    return dirs[round(deg / 22.5) % 16]


def calculate_sun_times(lat: float, lon: float) -> tuple[str, str]:
    """Calculates today's local Sunrise and Sunset times using NOAA solar equations."""
    now = datetime.now()
    day_of_year = now.timetuple().tm_yday
    tz_offset = now.astimezone().utcoffset().total_seconds() / 3600.0

    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
    )
    lat_rad = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_rad) * math.cos(decl))) - (
        math.tan(lat_rad) * math.tan(decl)
    )
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha_deg = math.degrees(math.acos(cos_ha))

    sunrise_min = 720.0 - 4.0 * (lon + ha_deg) - eqtime + tz_offset * 60.0
    sunset_min = 720.0 - 4.0 * (lon - ha_deg) - eqtime + tz_offset * 60.0

    def fmt_min(m: float) -> str:
        m = int(round(m)) % 1440
        hr, mn = divmod(m, 60)
        dt = now.replace(hour=hr, minute=mn)
        return dt.strftime("%I:%M %p").lstrip("0")

    return fmt_min(sunrise_min), fmt_min(sunset_min)


# ==============================================================================
# POLL LOCAL WEATHER_API ENDPOINTS
# ==============================================================================
def poll_current_weather_apis():
    """
    Polls the 3 real-time endpoints on weather_api:
      1. /api/weather/current
      2. /api/weather/advanced/current
      3. /api/weather/aviation
    """
    global weather_state, pressure_history

    # 1. /api/weather/current
    try:
        r = requests.get(f"{WEATHER_API_URL}/api/weather/current", timeout=3)
        r.raise_for_status()
        cur = r.json()
        if cur.get("temp_f") is not None:
            weather_state["temp_f"] = float(cur["temp_f"])
        if cur.get("feels_like_f") is not None:
            weather_state["feels_like_f"] = float(cur["feels_like_f"])
        if cur.get("dew_point_f") is not None:
            weather_state["dew_point_f"] = float(cur["dew_point_f"])
        if cur.get("relative_humidity") is not None:
            weather_state["relative_humidity"] = int(round(float(cur["relative_humidity"])))
        if cur.get("wind_avg_mph") is not None:
            weather_state["wind_avg_mph"] = float(cur["wind_avg_mph"])
        if cur.get("wind_gust_mph") is not None:
            weather_state["wind_gust_mph"] = float(cur["wind_gust_mph"])
        if cur.get("wind_direction"):
            weather_state["wind_direction"] = str(cur["wind_direction"]).strip()
        if cur.get("precip_in") is not None:
            weather_state["precip_in"] = float(cur["precip_in"])
        if cur.get("sea_level_pressure_inhg") is not None:
            slp = float(cur["sea_level_pressure_inhg"])
            weather_state["sea_level_pressure_inhg"] = slp
            now_ts = time.time()
            pressure_history.append((now_ts, slp))
            pressure_history = [(t, p) for t, p in pressure_history if now_ts - t <= 10800]
            if len(pressure_history) >= 2:
                delta = slp - pressure_history[0][1]
                if delta >= 0.03:
                    weather_state["pressure_trend"] = f"Rising ({delta:+.2f})"
                elif delta <= -0.03:
                    weather_state["pressure_trend"] = f"Falling ({delta:+.2f})"
                else:
                    weather_state["pressure_trend"] = f"Steady ({delta:+.2f})"
        if cur.get("uv_index") is not None:
            weather_state["uv_index"] = float(cur["uv_index"])
        if cur.get("solar_radiation") is not None:
            weather_state["solar_radiation"] = int(round(float(cur["solar_radiation"])))
        if cur.get("lightning_strike_count") is not None:
            weather_state["lightning_strike_count"] = int(cur["lightning_strike_count"])
        if cur.get("lightning_strike_last_distance") is not None:
            weather_state["lightning_strike_last_distance"] = float(cur["lightning_strike_last_distance"])
        if cur.get("conditions"):
            weather_state["conditions"] = str(cur["conditions"])
        if cur.get("icon"):
            weather_state["icon"] = str(cur["icon"])
    except Exception as exc:
        print(f"[WEATHER_API] /api/weather/current error: {exc}")

    # 2. /api/weather/advanced/current
    try:
        r = requests.get(f"{WEATHER_API_URL}/api/weather/advanced/current", timeout=3)
        r.raise_for_status()
        adv = r.json()
        if adv.get("wbgt_f") is not None:
            weather_state["wbgt_f"] = float(adv["wbgt_f"])
        if adv.get("vpd_kpa") is not None:
            weather_state["vpd_kpa"] = float(adv["vpd_kpa"])
        if adv.get("delta_t_c") is not None:
            weather_state["delta_t_c"] = float(adv["delta_t_c"])
        if adv.get("air_density_kg_m3") is not None:
            weather_state["air_density_kg_m3"] = float(adv["air_density_kg_m3"])
        if adv.get("illuminance_lux") is not None:
            weather_state["illuminance_lux"] = int(round(float(adv["illuminance_lux"])))
    except Exception as exc:
        print(f"[WEATHER_API] /api/weather/advanced/current error: {exc}")

    # 3. /api/weather/aviation
    try:
        r = requests.get(f"{WEATHER_API_URL}/api/weather/aviation", timeout=3)
        r.raise_for_status()
        av = r.json()
        if av.get("density_altitude_ft") is not None:
            weather_state["density_altitude_ft"] = int(round(float(av["density_altitude_ft"])))
        if av.get("station_pressure_inhg") is not None:
            weather_state["station_pressure_inhg"] = float(av["station_pressure_inhg"])
        if av.get("station_pressure_mb") is not None:
            weather_state["station_pressure_mb"] = int(round(float(av["station_pressure_mb"])))
        if av.get("sea_level_pressure_inhg") is not None and weather_state["sea_level_pressure_inhg"] is None:
            weather_state["sea_level_pressure_inhg"] = float(av["sea_level_pressure_inhg"])
    except Exception as exc:
        print(f"[WEATHER_API] /api/weather/aviation error: {exc}")


def poll_forecast_weather_apis():
    """
    Polls the 2 forecast endpoints on weather_api:
      4. /api/weather/forecast/hourly
      5. /api/weather/forecast/daily
    """
    global weather_state

    # 4. /api/weather/forecast/hourly
    try:
        r = requests.get(f"{WEATHER_API_URL}/api/weather/forecast/hourly", timeout=4)
        r.raise_for_status()
        hourly_list = r.json()
        if isinstance(hourly_list, list) and hourly_list:
            now_utc = datetime.now(timezone.utc)
            upcoming = []
            for item in hourly_list:
                t_raw = item.get("time", "")
                try:
                    dt_utc = datetime.fromisoformat(t_raw.replace("Z", "+00:00"))
                    # Keep hours starting from the current hour block onward
                    if (dt_utc - now_utc).total_seconds() >= -3300:
                        dt_local = dt_utc.astimezone()
                        t_label = dt_local.strftime("%I %p").lstrip("0")
                        upcoming.append({
                            "time": t_label,
                            "icon": str(item.get("icon", "partly-cloudy-day")),
                            "temp": int(round(float(item.get("temp_f", 75)))),
                            "pop": int(round(float(item.get("precip_probability", 0)))),
                            "wind_dir": str(item.get("wind_direction", "")).strip(),
                        })
                except ValueError:
                    continue

            # If timestamp filtering matched fewer than 6 items, take the first 6
            if len(upcoming) < 6:
                upcoming = [
                    {
                        "time": str(item.get("time", ""))[11:16],
                        "icon": str(item.get("icon", "partly-cloudy-day")),
                        "temp": int(round(float(item.get("temp_f", 75)))),
                        "pop": int(round(float(item.get("precip_probability", 0)))),
                        "wind_dir": str(item.get("wind_direction", "")).strip(),
                    }
                    for item in hourly_list[:6]
                ]

            weather_state["hourly"] = upcoming[:6]

            # If current wind_direction is empty string "", borrow the current hour's wind_direction
            if not weather_state["wind_direction"] and upcoming and upcoming[0].get("wind_dir"):
                weather_state["wind_direction"] = upcoming[0]["wind_dir"]
    except Exception as exc:
        print(f"[WEATHER_API] /api/weather/forecast/hourly error: {exc}")

    # 5. /api/weather/forecast/daily
    try:
        r = requests.get(f"{WEATHER_API_URL}/api/weather/forecast/daily", timeout=4)
        r.raise_for_status()
        daily_list = r.json()
        if isinstance(daily_list, list) and daily_list:
            parsed_daily = []
            for d in daily_list[:5]:
                parsed_daily.append({
                    "day": str(d.get("day_name", d.get("date", "---")))[:3],
                    "icon": str(d.get("icon", "partly-cloudy-day")),
                    "hi": int(round(float(d.get("temp_max_f", 80)))),
                    "lo": int(round(float(d.get("temp_min_f", 65)))),
                    "pop": int(round(float(d.get("precip_probability", 0)))),
                })
            weather_state["daily"] = parsed_daily
    except Exception as exc:
        print(f"[WEATHER_API] /api/weather/forecast/daily error: {exc}")


# ==============================================================================
# LIVE MQTT RAPID UPDATES FROM TEMPEST_BRIDGE
# ==============================================================================
def parse_tempest_mqtt(payload_str: str):
    """Updates rapid wind speed/direction and lightning strikes in between 15s REST polls."""
    global weather_state
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        return

    msg_type = data.get("type", "")
    if msg_type == "rapid_wind" and "ob" in data and len(data["ob"]) >= 3:
        weather_state["wind_avg_mph"] = float(data["ob"][1]) * 2.23694
        weather_state["wind_deg"] = int(data["ob"][2])
        weather_state["wind_direction"] = deg_to_cardinal(weather_state["wind_deg"])
    elif msg_type == "evt_strike" and "evt" in data and len(data["evt"]) >= 2:
        weather_state["lightning_last_time"] = datetime.fromtimestamp(data["evt"][0]).strftime("%I:%M %p").lstrip("0")
        weather_state["lightning_strike_last_distance"] = round(float(data["evt"][1]) * 0.621371, 1)
        weather_state["lightning_strike_count"] += 1


# ==============================================================================
# BUILD OPENHASP COMMANDS FOR PAGE 1 & PAGE 3
# ==============================================================================
def build_weather_commands() -> list:
    w = weather_state
    sunrise_str, sunset_str = calculate_sun_times(HOME_LAT, HOME_LON)

    # Use the exact 'conditions' and 'icon' from /api/weather/current
    cond_text = w["conditions"]
    cond_icon = resolve_mdi_icon(w["icon"])

    temp_str = f"{w['temp_f']:.1f}°F" if w["temp_f"] is not None else "--.-°F"
    feels_str = f"Feels Like {w['feels_like_f']:.1f}°F" if w["feels_like_f"] is not None else "Feels Like --.-°F"
    hum_str = f"{w['relative_humidity']}%" if w["relative_humidity"] is not None else "--%"
    dew_str = f"{w['dew_point_f']:.1f}°F" if w["dew_point_f"] is not None else "--°F"

    # Format wind direction gracefully when API returns ""
    if w["wind_direction"] and w["wind_deg"] is not None:
        wind_dir_str = f"Dir: {w['wind_direction']} ({w['wind_deg']:03d}°)"
    elif w["wind_direction"]:
        wind_dir_str = f"Dir: {w['wind_direction']}"
    elif w["wind_deg"] is not None:
        wind_dir_str = f"Dir: {deg_to_cardinal(w['wind_deg'])} ({w['wind_deg']:03d}°)"
    else:
        wind_dir_str = "Dir: Calm" if w["wind_avg_mph"] < 1.0 else "Dir: Variable"

    # Format Lightning card
    ltg_cnt = w["lightning_strike_count"]
    ltg_dist = w["lightning_strike_last_distance"]
    if ltg_cnt == 0 and ltg_dist is None:
        ltg_main = "None (1h)"
        ltg_sub = "Dist: -- mi | Count: 0"
    else:
        ltg_main = w["lightning_last_time"] if w["lightning_last_time"] != "None" else f"{ltg_cnt} Strikes"
        dist_txt = f"{ltg_dist:.1f} mi" if ltg_dist is not None else "-- mi"
        ltg_sub = f"Dist: {dist_txt} | Count: {ltg_cnt}"

    # Format WBGT Card
    wbgt_val = w["wbgt_f"]
    if wbgt_val is None:
        wbgt_str, wbgt_label = "--.-°F", "Awaiting Sensor"
    else:
        wbgt_str = f"{wbgt_val:.1f}°F"
        wbgt_label = (
            "Low Thermal Stress" if wbgt_val < 78.0
            else "Moderate Caution" if wbgt_val < 82.0
            else "High Heat Stress" if wbgt_val < 86.0
            else "Extreme Danger"
        )

    # Format VPD & Aviation Density Card
    vpd_val = w["vpd_kpa"]
    if vpd_val is None:
        vpd_str, vpd_label = "-.-- kPa", "Awaiting Sensor"
    else:
        vpd_str = f"{vpd_val:.2f} kPa"
        vpd_label = (
            "Saturated / Damp Air" if vpd_val < 0.4
            else "Optimal Transpiration" if vpd_val <= 1.6
            else "High Air Dryness"
        )

    da_str = f"Density Alt: {w['density_altitude_ft']:+,} ft"
    if w["delta_t_c"] is not None:
        da_str += f" | ΔT: {w['delta_t_c']:.1f}°C"

    # Format Barometer & Station Card
    slp_str = (
        f"{w['sea_level_pressure_inhg']:.2f} inHg"
        if w["sea_level_pressure_inhg"] is not None
        else "--.-- inHg"
    )
    if w["station_pressure_inhg"] is not None and w["station_pressure_mb"] is not None:
        stn_sub = f"Stn: {w['station_pressure_inhg']:.2f} inHg ({w['station_pressure_mb']} mb)"
    elif w["air_density_kg_m3"] is not None:
        stn_sub = f"Air Density: {w['air_density_kg_m3']:.3f} kg/m³"
    else:
        stn_sub = "Station Status: Online"

    cmds = [
        # Page 1: Hero Card
        f"p1b10.text={temp_str}",
        f"p1b11.text={cond_icon}",
        f"p1b12.text={cond_text}",
        f"p1b13.text={feels_str}",
        f"p1b14.text=Humidity: {hum_str} | Dew: {dew_str}",
        # Page 1: 2x2 Primary Telemetry Grid
        f"p1b21.text={w['wind_avg_mph']:.1f} ({w['wind_gust_mph']:.1f}) mph",
        f"p1b22.text={wind_dir_str}",
        f"p1b24.text={w['precip_in']:.2f} in",
        f"p1b25.text=Rate: {w['rain_rate_in_hr']:.2f} in/hr",
        f"p1b27.text={ltg_main}",
        f"p1b28.text={ltg_sub}",
        f"p1b30.text={w['illuminance_lux']:,} lux",
        f"p1b31.text=\uF5DE {sunrise_str}  \uF5DF {sunset_str}",
        # Page 1: Bottom 3 Advanced Environmental Cards
        f"p1b41.text={wbgt_str}",
        f"p1b42.text={wbgt_label}",
        f"p1b43.text=UV Index: {w['uv_index']:.2f} | {w['solar_radiation']} W/m²",
        f"p1b45.text={vpd_str}",
        f"p1b46.text={vpd_label}",
        f"p1b47.text={da_str}",
        f"p1b49.text={slp_str}",
        f"p1b50.text=Trend: {w['pressure_trend']}",
        f"p1b51.text={stn_sub}",
    ]

    # Page 3: 6-Hour Forecast (Top 6 cards)
    for idx, hr in enumerate(w.get("hourly", [])[:6]):
        h_icon = resolve_mdi_icon(hr.get("icon", "partly-cloudy-day"))
        cmds.extend([
            f"p3b{20 + idx}.text={hr['time']}",
            f"p3b{30 + idx}.text={h_icon}",
            f"p3b{40 + idx}.text={hr['temp']}°F",
            f"p3b{50 + idx}.text=\uF596 {hr['pop']}%",
        ])

    # Page 3: 5-Day Forecast (Bottom 5 cards)
    for idx, day in enumerate(w.get("daily", [])[:5]):
        d_icon = resolve_mdi_icon(day.get("icon", "partly-cloudy-day"))
        cmds.extend([
            f"p3b{60 + idx}.text={day['day']}",
            f"p3b{70 + idx}.text={d_icon}",
            f"p3b{80 + idx}.text={day['hi']}° / {day['lo']}°",
            f"p3b{90 + idx}.text=\uF596 {day['pop']}%",
        ])

    return cmds


# ==============================================================================
# DUAL METAR FETCHER & ADS-B PROCESSOR
# ==============================================================================
def fetch_dual_metars() -> list:
    metar_map = {
        "KSFB": {"cat": "VFR", "raw": "KSFB: METAR unavailable"},
        "KORL": {"cat": "VFR", "raw": "KORL: METAR unavailable"},
    }
    try:
        resp = requests.get(METAR_URL, timeout=5)
        resp.raise_for_status()
        for item in resp.json():
            icao = item.get("icaoId", "")
            if icao in metar_map:
                metar_map[icao]["cat"] = item.get("fltCat", "VFR")
                metar_map[icao]["raw"] = item.get("rawOb", f"{icao}: No raw text")
    except Exception as exc:
        print(f"[METAR] Error polling AviationWeather.gov: {exc}")

    sfb_cat = metar_map["KSFB"]["cat"]
    orl_cat = metar_map["KORL"]["cat"]
    return [
        f"p2b39.text=[{sfb_cat}]",
        f"p2b39.text_color={FLIGHT_CAT_COLORS.get(sfb_cat, '#2dd4bf')}",
        f"p2b40.text={metar_map['KSFB']['raw']}",
        f"p2b42.text=[{orl_cat}]",
        f"p2b42.text_color={FLIGHT_CAT_COLORS.get(orl_cat, '#2dd4bf')}",
        f"p2b41.text={metar_map['KORL']['raw']}",
    ]


def process_aviation(client: mqtt.Client) -> list:
    global revert_page_at, seen_close_aircraft

    now = time.time()
    seen_close_aircraft = {
        hx: ts for hx, ts in seen_close_aircraft.items()
        if now - ts < AIRCRAFT_COOLDOWN_SECONDS
    }

    valid_aircraft = []
    try:
        resp = requests.get(AIRCRAFT_JSON_URL, timeout=2)
        resp.raise_for_status()
        for ac in resp.json().get("aircraft", []):
            if "lat" in ac and "lon" in ac:
                ac["dist_nm"] = haversine_nm(HOME_LAT, HOME_LON, ac["lat"], ac["lon"])
                ac["brg"] = calculate_bearing(HOME_LAT, HOME_LON, ac["lat"], ac["lon"])
                valid_aircraft.append(ac)
    except Exception as exc:
        print(f"[ADS-B] Error fetching aircraft.json: {exc}")

    valid_aircraft.sort(key=lambda x: x["dist_nm"])
    closest_three = valid_aircraft[:3]
    closest_dist = closest_three[0]["dist_nm"] if closest_three else 99.9

    cmds = [
        f"p0b5.text={datetime.now().strftime('%I:%M %p | %b %d').lstrip('0')}",
        f"p2b2.text={len(valid_aircraft)} Aircraft Tracked | Closest: {closest_dist:.1f} NM",
    ]

    if closest_dist <= PROXIMITY_RADIUS_NM:
        top_ac = closest_three[0]
        top_callsign = top_ac.get("flight", top_ac.get("r", top_ac.get("hex", "UNK"))).strip()
        cmds.extend([
            f"p0b4.text=\uF015 ALERT: {top_callsign} ({closest_dist:.1f} NM)",
            "p0b4.text_color=#ef4444",
            "p2b3.border_color=#ef4444",
        ])
        for ac in closest_three:
            hx = ac.get("hex", "unknown")
            if ac["dist_nm"] <= PROXIMITY_RADIUS_NM and hx not in seen_close_aircraft:
                seen_close_aircraft[hx] = now
                revert_page_at = now + ALERT_DISPLAY_SECONDS
                print(f"[ALERT] {top_callsign} at {ac['dist_nm']:.1f} NM! Switching to Page 2.")
                client.publish(f"hasp/{HASP_NODE}/command/page", "2")
                break
    else:
        cmds.extend([
            "p0b4.text=\uF015 ADS-B: CLEAR (<3NM)",
            "p0b4.text_color=#2dd4bf",
            "p2b3.border_color=#334155",
        ])

    base_ids = [10, 20, 30]
    for idx, base_id in enumerate(base_ids):
        if idx < len(closest_three):
            ac = closest_three[idx]
            callsign = (ac.get("flight") or ac.get("r") or ac.get("hex") or "N/A").strip()
            ac_type = (ac.get("t") or "---").strip()
            reg = (ac.get("r") or "N/A").strip()
            dist = ac["dist_nm"]
            brg = ac["brg"]
            gs = int(ac.get("gs", 0))
            alt = ac.get("alt_baro", "---")
            vrate = ac.get("baro_rate", ac.get("geom_rate", 0)) or 0
            squawk = ac.get("squawk", "----")
            desc = (ac.get("desc") or "UNKNOWN AIRCRAFT TYPE").strip()
            db_flags = int(ac.get("dbFlags", 0) or 0)

            tag = "[MILITARY]" if (db_flags & 1) else "[LEO / GOV]" if (db_flags & 2) else "[CIVIL]"
            alt_str = f"{alt:,} ft" if isinstance(alt, int) else f"{alt} ft"
            vrate_str = f"+{vrate} fpm" if isinstance(vrate, (int, float)) and vrate > 0 else f"{vrate} fpm"

            cmds.extend([
                f"p2b{base_id}.text={callsign[:9]}",
                f"p2b{base_id + 1}.text={ac_type[:5]}",
                f"p2b{base_id + 2}.text={dist:.1f} NM  {brg:03d}°",
                f"p2b{base_id + 3}.text={gs} kts",
                f"p2b{base_id + 4}.text={alt_str} ({vrate_str})",
                f"p2b{base_id + 5}.text=Reg: {reg}  |  {desc[:34]}  |  Sqk: {squawk}  |  {tag}",
            ])
        else:
            cmds.extend([
                f"p2b{base_id}.text=---",
                f"p2b{base_id + 1}.text=----",
                f"p2b{base_id + 2}.text=--.- NM ---°",
                f"p2b{base_id + 3}.text=--- kts",
                f"p2b{base_id + 4}.text=----- ft (--- fpm)",
                f"p2b{base_id + 5}.text=No aircraft in slot #{idx + 1}",
            ])

    return cmds


# ==============================================================================
# MQTT CALLBACKS & MAIN LOOP
# ==============================================================================
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT} (rc={rc})")
    client.subscribe(f"hasp/{HASP_NODE}/state/p0b1")
    client.subscribe(f"hasp/{HASP_NODE}/state/page")
    client.subscribe(TEMPEST_MQTT_TOPIC)


def on_message(client, userdata, msg):
    global previous_page, revert_page_at
    topic = msg.topic
    payload_str = msg.payload.decode("utf-8", errors="ignore")

    if topic.startswith(f"hasp/{HASP_NODE}/"):
        if topic.endswith("/state/page"):
            try:
                page_num = int(payload_str)
                if page_num in (1, 2, 3) and revert_page_at is None:
                    previous_page = page_num
            except ValueError:
                pass
        elif topic.endswith("/state/p0b1"):
            try:
                data = json.loads(payload_str)
                if data.get("event") == "up" and "val" in data:
                    target_page = int(data["val"]) + 1
                    previous_page = target_page
                    revert_page_at = None
                    client.publish(f"hasp/{HASP_NODE}/command/page", str(target_page))
            except (json.JSONDecodeError, ValueError):
                pass
    else:
        parse_tempest_mqtt(payload_str)


def publish_batch(client: mqtt.Client, commands: list):
    if not commands:
        return
    chunk_size = 24
    for i in range(0, len(commands), chunk_size):
        client.publish(f"hasp/{HASP_NODE}/command/json", json.dumps(commands[i:i + chunk_size]))


def main():
    global revert_page_at, cached_metar_cmds, last_metar_fetch
    global last_api_current_fetch, last_api_forecast_fetch, last_weather_push

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    print(f"[INIT] 800x480 openHASP Publisher running against {WEATHER_API_URL}...")

    try:
        while True:
            now = time.time()
            batch_commands = []

            # 1. Revert from Page 2 back to previous page after 10-second alert
            if revert_page_at and now >= revert_page_at:
                client.publish(f"hasp/{HASP_NODE}/command/page", str(previous_page))
                revert_page_at = None

            # 2. Refresh KSFB & KORL METARs every 10 minutes (600s)
            if now - last_metar_fetch >= 600:
                cached_metar_cmds = fetch_dual_metars()
                last_metar_fetch = now

            # 3. Poll /current, /advanced/current, and /aviation every 15 seconds
            if now - last_api_current_fetch >= 15:
                poll_current_weather_apis()
                last_api_current_fetch = now

            # 4. Poll /forecast/hourly and /forecast/daily every 60 seconds
            if now - last_api_forecast_fetch >= 60:
                poll_forecast_weather_apis()
                last_api_forecast_fetch = now

            # 5. Push full Weather, Forecast, and cached METAR state every 4 seconds
            #    so newly connected browsers/screens populate immediately
            if now - last_weather_push >= 4:
                batch_commands.extend(build_weather_commands())
                batch_commands.extend(cached_metar_cmds)
                last_weather_push = now

            # 6. Refresh ADS-B Traffic every 2 seconds
            batch_commands.extend(process_aviation(client))
            publish_batch(client, batch_commands)

            time.sleep(2)

    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()