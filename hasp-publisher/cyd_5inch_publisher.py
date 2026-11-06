#!/usr/bin/env python3
"""
openHASP 5-Inch (800x480) Telemetry Publisher for Piccolo (Raspberry Pi 5)
Subscribes directly to local Tempest MQTT topics from tempest_bridge,
polls local weather_api for forecasts, and reads ultrafeeder aircraft.json.
"""

import json
import math
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests

# ==============================================================================
# CONFIGURATION (Mapped to Piccolo docker-compose.yml & .env)
# ==============================================================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
HASP_NODE = os.getenv("HASP_NODE", "plate_5inch")

# Topic pattern published by your tempest_bridge container
TEMPEST_MQTT_TOPIC = os.getenv("TEMPEST_MQTT_TOPIC", "tempest/#")

# Home Coordinates & Elevation from .env / ultrafeeder config
HOME_LAT = float(os.getenv("HOME_LATITUDE", "28.6611"))
HOME_LON = float(os.getenv("HOME_LONGITUDE", "-81.3656"))
STATION_ELEV_M = 25.9  # 85 ft (matches ALT=85ft in ultrafeeder)

# Internal piccolo_net Endpoints
AIRCRAFT_JSON_URL = os.getenv(
    "AIRCRAFT_JSON_URL", "http://ultrafeeder:80/data/aircraft.json"
)
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather_api:8000")
DASHBOARD_API_URL = os.getenv("DASHBOARD_API_URL", "http://family_dashboard_api:8000")
METAR_URL = "https://aviationweather.gov/api/data/metar?ids=KSFB,KORL&format=json"

# Proximity Alert Settings
PROXIMITY_RADIUS_NM = 3.0
ALERT_DISPLAY_SECONDS = 10
AIRCRAFT_COOLDOWN_SECONDS = 300

MDI_ICONS = {
    "clear-day": "\uf599",
    "clear-night": "\uf594",
    "partly-cloudy": "\uf595",
    "cloudy": "\uf590",
    "rain": "\uf597",
    "thunderstorm": "\uf593",
    "wind": "\uf5a0",
}

FLIGHT_CAT_COLORS = {
    "VFR": "#2dd4bf",
    "MVFR": "#38bdf8",
    "IFR": "#ef4444",
    "LIFR": "#e879f9",
}

# ==============================================================================
# LIVE TELEMETRY STATE (Updated via MQTT from tempest_bridge + weather_api)
# ==============================================================================
weather_state = {
    "temp_f": None,
    "feels_like_f": None,
    "humidity": None,
    "dew_point_f": None,
    "condition": "Waiting for Tempest...",
    "icon_key": "partly-cloudy",
    "wind_avg_mph": 0.0,
    "wind_gust_mph": 0.0,
    "wind_deg": 0,
    "rain_rate_in_hr": 0.00,
    "rain_today_in": 0.00,
    "lightning_last_time": "None",
    "lightning_dist_mi": 0.0,
    "lightning_count": 0,
    "wbgt_f": None,
    "uv_index": 0.0,
    "solar_rad_wm2": 0,
    "vpd_kpa": None,
    "density_alt_ft": 0,
    "pressure_inhg": None,
    "pressure_trend": "Steady",
    "station_volts": 0.0,
    "solar_lux": 0,
    "hourly": [],
    "daily": [],
}

seen_close_aircraft = {}
revert_page_at = None
previous_page = 1
last_metar_fetch = 0
last_forecast_fetch = 0
last_weather_push = 0
pressure_history = []  # [(timestamp, pressure_inhg)] for 3-hour trend


# ==============================================================================
# METEOROLOGICAL & GEOSPATIAL CALCULATIONS
# ==============================================================================
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


def compute_derived_metrics(
    temp_c: float, rh: float, pres_mb: float, wind_mps: float, solar_wm2: float
):
    """Computes Dew Point, Feels Like, VPD, WBGT, Sea-Level Pressure, and Density Altitude from Tempest obs."""
    temp_f = temp_c * 9.0 / 5.0 + 32.0
    rh_clamped = max(1.0, min(100.0, float(rh)))

    # 1. Dew Point (Magnus formula)
    b, c = 17.625, 243.04
    gamma = math.log(rh_clamped / 100.0) + (b * temp_c) / (c + temp_c)
    dew_c = (c * gamma) / (b - gamma)
    dew_f = dew_c * 9.0 / 5.0 + 32.0

    # 2. Feels Like (Heat Index / Wind Chill)
    wind_mph = wind_mps * 2.23694
    if temp_f >= 80.0 and rh_clamped >= 40.0:
        hi = (
            -42.379
            + 2.04901523 * temp_f
            + 10.14333127 * rh_clamped
            - 0.22475541 * temp_f * rh_clamped
            - 0.00683783 * temp_f * temp_f
            - 0.05481717 * rh_clamped * rh_clamped
            + 0.00122874 * temp_f * temp_f * rh_clamped
            + 0.00085282 * temp_f * rh_clamped * rh_clamped
            - 0.00000199 * temp_f * temp_f * rh_clamped * rh_clamped
        )
        feels_f = hi
    elif temp_f <= 50.0 and wind_mph >= 3.0:
        feels_f = (
            35.74
            + 0.6215 * temp_f
            - 35.75 * (wind_mph**0.16)
            + 0.4275 * temp_f * (wind_mph**0.16)
        )
    else:
        feels_f = temp_f

    # 3. Vapor Pressure Deficit (VPD in kPa)
    svp = 0.61078 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    avp = svp * (rh_clamped / 100.0)
    vpd_kpa = max(0.0, svp - avp)

    # 4. Wet Bulb Globe Temperature (WBGT °F) approximation
    # Stull (2011) Wet Bulb + solar/wind globe adjustment
    tw_c = (
        temp_c * math.atan(0.151977 * ((rh_clamped + 8.313659) ** 0.5))
        + math.atan(temp_c + rh_clamped)
        - math.atan(rh_clamped - 1.676331)
        + 0.00391838 * (rh_clamped**1.5) * math.atan(0.023101 * rh_clamped)
        - 4.686035
    )
    tg_c = temp_c + 0.014 * float(solar_wm2) - 0.25 * math.sqrt(max(0.1, wind_mps))
    wbgt_c = 0.7 * tw_c + 0.2 * max(temp_c, tg_c) + 0.1 * temp_c
    wbgt_f = wbgt_c * 9.0 / 5.0 + 32.0

    # 5. Sea-Level Pressure (inHg) & Density Altitude (ft)
    slp_mb = pres_mb * (
        (1.0 - (0.0065 * STATION_ELEV_M) / (temp_c + 273.15 + 0.0065 * STATION_ELEV_M))
        ** -5.257
    )
    slp_inhg = slp_mb * 0.02953

    pres_alt_ft = (1.0 - ((slp_mb / 1013.25) ** 0.190284)) * 145366.45
    isa_temp_c = 15.0 - 0.0019812 * 85.0
    density_alt_ft = int(pres_alt_ft + 118.8 * (temp_c - isa_temp_c))

    return temp_f, feels_f, dew_f, vpd_kpa, wbgt_f, slp_inhg, density_alt_ft


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
# TEMPEST MQTT PARSER (Handles Raw UDP JSON & Flattened Dicts)
# ==============================================================================
def parse_tempest_mqtt(topic: str, payload_str: str):
    """Ingests live MQTT messages published by tempest_bridge."""
    global weather_state, pressure_history
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        return

    msg_type = data.get("type", "")

    # Case 1: Raw WeatherFlow UDP 'rapid_wind' packet
    if msg_type == "rapid_wind" and "ob" in data:
        ob = data["ob"]
        if len(ob) >= 3:
            weather_state["wind_avg_mph"] = float(ob[1]) * 2.23694
            weather_state["wind_deg"] = int(ob[2])
        return

    # Case 2: Raw WeatherFlow UDP 'evt_strike' packet
    if msg_type == "evt_strike" and "evt" in data:
        evt = data["evt"]
        if len(evt) >= 2:
            strike_dt = datetime.fromtimestamp(evt[0]).strftime("%I:%M %p").lstrip("0")
            weather_state["lightning_last_time"] = strike_dt
            weather_state["lightning_dist_mi"] = round(float(evt[1]) * 0.621371, 1)
            weather_state["lightning_count"] = (
                weather_state.get("lightning_count", 0) + 1
            )
        return

    # Case 3: Raw WeatherFlow UDP 'obs_st' packet
    if msg_type == "obs_st" and "obs" in data and data["obs"]:
        obs = data["obs"][0]
        # obs_st indices:
        # 0:epoch, 1:lull, 2:avg_mps, 3:gust_mps, 4:dir, 5:int, 6:pres_mb, 7:temp_c,
        # 8:rh, 9:lux, 10:uv, 11:solar_wm2, 12:rain_mm, 13:precip_type, 14:ltg_dist_km,
        # 15:ltg_cnt, 16:bat_v, 17:rep_int, 18:local_day_rain_mm (if present)
        wind_avg_mps = float(obs[2] or 0.0)
        wind_gust_mps = float(obs[3] or 0.0)
        wind_deg = int(obs[4] or 0)
        pres_mb = float(obs[6] or 1013.25)
        temp_c = float(obs[7] or 20.0)
        rh = float(obs[8] or 50.0)
        lux = int(obs[9] or 0)
        uv = float(obs[10] or 0.0)
        solar_wm2 = int(obs[11] or 0)
        rain_interval_mm = float(obs[12] or 0.0)
        ltg_dist_km = float(obs[14] or 0.0)
        ltg_cnt = int(obs[15] or 0)
        bat_v = float(obs[16] or 0.0)
        rep_min = float(obs[17] or 1.0)

        temp_f, feels_f, dew_f, vpd_kpa, wbgt_f, slp_inhg, d_alt = (
            compute_derived_metrics(temp_c, rh, pres_mb, wind_avg_mps, solar_wm2)
        )

        weather_state.update(
            {
                "temp_f": temp_f,
                "feels_like_f": feels_f,
                "humidity": int(round(rh)),
                "dew_point_f": dew_f,
                "wind_avg_mph": wind_avg_mps * 2.23694,
                "wind_gust_mph": wind_gust_mps * 2.23694,
                "wind_deg": wind_deg,
                "rain_rate_in_hr": (rain_interval_mm / 25.4)
                * (60.0 / max(1.0, rep_min)),
                "wbgt_f": wbgt_f,
                "uv_index": uv,
                "solar_rad_wm2": solar_wm2,
                "vpd_kpa": vpd_kpa,
                "density_alt_ft": d_alt,
                "pressure_inhg": slp_inhg,
                "station_volts": bat_v,
                "solar_lux": lux,
            }
        )
        if len(obs) > 18 and obs[18] is not None:
            weather_state["rain_today_in"] = float(obs[18]) / 25.4
        if ltg_cnt > 0:
            weather_state["lightning_dist_mi"] = round(ltg_dist_km * 0.621371, 1)
            weather_state["lightning_count"] = ltg_cnt
            weather_state["lightning_last_time"] = (
                datetime.now().strftime("%I:%M %p").lstrip("0")
            )

        # Update 3-hour pressure trend
        now_ts = time.time()
        pressure_history.append((now_ts, slp_inhg))
        pressure_history = [(t, p) for t, p in pressure_history if now_ts - t <= 10800]
        if len(pressure_history) >= 2:
            delta = slp_inhg - pressure_history[0][1]
            if delta >= 0.03:
                weather_state["pressure_trend"] = f"Rising ({delta:+.2f})"
            elif delta <= -0.03:
                weather_state["pressure_trend"] = f"Falling ({delta:+.2f})"
            else:
                weather_state["pressure_trend"] = f"Steady ({delta:+.2f})"
        return

    # Case 4: Pre-parsed / flattened JSON dictionary published by tempest_bridge
    if isinstance(data, dict):
        if "air_temperature" in data or "temp_c" in data:
            tc = float(data.get("air_temperature", data.get("temp_c")))
            rh = float(
                data.get(
                    "relative_humidity",
                    data.get("humidity", weather_state["humidity"] or 50),
                )
            )
            pr = float(data.get("station_pressure", data.get("pressure_mb", 1013.25)))
            ws = float(data.get("wind_avg", 0.0))
            sr = float(data.get("solar_radiation", weather_state["solar_rad_wm2"] or 0))
            tf, ff, df, vpd, wbgt, slp, da = compute_derived_metrics(tc, rh, pr, ws, sr)
            weather_state.update(
                {
                    "temp_f": tf,
                    "feels_like_f": ff,
                    "humidity": int(round(rh)),
                    "dew_point_f": df,
                    "vpd_kpa": vpd,
                    "wbgt_f": wbgt,
                    "pressure_inhg": slp,
                    "density_alt_ft": da,
                }
            )
        elif "temp_f" in data or "temperature" in data:
            weather_state["temp_f"] = float(data.get("temp_f", data.get("temperature")))

        if "wind_avg_mph" in data:
            weather_state["wind_avg_mph"] = float(data["wind_avg_mph"])
        elif "wind_avg" in data or "wind_speed" in data:
            weather_state["wind_avg_mph"] = (
                float(data.get("wind_avg", data.get("wind_speed"))) * 2.23694
            )

        if "wind_gust_mph" in data:
            weather_state["wind_gust_mph"] = float(data["wind_gust_mph"])
        elif "wind_gust" in data:
            weather_state["wind_gust_mph"] = float(data["wind_gust"]) * 2.23694

        if "wind_direction" in data or "wind_deg" in data:
            weather_state["wind_deg"] = int(
                data.get("wind_direction", data.get("wind_deg"))
            )

        if "illuminance" in data or "solar_lux" in data or "lux" in data:
            weather_state["solar_lux"] = int(
                data.get("illuminance", data.get("solar_lux", data.get("lux")))
            )

        if "uv" in data or "uv_index" in data:
            weather_state["uv_index"] = float(data.get("uv", data.get("uv_index")))

        if "solar_radiation" in data:
            weather_state["solar_rad_wm2"] = int(data["solar_radiation"])


# ==============================================================================
# LOCAL WEATHER_API FORECAST & CURRENT POLLING
# ==============================================================================
def poll_local_weather_api():
    """
    Polls your local weather_api container (http://weather_api:8000) for
    6-hour / 5-day forecasts and any aggregated rain/lightning/condition fields.
    """
    global weather_state

    # 1. Poll current endpoint on weather_api
    for url in [
        f"{WEATHER_API_URL}/api/weather/current",
        f"{DASHBOARD_API_URL}/api/weather/current",
        f"{WEATHER_API_URL}/weather/current",
    ]:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                cur = r.json()
                if isinstance(cur, dict):
                    if weather_state["temp_f"] is None and (
                        "temp_f" in cur or "temperature" in cur
                    ):
                        weather_state["temp_f"] = float(
                            cur.get("temp_f", cur.get("temperature"))
                        )
                    if "condition" in cur or "conditions" in cur or "summary" in cur:
                        weather_state["condition"] = str(
                            cur.get("condition")
                            or cur.get("conditions")
                            or cur.get("summary")
                        )
                    if (
                        "rain_today" in cur
                        or "precip_accum_local_day" in cur
                        or "rain_today_in" in cur
                    ):
                        val = cur.get(
                            "rain_today_in",
                            cur.get(
                                "rain_today", cur.get("precip_accum_local_day", 0.0)
                            ),
                        )
                        if val is not None:
                            weather_state["rain_today_in"] = float(val)
                break
        except Exception:
            continue

    # 2. Poll hourly forecast endpoint on weather_api
    for url in [
        f"{WEATHER_API_URL}/api/weather/forecast/hourly",
        f"{WEATHER_API_URL}/api/weather/forecast",
        f"{DASHBOARD_API_URL}/api/weather/forecast",
    ]:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                fc = r.json()
                hourly_raw = (
                    fc
                    if isinstance(fc, list)
                    else fc.get("hourly", fc.get("forecast", []))
                )
                if isinstance(hourly_raw, list) and hourly_raw:
                    parsed_hourly = []
                    for item in hourly_raw[:6]:
                        t_raw = (
                            item.get("time")
                            or item.get("timestamp")
                            or item.get("datetime")
                            or "--"
                        )
                        if isinstance(t_raw, (int, float)):
                            t_str = (
                                datetime.fromtimestamp(t_raw)
                                .strftime("%I %p")
                                .lstrip("0")
                            )
                        elif isinstance(t_raw, str) and "T" in t_raw:
                            try:
                                dt = datetime.fromisoformat(
                                    t_raw.replace("Z", "+00:00")
                                ).astimezone()
                                t_str = dt.strftime("%I %p").lstrip("0")
                            except ValueError:
                                t_str = t_raw[:5]
                        else:
                            t_str = str(t_raw)

                        temp_val = item.get(
                            "temp_f", item.get("temp", item.get("temperature", 75))
                        )
                        pop_val = item.get(
                            "pop",
                            item.get("precip_probability", item.get("rain_chance", 0)),
                        )
                        icon_raw = str(
                            item.get("icon", item.get("condition", "partly-cloudy"))
                        ).lower()
                        icon_key = "partly-cloudy"
                        for k in MDI_ICONS:
                            if k in icon_raw:
                                icon_key = k
                                break
                        parsed_hourly.append(
                            {
                                "time": t_str,
                                "icon": icon_key,
                                "temp": int(round(float(temp_val))),
                                "pop": int(round(float(pop_val))),
                            }
                        )
                    weather_state["hourly"] = parsed_hourly

                if isinstance(fc, dict) and ("daily" in fc or "days" in fc):
                    daily_raw = fc.get("daily") or fc.get("days") or []
                    parsed_daily = []
                    for d in daily_raw[:5]:
                        day_str = str(d.get("day", d.get("date", "---")))[:3]
                        hi_val = int(
                            round(
                                float(d.get("hi", d.get("temp_max", d.get("high", 80))))
                            )
                        )
                        lo_val = int(
                            round(
                                float(d.get("lo", d.get("temp_min", d.get("low", 65))))
                            )
                        )
                        pop_val = int(
                            round(float(d.get("pop", d.get("precip_probability", 0))))
                        )
                        parsed_daily.append(
                            {
                                "day": day_str,
                                "icon": "partly-cloudy",
                                "hi": hi_val,
                                "lo": lo_val,
                                "pop": pop_val,
                            }
                        )
                    if parsed_daily:
                        weather_state["daily"] = parsed_daily
                break
        except Exception:
            continue


# ==============================================================================
# FORMAT PAGE 1 & PAGE 3 COMMANDS
# ==============================================================================
def build_weather_commands() -> list:
    w = weather_state
    sunrise_str, sunset_str = calculate_sun_times(HOME_LAT, HOME_LON)

    # Derive sky condition from live Solar Lux / Rain if API condition string wasn't set
    is_night = w["solar_lux"] < 50
    if w["rain_rate_in_hr"] > 0:
        cond_text, icon_key = "Raining", "rain"
    elif w["lightning_count"] > 0:
        cond_text, icon_key = "Thunderstorm", "thunderstorm"
    elif is_night:
        cond_text, icon_key = "Clear Night", "clear-night"
    elif w["solar_lux"] > 25000:
        cond_text, icon_key = "Sunny / Clear", "clear-day"
    else:
        cond_text = (
            w["condition"]
            if w["condition"] != "Waiting for Tempest..."
            else "Partly Cloudy"
        )
        icon_key = w.get("icon_key", "partly-cloudy")

    cond_icon = MDI_ICONS.get(icon_key, "\uf595")
    cardinal = deg_to_cardinal(w["wind_deg"])

    temp_str = f"{w['temp_f']:.1f}°F" if w["temp_f"] is not None else "--.-°F"
    feels_str = (
        f"Feels Like {w['feels_like_f']:.1f}°F"
        if w["feels_like_f"] is not None
        else "Feels Like --.-°F"
    )
    hum_str = f"{w['humidity']}%" if w["humidity"] is not None else "--%"
    dew_str = f"{w['dew_point_f']:.1f}°F" if w["dew_point_f"] is not None else "--°F"

    wbgt_val = w["wbgt_f"]
    if wbgt_val is None:
        wbgt_str, wbgt_label = "--.-°F", "Awaiting Sensor"
    else:
        wbgt_str = f"{wbgt_val:.1f}°F"
        wbgt_label = (
            "Low Thermal Stress"
            if wbgt_val < 78.0
            else "Moderate Caution"
            if wbgt_val < 82.0
            else "High Heat Stress"
            if wbgt_val < 86.0
            else "Extreme Danger"
        )

    vpd_val = w["vpd_kpa"]
    if vpd_val is None:
        vpd_str, vpd_label = "-.-- kPa", "Awaiting Sensor"
    else:
        vpd_str = f"{vpd_val:.2f} kPa"
        vpd_label = (
            "Saturated / Damp Air"
            if vpd_val < 0.4
            else "Optimal Transpiration"
            if vpd_val <= 1.6
            else "High Air Dryness"
        )

    pres_str = (
        f"{w['pressure_inhg']:.2f} inHg"
        if w["pressure_inhg"] is not None
        else "--.-- inHg"
    )
    ltg_sub = (
        "Dist: -- mi | Count: 0"
        if w["lightning_count"] == 0
        else f"Dist: {w['lightning_dist_mi']} mi | Count: {w['lightning_count']}"
    )

    cmds = [
        f"p1b10.text={temp_str}",
        f"p1b11.text={cond_icon}",
        f"p1b12.text={cond_text}",
        f"p1b13.text={feels_str}",
        f"p1b14.text=Humidity: {hum_str} | Dew: {dew_str}",
        f"p1b21.text={w['wind_avg_mph']:.1f} ({w['wind_gust_mph']:.1f}) mph",
        f"p1b22.text=Dir: {cardinal} ({w['wind_deg']:03d}°)",
        f"p1b24.text={w['rain_today_in']:.2f} in",
        f"p1b25.text=Rate: {w['rain_rate_in_hr']:.2f} in/hr",
        f"p1b27.text={w['lightning_last_time']}",
        f"p1b28.text={ltg_sub}",
        f"p1b30.text={w['solar_lux']:,} lux",
        f"p1b31.text=\uf5de {sunrise_str}  \uf5df {sunset_str}",
        f"p1b41.text={wbgt_str}",
        f"p1b42.text={wbgt_label}",
        f"p1b43.text=UV Index: {w['uv_index']:.1f} | {w['solar_rad_wm2']} W/m²",
        f"p1b45.text={vpd_str}",
        f"p1b46.text={vpd_label}",
        f"p1b47.text=Density Alt: {w['density_alt_ft']:+,} ft",
        f"p1b49.text={pres_str}",
        f"p1b50.text=Trend: {w['pressure_trend']}",
        f"p1b51.text=Tempest Bat: {w['station_volts']:.2f}V",
    ]

    for idx, hr in enumerate(w.get("hourly", [])[:6]):
        h_icon = MDI_ICONS.get(hr.get("icon", "partly-cloudy"), "\uf595")
        cmds.extend(
            [
                f"p3b{20 + idx}.text={hr['time']}",
                f"p3b{30 + idx}.text={h_icon}",
                f"p3b{40 + idx}.text={hr['temp']}°F",
                f"p3b{50 + idx}.text=\uf596 {hr['pop']}%",
            ]
        )

    for idx, day in enumerate(w.get("daily", [])[:5]):
        d_icon = MDI_ICONS.get(day.get("icon", "partly-cloudy"), "\uf595")
        cmds.extend(
            [
                f"p3b{60 + idx}.text={day['day']}",
                f"p3b{70 + idx}.text={d_icon}",
                f"p3b{80 + idx}.text={day['hi']}° / {day['lo']}°",
                f"p3b{90 + idx}.text=\uf596 {day['pop']}%",
            ]
        )

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
        hx: ts
        for hx, ts in seen_close_aircraft.items()
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
        top_callsign = top_ac.get(
            "flight", top_ac.get("r", top_ac.get("hex", "UNK"))
        ).strip()
        cmds.extend(
            [
                f"p0b4.text=\uf015 ALERT: {top_callsign} ({closest_dist:.1f} NM)",
                "p0b4.text_color=#ef4444",
                "p2b3.border_color=#ef4444",
            ]
        )
        for ac in closest_three:
            hx = ac.get("hex", "unknown")
            if ac["dist_nm"] <= PROXIMITY_RADIUS_NM and hx not in seen_close_aircraft:
                seen_close_aircraft[hx] = now
                revert_page_at = now + ALERT_DISPLAY_SECONDS
                print(
                    f"[ALERT] {top_callsign} at {ac['dist_nm']:.1f} NM! Switching to Page 2."
                )
                client.publish(f"hasp/{HASP_NODE}/command/page", "2")
                break
    else:
        cmds.extend(
            [
                "p0b4.text=\uf015 ADS-B: CLEAR (<3NM)",
                "p0b4.text_color=#2dd4bf",
                "p2b3.border_color=#334155",
            ]
        )

    base_ids = [10, 20, 30]
    for idx, base_id in enumerate(base_ids):
        if idx < len(closest_three):
            ac = closest_three[idx]
            callsign = (
                ac.get("flight") or ac.get("r") or ac.get("hex") or "N/A"
            ).strip()
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

            cmds.extend(
                [
                    f"p2b{base_id}.text={callsign[:9]}",
                    f"p2b{base_id + 1}.text={ac_type[:5]}",
                    f"p2b{base_id + 2}.text={dist:.1f} NM  {brg:03d}°",
                    f"p2b{base_id + 3}.text={gs} kts",
                    f"p2b{base_id + 4}.text={alt_str} ({vrate_str})",
                    f"p2b{base_id + 5}.text=Reg: {reg}  |  {desc[:34]}  |  Sqk: {squawk}  |  {tag}",
                ]
            )
        else:
            cmds.extend(
                [
                    f"p2b{base_id}.text=---",
                    f"p2b{base_id + 1}.text=----",
                    f"p2b{base_id + 2}.text=--.- NM ---°",
                    f"p2b{base_id + 3}.text=--- kts",
                    f"p2b{base_id + 4}.text=----- ft (--- fpm)",
                    f"p2b{base_id + 5}.text=No aircraft in slot #{idx + 1}",
                ]
            )

    return cmds


# ==============================================================================
# MQTT CALLBACKS & MAIN LOOP
# ==============================================================================
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT} (rc={rc})")
    client.subscribe(f"hasp/{HASP_NODE}/state/p0b1")
    client.subscribe(f"hasp/{HASP_NODE}/state/page")
    client.subscribe(TEMPEST_MQTT_TOPIC)
    print(f"[MQTT] Subscribed to Tempest stream on '{TEMPEST_MQTT_TOPIC}'")


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
        # Process live Tempest UDP-to-MQTT broadcast
        parse_tempest_mqtt(topic, payload_str)


def publish_batch(client: mqtt.Client, commands: list):
    if not commands:
        return
    chunk_size = 24
    for i in range(0, len(commands), chunk_size):
        client.publish(
            f"hasp/{HASP_NODE}/command/json", json.dumps(commands[i : i + chunk_size])
        )


def main():
    global revert_page_at, last_metar_fetch, last_forecast_fetch, last_weather_push

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
                batch_commands.extend(fetch_dual_metars())
                last_metar_fetch = now

            if now - last_forecast_fetch >= 120:
                poll_local_weather_api()
                last_forecast_fetch = now

            if now - last_weather_push >= 5:
                batch_commands.extend(build_weather_commands())
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
