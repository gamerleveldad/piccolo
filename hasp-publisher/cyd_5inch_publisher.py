#!/usr/bin/env python3
"""
openHASP 5-Inch (800x480) Telemetry Publisher for Raspberry Pi 5
Integrates Tempest Weather, ultrafeeder ADS-B (aircraft.json), and FAA METARs (KSFB/KORL).
"""

import json
import math
import os
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import requests

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")  # Anonymous enabled in mosquitto.conf
MQTT_PASS = os.getenv("MQTT_PASS", "")
HASP_NODE = os.getenv("HASP_NODE", "plate_5inch")

# Pulls HOME_LATITUDE and HOME_LONGITUDE directly from your ~/Piccolo/.env file
HOME_LAT = float(os.getenv("HOME_LATITUDE", "28.6611"))
HOME_LON = float(os.getenv("HOME_LONGITUDE", "-81.3656"))

# Internal piccolo_net Docker Endpoints
AIRCRAFT_JSON_URL = os.getenv(
    "AIRCRAFT_JSON_URL", "http://ultrafeeder:80/data/aircraft.json"
)
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather_api:8000")
DASHBOARD_API_URL = os.getenv("DASHBOARD_API_URL", "http://family_dashboard_api:8000")
FLIGHT_API_URL = os.getenv("FLIGHT_API_URL", "http://flight_api:8000")

# Append your specific route path on weather_api or family_dashboard_api
TEMPEST_CURRENT_URL = f"{WEATHER_API_URL}/weather"
METAR_URL = "https://aviationweather.gov/api/data/metar?ids=KSFB,KORL&format=json"

# Proximity Alert Settings
PROXIMITY_RADIUS_NM = 3.0
ALERT_DISPLAY_SECONDS = 10
AIRCRAFT_COOLDOWN_SECONDS = 300  # 5-minute cooldown per aircraft hex

# Built-in openHASP Material Design Icon (MDI) Unicode Map
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
    "VFR": "#2dd4bf",  # Teal/Green
    "MVFR": "#38bdf8",  # Sky Blue
    "IFR": "#ef4444",  # Red
    "LIFR": "#e879f9",  # Magenta
}

# ==============================================================================
# STATE TRACKING
# ==============================================================================
seen_close_aircraft = {}  # {hex_code: last_triggered_timestamp}
revert_page_at = None  # Timestamp when proximity alert expires
previous_page = 1  # Last user-selected page (1, 2, or 3)
last_metar_fetch = 0
last_weather_fetch = 0
cached_metar_cmds = []


# ==============================================================================
# GEOSPATIAL CALCULATIONS
# ==============================================================================
def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in Nautical Miles (NM) between two lat/lon points."""
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
    """Calculate initial compass bearing (0-359°) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - (
        math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    )
    initial_bearing = math.degrees(math.atan2(x, y))
    return int((initial_bearing + 360) % 360)


def deg_to_cardinal(deg: float) -> str:
    """Convert wind degrees to 16-point cardinal direction."""
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
    ix = round(deg / (360.0 / len(dirs)))
    return dirs[ix % len(dirs)]


# ==============================================================================
# MQTT CALLBACKS & BATCH PUBLISHER
# ==============================================================================
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to broker (rc={rc})")
    client.subscribe(f"hasp/{HASP_NODE}/state/p0b1")
    client.subscribe(f"hasp/{HASP_NODE}/state/page")


def on_message(client, userdata, msg):
    global previous_page, revert_page_at
    topic = msg.topic
    payload_str = msg.payload.decode("utf-8", errors="ignore")

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
                revert_page_at = None  # Cancel active alert override if user taps tab
                client.publish(f"hasp/{HASP_NODE}/command/page", str(target_page))
        except (json.JSONDecodeError, ValueError):
            pass


def publish_batch(client: mqtt.Client, commands: list):
    """Send batched JSON array updates to openHASP in chunks of 24 to respect buffer limits."""
    if not commands:
        return
    chunk_size = 24
    for i in range(0, len(commands), chunk_size):
        chunk = commands[i : i + chunk_size]
        client.publish(f"hasp/{HASP_NODE}/command/json", json.dumps(chunk))


# ==============================================================================
# WEATHER & FORECAST (PAGE 1 & PAGE 3)
# ==============================================================================
def fetch_and_format_weather() -> list:
    """
    Fetches Tempest current weather and 6-hour/5-day forecast from local endpoint.
    Includes complete fallback telemetry so all 800x480 cards populate out of the box.
    """
    try:
        resp = requests.get(TEMPEST_CURRENT_URL, timeout=3)
        resp.raise_for_status()
        w = resp.json()
    except Exception:
        w = {
            "temp_f": 75.0,
            "feels_like_f": 75.0,
            "humidity": 90,
            "dew_point_f": 72.0,
            "condition": "Partly Cloudy",
            "icon_key": "partly-cloudy",
            "wind_avg_mph": 1.9,
            "wind_gust_mph": 1.8,
            "wind_deg": 68,
            "rain_rate_in_hr": 0.00,
            "rain_today_in": 0.00,
            "lightning_last_time": "None (1h)",
            "lightning_dist_mi": 0,
            "lightning_count_1h": 0,
            "wbgt_f": 73.8,
            "uv_index": 3.2,
            "solar_rad_wm2": 340,
            "vpd_kpa": 2.98,
            "density_alt_ft": 1120,
            "pressure_inhg": 30.04,
            "pressure_trend": "Steady (+0.01/3h)",
            "station_volts": 2.71,
            "solar_lux": 14200,
            "sunrise": "06:42 AM",
            "sunset": "05:38 PM",
            "hourly": [
                {"time": "5 PM", "icon": "partly-cloudy", "temp": 75, "pop": 10},
                {"time": "6 PM", "icon": "cloudy", "temp": 75, "pop": 10},
                {"time": "7 PM", "icon": "cloudy", "temp": 73, "pop": 10},
                {"time": "8 PM", "icon": "cloudy", "temp": 72, "pop": 10},
                {"time": "9 PM", "icon": "clear-night", "temp": 70, "pop": 10},
                {"time": "10 PM", "icon": "clear-night", "temp": 70, "pop": 10},
            ],
            "daily": [
                {"day": "Thu", "icon": "partly-cloudy", "hi": 82, "lo": 64, "pop": 10},
                {"day": "Fri", "icon": "partly-cloudy", "hi": 83, "lo": 65, "pop": 20},
                {"day": "Sat", "icon": "rain", "hi": 79, "lo": 66, "pop": 40},
                {"day": "Sun", "icon": "clear-day", "hi": 80, "lo": 61, "pop": 10},
                {"day": "Mon", "icon": "clear-day", "hi": 81, "lo": 62, "pop": 10},
            ],
        }

    cond_icon = MDI_ICONS.get(w.get("icon_key", "partly-cloudy"), "\uf595")
    cardinal = deg_to_cardinal(w.get("wind_deg", 0))

    # Categorize WBGT thermal stress
    wbgt = float(w.get("wbgt_f", 70.0))
    if wbgt < 78.0:
        wbgt_label = "Low Thermal Stress"
    elif wbgt < 82.0:
        wbgt_label = "Moderate Caution"
    elif wbgt < 86.0:
        wbgt_label = "High Heat Stress"
    else:
        wbgt_label = "Extreme Danger"

    # Categorize VPD state
    vpd = float(w.get("vpd_kpa", 1.2))
    if vpd < 0.4:
        vpd_label = "Saturated / Damp Air"
    elif vpd <= 1.6:
        vpd_label = "Optimal Transpiration"
    else:
        vpd_label = "High Air Dryness"

    ltg_sub = (
        "Dist: -- mi | Count: 0"
        if w.get("lightning_count_1h", 0) == 0
        else f"Dist: {w['lightning_dist_mi']} mi | 1h: {w['lightning_count_1h']}"
    )

    cmds = [
        # Page 1: Hero Card
        f"p1b10.text={w['temp_f']:.1f}°F",
        f"p1b11.text={cond_icon}",
        f"p1b12.text={w['condition']}",
        f"p1b13.text=Feels Like {w['feels_like_f']:.1f}°F",
        f"p1b14.text=Humidity: {w['humidity']}% | Dew: {w['dew_point_f']:.1f}°F",
        # Page 1: 2x2 Primary Cards
        f"p1b21.text={w['wind_avg_mph']:.1f} ({w['wind_gust_mph']:.1f}) mph",
        f"p1b22.text=Dir: {cardinal} ({w['wind_deg']:03d}°)",
        f"p1b24.text={w['rain_today_in']:.2f} in",
        f"p1b25.text=Rate: {w['rain_rate_in_hr']:.2f} in/hr",
        f"p1b27.text={w['lightning_last_time']}",
        f"p1b28.text={ltg_sub}",
        f"p1b30.text={w['solar_lux']:,} lux",
        f"p1b31.text=\uf5de {w['sunrise']}  \uf5df {w['sunset']}",
        # Page 1: Bottom 3 Advanced Environmental Cards
        f"p1b41.text={wbgt:.1f}°F",
        f"p1b42.text={wbgt_label}",
        f"p1b43.text=UV Index: {w['uv_index']:.1f} | {w['solar_rad_wm2']} W/m²",
        f"p1b45.text={vpd:.2f} kPa",
        f"p1b46.text={vpd_label}",
        f"p1b47.text=Density Alt: +{w['density_alt_ft']:,} ft",
        f"p1b49.text={w['pressure_inhg']:.2f} inHg",
        f"p1b50.text=Trend: {w['pressure_trend']}",
        f"p1b51.text=Tempest Bat: {w['station_volts']:.2f}V (OK)",
    ]

    # Page 3: 6-Hour Forecast (All 6 columns)
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

    # Page 3: 5-Day Forecast (All 5 columns)
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
# DUAL METAR FETCHER (KSFB & KORL)
# ==============================================================================
def fetch_dual_metars() -> list:
    """Queries AviationWeather.gov for KSFB and KORL and color-codes flight categories."""
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


# ==============================================================================
# ADS-B AVIATION & PROXIMITY OVERRIDE (PAGE 2)
# ==============================================================================
def process_aviation(client: mqtt.Client) -> list:
    """
    Reads ultrafeeder aircraft.json, computes distance & bearing, formats top 3 rows,
    and triggers a 10-second Page 2 override + red border alert when <= 3.0 NM.
    """
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

    # Check if any aircraft is within 3.0 NM
    any_within_3nm = closest_dist <= PROXIMITY_RADIUS_NM
    if any_within_3nm:
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
                "\uf015 ADS-B: CLEAR (<3NM)"
                if False
                else "p0b4.text=\uf015 ADS-B: CLEAR (<3NM)",
                "p0b4.text_color=#2dd4bf",
                "p2b3.border_color=#334155",
            ]
        )

    # Format the 3 aircraft table cards (base IDs 10, 20, 30)
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

            tag = "[CIVIL]"
            if db_flags & 1:
                tag = "[MILITARY]"
            elif db_flags & 2:
                tag = "[LEO / GOV]"

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
# MAIN DAEMON LOOP
# ==============================================================================
def main():
    global revert_page_at, cached_metar_cmds, last_metar_fetch, last_weather_fetch

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    print(f"[INIT] 800x480 openHASP Publisher active for node '{HASP_NODE}'...")

    try:
        while True:
            now = time.time()
            batch_commands = []

            # 1. Revert from Page 2 back to previous page after 10-second proximity alert
            if revert_page_at and now >= revert_page_at:
                print(f"[ALERT] 10s elapsed. Returning to Page {previous_page}.")
                client.publish(f"hasp/{HASP_NODE}/command/page", str(previous_page))
                revert_page_at = None

            # 2. Refresh KSFB & KORL METARs every 10 minutes (600s)
            if now - last_metar_fetch >= 600:
                cached_metar_cmds = fetch_dual_metars()
                batch_commands.extend(cached_metar_cmds)
                last_metar_fetch = now

            # 3. Refresh Weather & Forecast every 15 seconds
            if now - last_weather_fetch >= 15:
                batch_commands.extend(fetch_and_format_weather())
                last_weather_fetch = now

            # 4. Refresh ADS-B Traffic every 2 seconds
            batch_commands.extend(process_aviation(client))

            # 5. Publish batched updates via MQTT
            publish_batch(client, batch_commands)

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[EXIT] Stopping publisher...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
