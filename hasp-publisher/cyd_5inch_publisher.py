#!/usr/bin/env python3
"""
openHASP 5-Inch (800x480) Telemetry Publisher for Piccolo (Raspberry Pi 5)
"""

import json
import math
import os
import re
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

AIRCRAFT_JSON_URL = os.getenv(
    "AIRCRAFT_JSON_URL", "http://ultrafeeder:80/data/aircraft.json"
)
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather_api:8000").rstrip("/")
METAR_URL = "https://aviationweather.gov/api/data/metar?ids=KSFB,KORL&format=json"

PROXIMITY_RADIUS_NM = 3.0
ALERT_DISPLAY_SECONDS = 10
AIRCRAFT_COOLDOWN_SECONDS = 300
EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}

AIRLINE_LOGO_WHITELIST = {
    "SWA",
    "NKS",
    "DAL",
    "JBU",
    "FFT",
    "AAL",
    "UAL",
    "MXY",
    "ACA",
    "AFR",
    "BAW",
    "UAE",
    "ASA",
    "AAY",
    "SCX",
    "EIN",
    "AMX",
    "VIR",
    "AJT",
    "ABX",
    "CKS",
    "GTI",
    "UPS",
    "MTN",
    "FDX",
    "EJA",
    "LXJ",
    "VJT",
    "WUP",
}

FLIGHT_CAT_COLORS = {
    "VFR": "#2dd4bf",
    "MVFR": "#38bdf8",
    "IFR": "#ef4444",
    "LIFR": "#e879f9",
}

# ==============================================================================
# STATE TRACKING
# ==============================================================================
weather_state = {
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
    "wbgt_f": None,
    "vpd_kpa": None,
    "delta_t_c": None,
    "air_density_kg_m3": None,
    "illuminance_lux": 0,
    "density_altitude_ft": 0,
    "station_pressure_inhg": None,
    "station_pressure_mb": None,
    "pressure_trend": "Steady",
    "today_pop": 0,
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
pressure_history = []
current_backlight_mode = None


# ==============================================================================
# ICON, COLOR & MATH HELPERS
# ==============================================================================
def resolve_png_icon(icon_str: str) -> str:
    s = (icon_str or "").lower().strip()
    if "thunderstorms possible" in s or "thunderstorm possible" in s:
        return "L:/cond_tstorm_possible.png"
    if "thunderstorm" in s:
        return "L:/cond_tstorm.png"
    if "snow" in s or "wintry" in s:
        return "L:/cond_snow.png"
    if "rain possible" in s:
        return "L:/cond_rain_possible.png"
    if "rain" in s or "shower" in s or "drizzle" in s:
        return "L:/cond_rain.png"
    if "wind" in s:
        return "L:/cond_wind.png"
    if "partly" in s:
        return "L:/cond_moon.png" if "night" in s else "L:/cond_partly.png"
    if "cloud" in s or "fog" in s or "overcast" in s:
        return "L:/cond_cloudy.png"
    if "night" in s:
        return "L:/cond_moon.png"
    if "clear" in s or "sun" in s:
        return "L:/cond_sun.png"
    return "L:/cond_cloudy.png"


def resolve_aircraft_icon(callsign: str, db_flags: int) -> str:
    if db_flags & 1:
        return "L:/air_mil.png"
    match = re.match(r"^([A-Z]{3})", (callsign or "").strip().upper())
    if match:
        prefix = match.group(1)
        if prefix in AIRLINE_LOGO_WHITELIST:
            return f"L:/air_{prefix}.png"
    return "L:/air_generic.png"


def get_temp_color(temp_f) -> str:
    if temp_f is None:
        return "#ffffff"
    if temp_f < 30.0:
        return "#2563eb"  # Dark Blue
    if temp_f < 60.0:
        return "#38bdf8"  # Light Blue
    if temp_f < 80.0:
        return "#22c55e"  # Green
    if temp_f <= 90.0:
        return "#facc15"  # Yellow
    if temp_f <= 100.0:
        return "#ef4444"  # Red
    return "#b91c1c"  # Dark Red


def haversine_nm(lat1, lon1, lat2, lon2):
    r_nm = 3440.065
    a = (
        math.sin(math.radians(lat2 - lat1) / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(math.radians(lon2 - lon1) / 2.0) ** 2
    )
    return 2.0 * r_nm * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def calculate_bearing(lat1, lon1, lat2, lon2):
    x = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    y = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(
        math.radians(lat1)
    ) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    return int((math.degrees(math.atan2(x, y)) + 360) % 360)


def deg_to_cardinal(deg: float) -> str:
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    return dirs[round(deg / 22.5) % 16]


def calculate_sun_times(lat: float, lon: float):
    now = datetime.now()
    doy = now.timetuple().tm_yday
    tz = now.astimezone().utcoffset().total_seconds() / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (doy - 1)
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
    cos_ha = max(
        -1.0,
        min(
            1.0,
            (
                math.cos(math.radians(90.833))
                / (math.cos(math.radians(lat)) * math.cos(decl))
            )
            - (math.tan(math.radians(lat)) * math.tan(decl)),
        ),
    )
    ha_deg = math.degrees(math.acos(cos_ha))
    s_rise = 720.0 - 4.0 * (lon + ha_deg) - eqtime + tz * 60.0
    s_set = 720.0 - 4.0 * (lon - ha_deg) - eqtime + tz * 60.0
    rise_str = (
        now.replace(hour=int(s_rise // 60) % 24, minute=int(s_rise % 60))
        .strftime("%I:%M %p")
        .lstrip("0")
    )
    set_str = (
        now.replace(hour=int(s_set // 60) % 24, minute=int(s_set % 60))
        .strftime("%I:%M %p")
        .lstrip("0")
    )
    return rise_str, set_str, s_rise, s_set


def update_backlight(client: mqtt.Client):
    global current_backlight_mode
    _, _, sunrise_min, sunset_min = calculate_sun_times(HOME_LAT, HOME_LON)
    now = datetime.now()
    is_day = sunrise_min <= (now.hour * 60 + now.minute) <= sunset_min
    target_mode = "day" if is_day else "night"
    if current_backlight_mode != target_mode:
        brightness = 255 if is_day else 15
        client.publish(
            f"hasp/{HASP_NODE}/command/backlight",
            json.dumps({"brightness": brightness}),
        )
        current_backlight_mode = target_mode


# ==============================================================================
# WEATHER POLLING
# ==============================================================================
def poll_current_weather_apis():
    global weather_state, pressure_history
    try:
        cur = requests.get(f"{WEATHER_API_URL}/api/weather/current", timeout=3).json()
        if cur.get("temp_f") is not None:
            weather_state["temp_f"] = float(cur["temp_f"])
        if cur.get("feels_like_f") is not None:
            weather_state["feels_like_f"] = float(cur["feels_like_f"])
        if cur.get("dew_point_f") is not None:
            weather_state["dew_point_f"] = float(cur["dew_point_f"])
        if cur.get("relative_humidity") is not None:
            weather_state["relative_humidity"] = int(
                round(float(cur["relative_humidity"]))
            )
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
            pressure_history = [
                (t, p) for t, p in pressure_history if now_ts - t <= 10800
            ]
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
            weather_state["lightning_strike_last_distance"] = float(
                cur["lightning_strike_last_distance"]
            )
        if cur.get("conditions"):
            weather_state["conditions"] = str(cur["conditions"])
        if cur.get("icon"):
            weather_state["icon"] = str(cur["icon"])
    except Exception:
        pass

    try:
        adv = requests.get(
            f"{WEATHER_API_URL}/api/weather/advanced/current", timeout=3
        ).json()
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
    except Exception:
        pass

    try:
        av = requests.get(f"{WEATHER_API_URL}/api/weather/aviation", timeout=3).json()
        if av.get("density_altitude_ft") is not None:
            weather_state["density_altitude_ft"] = int(
                round(float(av["density_altitude_ft"]))
            )
        if av.get("station_pressure_inhg") is not None:
            weather_state["station_pressure_inhg"] = float(av["station_pressure_inhg"])
        if av.get("station_pressure_mb") is not None:
            weather_state["station_pressure_mb"] = int(
                round(float(av["station_pressure_mb"]))
            )
    except Exception:
        pass


def poll_forecast_weather_apis():
    global weather_state
    try:
        hourly_list = requests.get(
            f"{WEATHER_API_URL}/api/weather/forecast/hourly", timeout=4
        ).json()
        if isinstance(hourly_list, list) and hourly_list:
            upcoming = []
            for item in hourly_list:
                try:
                    dt_utc = datetime.fromisoformat(
                        item.get("time", "").replace("Z", "+00:00")
                    )
                    if (dt_utc - datetime.now(timezone.utc)).total_seconds() >= -3300:
                        upcoming.append(
                            {
                                "time": dt_utc.astimezone()
                                .strftime("%I %p")
                                .lstrip("0"),
                                "icon": str(item.get("icon", "partly-cloudy-day")),
                                "temp": int(round(float(item.get("temp_f", 75)))),
                                "pop": int(
                                    round(float(item.get("precip_probability", 0)))
                                ),
                                "wind_dir": str(item.get("wind_direction", "")).strip(),
                            }
                        )
                except Exception:
                    continue
            weather_state["hourly"] = upcoming[:6]
    except Exception:
        pass

    try:
        daily_list = requests.get(
            f"{WEATHER_API_URL}/api/weather/forecast/daily", timeout=4
        ).json()
        if isinstance(daily_list, list) and daily_list:
            weather_state["daily"] = [
                {
                    "day": str(d.get("day_name", "---"))[:3],
                    "icon": str(d.get("icon", "partly-cloudy-day")),
                    "hi": int(round(float(d.get("temp_max_f", 80)))),
                    "lo": int(round(float(d.get("temp_min_f", 65)))),
                    "pop": int(round(float(d.get("precip_probability", 0)))),
                }
                for d in daily_list[:5]
            ]
            if weather_state["daily"]:
                weather_state["today_pop"] = weather_state["daily"][0]["pop"]
    except Exception:
        pass


def parse_tempest_mqtt(payload_str: str):
    global weather_state
    try:
        data = json.loads(payload_str)
    except Exception:
        return
    if data.get("type") == "rapid_wind" and len(data.get("ob", [])) >= 3:
        weather_state["wind_avg_mph"] = float(data["ob"][1]) * 2.23694
        weather_state["wind_deg"] = int(data["ob"][2])
        weather_state["wind_direction"] = deg_to_cardinal(weather_state["wind_deg"])
    elif data.get("type") == "evt_strike" and len(data.get("evt", [])) >= 2:
        weather_state["lightning_last_time"] = (
            datetime.fromtimestamp(data["evt"][0]).strftime("%I:%M %p").lstrip("0")
        )
        weather_state["lightning_strike_last_distance"] = round(
            float(data["evt"][1]) * 0.621371, 1
        )
        weather_state["lightning_strike_count"] += 1


def build_weather_commands() -> list:
    w = weather_state
    sunrise_str, sunset_str, _, _ = calculate_sun_times(HOME_LAT, HOME_LON)

    temp_str = f"{w['temp_f']:.1f}°F" if w["temp_f"] is not None else "--.-°F"
    temp_color = get_temp_color(w["temp_f"])
    feels_str = (
        f"Feels Like {w['feels_like_f']:.1f}°F"
        if w["feels_like_f"] is not None
        else "Feels Like --.-°F"
    )
    feels_color = get_temp_color(w["feels_like_f"])

    hum_str = (
        f"{w['relative_humidity']}%" if w["relative_humidity"] is not None else "--%"
    )
    dew_str = f"{w['dew_point_f']:.1f}°F" if w["dew_point_f"] is not None else "--°F"
    slp_str = (
        f"{w['sea_level_pressure_inhg']:.2f} inHg"
        if w["sea_level_pressure_inhg"] is not None
        else "--.-- inHg"
    )

    if w["wind_direction"] and w["wind_deg"] is not None:
        wind_dir_str = f"Dir: {w['wind_direction']} ({w['wind_deg']:03d}°)"
    elif w["wind_direction"]:
        wind_dir_str = f"Dir: {w['wind_direction']}"
    elif w["wind_deg"] is not None:
        wind_dir_str = f"Dir: {deg_to_cardinal(w['wind_deg'])} ({w['wind_deg']:03d}°)"
    else:
        wind_dir_str = "Dir: Calm" if w["wind_avg_mph"] < 1.0 else "Dir: Variable"

    ltg_cnt = w["lightning_strike_count"]
    ltg_dist = w["lightning_strike_last_distance"]
    if ltg_cnt == 0 and ltg_dist is None:
        ltg_main, ltg_sub = "None (1h)", "Dist: -- mi | Count: 0"
    else:
        ltg_main = (
            w["lightning_last_time"]
            if w["lightning_last_time"] != "None"
            else f"{ltg_cnt} Strikes"
        )
        dist_txt = f"{ltg_dist:.1f} mi" if ltg_dist is not None else "-- mi"
        ltg_sub = f"Dist: {dist_txt} | Count: {ltg_cnt}"

    # WBGT 5-color comfort gradient (Green -> Red)
    wbgt_val = w["wbgt_f"]
    if wbgt_val is None:
        wbgt_str, wbgt_label, wbgt_color = "--.-°F", "Awaiting Sensor", "#94a3b8"
    elif wbgt_val < 78.0:
        wbgt_str, wbgt_label, wbgt_color = (
            f"{wbgt_val:.1f}°F",
            "Pleasant / Low Stress",
            "#22c55e",
        )
    elif wbgt_val <= 82.0:
        wbgt_str, wbgt_label, wbgt_color = (
            f"{wbgt_val:.1f}°F",
            "Warm / Moderate Caution",
            "#a3e635",
        )
    elif wbgt_val <= 86.0:
        wbgt_str, wbgt_label, wbgt_color = (
            f"{wbgt_val:.1f}°F",
            "Unpleasant / High Heat",
            "#facc15",
        )
    elif wbgt_val <= 90.0:
        wbgt_str, wbgt_label, wbgt_color = (
            f"{wbgt_val:.1f}°F",
            "Oppressive / Very High",
            "#fb923c",
        )
    else:
        wbgt_str, wbgt_label, wbgt_color = (
            f"{wbgt_val:.1f}°F",
            "Extreme Heat Danger",
            "#ef4444",
        )

    # VPD 5-color comfort gradient (Green = Ideal Comfort -> Red = Extreme Dryness)
    vpd_val = w["vpd_kpa"]
    if vpd_val is None:
        vpd_str, vpd_label, vpd_color = "-.-- kPa", "Awaiting Sensor", "#94a3b8"
    elif 0.40 <= vpd_val <= 1.20:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Pleasant / Ideal Comfort",
            "#22c55e",
        )
    elif vpd_val < 0.40:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Clammy / Saturated Air",
            "#a3e635",
        )
    elif vpd_val <= 1.40:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Mild Dryness / Breezy",
            "#a3e635",
        )
    elif vpd_val <= 1.60:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Dry / Fast Evaporation",
            "#facc15",
        )
    elif vpd_val <= 2.00:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Very Dry / High Stress",
            "#fb923c",
        )
    else:
        vpd_str, vpd_label, vpd_color = (
            f"{vpd_val:.2f} kPa",
            "Parched / Extreme Dryness",
            "#ef4444",
        )

    da_str = f"Density Alt: {w['density_altitude_ft']:+,} ft"
    if w["delta_t_c"] is not None:
        da_str += f" | ΔT: {w['delta_t_c']:.1f}°C"

    if w["station_pressure_inhg"] is not None:
        stn_sub = f"Stn: {w['station_pressure_inhg']:.2f} inHg ({w['station_pressure_mb']} mb)"
    else:
        stn_sub = "Stn: -- inHg (-- mb)"

    cmds = [
        # Main Conditions (Top Left)
        f"p1b10.text={temp_str}",
        f"p1b10.text_color={temp_color}",
        f"p1b11.src={resolve_png_icon(w['icon'])}",
        f"p1b12.text={w['conditions']}",
        f"p1b13.text={feels_str}",
        f"p1b13.text_color={feels_color}",
        f"p1b14.text=Humidity: {hum_str} | Dew: {dew_str}",
        # Wind Block (Top Middle)
        f"p1b21.text={w['wind_avg_mph']:.1f} ({w['wind_gust_mph']:.1f}) mph",
        f"p1b22.text={wind_dir_str}",
        # WBGT Block (Top Right)
        f"p1b24.text={wbgt_str}",
        f"p1b24.text_color={wbgt_color}",
        f"p1b25.text={wbgt_label}",
        "p1b25.text_color=#f8fafc",
        # Lightning Block (Middle Middle)
        f"p1b27.text={ltg_main}",
        f"p1b28.text={ltg_sub}",
        "p1b28.text_color=#facc15",
        # VPD Deficit Block (Middle Right)
        f"p1b30.text={vpd_str}",
        f"p1b30.text_color={vpd_color}",
        f"p1b31.text={vpd_label}",
        "p1b31.text_color=#f8fafc",
        # Rain & Chance Block (Bottom Left)
        f"p1b41.text={w['precip_in']:.2f} in",
        "p1b41.text_color=#ffffff",
        f"p1b42.text=Rate: {w['rain_rate_in_hr']:.2f} in/hr",
        "p1b42.text_color=#38bdf8",
        f"p1b43.text=Rain Chance: {w['today_pop']}%",
        "p1b43.text_color=#2dd4bf",
        # Solar Lux & UV & Sun Block (Bottom Middle)
        f"p1b45.text={w['illuminance_lux']:,} lux",
        "p1b45.text_color=#facc15",
        f"p1b46.text=UV Index: {w['uv_index']:.2f} | {w['solar_radiation']} W/m²",
        "p1b46.text_color=#f8fafc",
        f"p1b47.text={sunrise_str}",
        f"p1b53.text={sunset_str}",
        # Barometer, Trend & Density Altitude Block (Bottom Right)
        f"p1b49.text={slp_str}",
        f"p1b50.text=Trend: {w['pressure_trend']}",
        f"p1b51.text={da_str}",
        f"p1b52.text={stn_sub}",
    ]

    for idx, hr in enumerate(w.get("hourly", [])[:6]):
        cmds.extend(
            [
                f"p3b{20 + idx}.text={hr['time']}",
                f"p3b{30 + idx}.src={resolve_png_icon(hr.get('icon'))}",
                f"p3b{40 + idx}.text={hr['temp']}°F",
                f"p3b{50 + idx}.text={hr['pop']}%",
            ]
        )
    for idx, day in enumerate(w.get("daily", [])[:5]):
        cmds.extend(
            [
                f"p3b{60 + idx}.text={day['day']}",
                f"p3b{70 + idx}.src={resolve_png_icon(day.get('icon'))}",
                f"p3b{80 + idx}.text={day['hi']}° / {day['lo']}°",
                f"p3b{90 + idx}.text={day['pop']}%",
            ]
        )

    return cmds


def fetch_dual_metars() -> list:
    metar_map = {
        "KSFB": {"cat": "VFR", "raw": "KSFB: METAR unavailable"},
        "KORL": {"cat": "VFR", "raw": "KORL: METAR unavailable"},
    }
    try:
        for item in requests.get(METAR_URL, timeout=5).json():
            icao = item.get("icaoId", "")
            if icao in metar_map:
                metar_map[icao]["cat"] = item.get("fltCat", "VFR")
                metar_map[icao]["raw"] = item.get("rawOb", f"{icao}: No raw text")
    except Exception:
        pass
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
        hx: ts
        for hx, ts in seen_close_aircraft.items()
        if now - ts < AIRCRAFT_COOLDOWN_SECONDS
    }

    valid_aircraft = []
    try:
        for ac in requests.get(AIRCRAFT_JSON_URL, timeout=2).json().get("aircraft", []):
            if "lat" in ac and "lon" in ac:
                ac["dist_nm"] = haversine_nm(HOME_LAT, HOME_LON, ac["lat"], ac["lon"])
                ac["brg"] = calculate_bearing(HOME_LAT, HOME_LON, ac["lat"], ac["lon"])
                valid_aircraft.append(ac)
    except Exception:
        pass

    valid_aircraft.sort(key=lambda x: x["dist_nm"])
    closest_three = valid_aircraft[:3]

    now_label = datetime.now().strftime("%I:%M %p | %b %d").lstrip("0")
    cmds = [
        f"p0b5.text={now_label}",
        f"p2b2.text={len(valid_aircraft)} Tracked",
    ]

    # Top Toolbar: Always display nearest aircraft (Callsign, Description, Dist, Brg, Alt)
    if closest_three:
        top_ac = closest_three[0]
        top_cs = (
            top_ac.get("flight") or top_ac.get("r") or top_ac.get("hex") or "UNK"
        ).strip()[:8]
        top_desc = (top_ac.get("desc") or top_ac.get("t") or "UNKNOWN").strip()[:18]
        top_alt = top_ac.get("alt_baro", "---")
        top_alt_str = f"{top_alt:,}ft" if isinstance(top_alt, int) else f"{top_alt}ft"
        top_sqk = str(top_ac.get("squawk") or "").strip()
        is_close = top_ac["dist_nm"] <= PROXIMITY_RADIUS_NM
        is_emerg = top_sqk in EMERGENCY_SQUAWKS

        bar_text = f"{top_cs} | {top_desc} | {top_ac['dist_nm']:.1f}NM {top_ac['brg']:03d}° | {top_alt_str}"
        bar_color = "#ef4444" if (is_close or is_emerg) else "#2dd4bf"
        cmds.extend(
            [
                f"p0b4.text={bar_text}",
                f"p0b4.text_color={bar_color}",
            ]
        )

        for ac in closest_three:
            hx = ac.get("hex", "unknown")
            if ac["dist_nm"] <= PROXIMITY_RADIUS_NM and hx not in seen_close_aircraft:
                seen_close_aircraft[hx] = now
                revert_page_at = now + ALERT_DISPLAY_SECONDS
                client.publish(f"hasp/{HASP_NODE}/command/page", "2")
                break
    else:
        cmds.extend(
            [
                "p0b4.text=ADS-B: No Traffic Tracked",
                "p0b4.text_color=#94a3b8",
            ]
        )

    # Page 2 Rows (Slots 1, 2, 3)
    card_ids = [3, 4, 5]
    for idx, base_id in enumerate([10, 20, 30]):
        card_id = card_ids[idx]
        if idx < len(closest_three):
            ac = closest_three[idx]
            cs = (ac.get("flight") or ac.get("r") or ac.get("hex") or "N/A").strip()[:9]
            ac_type = (ac.get("t") or "---").strip()[:5]
            reg = (ac.get("r") or "N/A").strip()
            desc = (ac.get("desc") or "UNKNOWN AIRCRAFT TYPE").strip()[:34]
            sqk = str(ac.get("squawk") or "----").strip()
            alt = ac.get("alt_baro", "---")
            vrate = ac.get("baro_rate", ac.get("geom_rate", 0)) or 0
            db_flags = int(ac.get("dbFlags", 0) or 0)
            tag = (
                "[MILITARY]"
                if (db_flags & 1)
                else "[LEO / GOV]"
                if (db_flags & 2)
                else "[CIVIL]"
            )

            alt_str = f"{alt:,} ft" if isinstance(alt, int) else f"{alt} ft"
            vrate_str = (
                f"+{vrate} fpm"
                if isinstance(vrate, (int, float)) and vrate > 0
                else f"{vrate} fpm"
            )
            logo_src = resolve_aircraft_icon(cs, db_flags)

            # Red border if emergency squawk (7500/7600/7700) or <3NM proximity alert
            is_emerg_sqk = sqk in EMERGENCY_SQUAWKS
            is_prox = ac["dist_nm"] <= PROXIMITY_RADIUS_NM
            if is_emerg_sqk or is_prox:
                border_col = "#ef4444"
                border_w = 3 if is_emerg_sqk else 2
            else:
                border_col = "#334155"
                border_w = 1

            cmds.extend(
                [
                    f"p2b{card_id}.border_color={border_col}",
                    f"p2b{card_id}.border_width={border_w}",
                    f"p2b{base_id + 6}.src={logo_src}",
                    f"p2b{base_id}.text={cs}",
                    f"p2b{base_id + 1}.text={ac_type}",
                    f"p2b{base_id + 2}.text={ac['dist_nm']:.1f} NM {ac['brg']:03d}°",
                    f"p2b{base_id + 3}.text={int(ac.get('gs', 0))} kts",
                    f"p2b{base_id + 4}.text={alt_str} ({vrate_str})",
                    f"p2b{base_id + 5}.text=Reg: {reg}  |  {desc}  |  Sqk: {sqk}  |  {tag}",
                ]
            )
        else:
            cmds.extend(
                [
                    f"p2b{card_id}.border_color=#334155",
                    f"p2b{card_id}.border_width=1",
                    f"p2b{base_id + 6}.src=L:/air_generic.png",
                    f"p2b{base_id}.text=---",
                    f"p2b{base_id + 1}.text=----",
                    f"p2b{base_id + 2}.text=--.- NM ---°",
                    f"p2b{base_id + 3}.text=--- kts",
                    f"p2b{base_id + 4}.text=----- ft (--- fpm)",
                    f"p2b{base_id + 5}.text=No aircraft in slot #{idx + 1}",
                ]
            )
    return cmds


def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(f"hasp/{HASP_NODE}/state/p0b1")
    client.subscribe(f"hasp/{HASP_NODE}/state/page")
    client.subscribe(TEMPEST_MQTT_TOPIC)


def on_message(client, userdata, msg):
    global previous_page, revert_page_at
    topic, payload = msg.topic, msg.payload.decode("utf-8", errors="ignore")
    if topic.startswith(f"hasp/{HASP_NODE}/"):
        if topic.endswith("/state/page"):
            try:
                p = int(payload)
                if p in (1, 2, 3) and revert_page_at is None:
                    previous_page = p
            except Exception:
                pass
        elif topic.endswith("/state/p0b1"):
            try:
                d = json.loads(payload)
                if d.get("event") == "up" and "val" in d:
                    target_page = int(d["val"]) + 1
                    previous_page = target_page
                    revert_page_at = None
                    client.publish(f"hasp/{HASP_NODE}/command/page", str(target_page))
            except Exception:
                pass
    else:
        parse_tempest_mqtt(payload)


def publish_batch(client: mqtt.Client, commands: list):
    for i in range(0, len(commands), 24):
        client.publish(
            f"hasp/{HASP_NODE}/command/json", json.dumps(commands[i : i + 24])
        )


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
    try:
        while True:
            now = time.time()
            batch_commands = []
            if revert_page_at and now >= revert_page_at:
                client.publish(f"hasp/{HASP_NODE}/command/page", str(previous_page))
                revert_page_at = None
            if now - last_metar_fetch >= 600:
                cached_metar_cmds = fetch_dual_metars()
                last_metar_fetch = now
            if now - last_api_current_fetch >= 15:
                poll_current_weather_apis()
                update_backlight(client)
                last_api_current_fetch = now
            if now - last_api_forecast_fetch >= 60:
                poll_forecast_weather_apis()
                last_api_forecast_fetch = now
            if now - last_weather_push >= 4:
                batch_commands.extend(build_weather_commands())
                batch_commands.extend(cached_metar_cmds)
                last_weather_push = now
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
