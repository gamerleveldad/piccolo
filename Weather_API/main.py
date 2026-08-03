import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
import math
import json
import asyncpg

app = FastAPI(title="Maverick Weather API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "weatherflow")

def get_async_influx_client() -> InfluxDBClientAsync:
    return InfluxDBClientAsync(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

# --- PostgreSQL Configuration ---
PG_HOST = os.environ.get("POSTGRES_HOST", "postgres_db")
PG_DB = os.environ.get("POSTGRES_DB")
PG_USER = os.environ.get("POSTGRES_USER")
PG_PASS = os.environ.get("POSTGRES_PASSWORD")

async def get_pg_conn():
    return await asyncpg.connect(
        host=PG_HOST,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS
    )

def safe_float(val) -> float | None:
    """Helper to convert asyncpg Decimal objects to standard floats for JSON."""
    return float(val) if val is not None else None

# Unit conversion helpers
def c_to_f(c_temp: float | None) -> float | None:
    if c_temp is None:
        return None
    return round((c_temp * 9 / 5) + 32, 1)

def ms_to_mph(ms_speed: float | None) -> float | None:
    if ms_speed is None:
        return None
    return round(ms_speed * 2.23694, 1)

def mm_to_inches(mm_val: float | None) -> float:
    if mm_val is None:
        return 0.0
    return round(mm_val / 25.4, 2)

def hpa_to_inhg(hpa_val: float | None) -> float | None:
    if hpa_val is None:
        return None
    return round(hpa_val * 0.0295301, 2)

def calculate_heat_misery(wbgt_c: float | None) -> int:
    if wbgt_c is None: 
        return 0
    wbgt_f = c_to_f(wbgt_c)
    if wbgt_f is None: 
        return 0
    if wbgt_f <= 70: 
        return 0
    if wbgt_f >= 90: 
        return 10
    return round((wbgt_f - 70) / 2.0)

def calculate_humidity_misery(vpd_kpa: float | None) -> int:
    if vpd_kpa is None: 
        return 0
    if vpd_kpa >= 1.5: 
        return 0
    if vpd_kpa <= 0.5: 
        return 10
    return round(10 - ((vpd_kpa - 0.5) * 10))

def calculate_density_altitude(temp_c: float | None, dewpoint_c: float | None, pressure_mb: float | None) -> int | None:
    # Explicitly check each variable to trigger Pylance type narrowing
    if temp_c is None or dewpoint_c is None or pressure_mb is None: 
        return None
    
    try:
        e = 6.11 * (10 ** ((7.5 * dewpoint_c) / (237.3 + dewpoint_c)))
        temp_k = temp_c + 273.15
        tv_k = temp_k / (1 - (e / pressure_mb) * (1 - 0.622))
        tv_r = tv_k * 1.8  
        p_inhg = pressure_mb * 0.0295301  
        da_ft = 145366 * (1 - ((17.326 * p_inhg) / tv_r) ** 0.235)
        return int(round(da_ft))
    except Exception:
        return None

@app.get("/health")
async def health_check() -> Dict[str, str]:
    async with get_async_influx_client() as client:
        health = await client.health()
        if health.status == "pass":
            return {"status": "up", "influxdb": "connected"}
        raise HTTPException(status_code=503, detail="InfluxDB unhealthy")

@app.get("/api/weather/forecast/daily")
async def get_daily_forecast() -> List[Dict[str, Any]]:
    """
    Retrieves daily forecast records, dynamically calculating max wind and accumulated precipitation 
    from hourly forecast records to complete missing fields. Converts all values to Imperial units.
    """
    daily_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1d, stop: 10d)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_daily")
      |> keep(columns: ["_time", "_field", "_value"])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    hourly_summary_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1d, stop: 10d)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_hourly")
      |> filter(fn: (r) => r["_field"] == "precip" or r["_field"] == "wind_avg" or r["_field"] == "wind_gust")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    try:
        async with get_async_influx_client() as client:
            query_api = client.query_api()
            daily_tables = await query_api.query(daily_query)
            hourly_tables = await query_api.query(hourly_summary_query)

        # Aggregate missing daily fields from hourly data indexed by date string (YYYY-MM-DD)
        hourly_aggregates = {}
        for table in hourly_tables:
            for record in table.records:
                rec_time = record.get_time()
                date_key = rec_time.strftime("%Y-%m-%d")
                
                if date_key not in hourly_aggregates:
                    hourly_aggregates[date_key] = {"precip_accum_mm": 0.0, "max_wind_ms": 0.0}
                
                precip = record.values.get("precip", 0.0) or 0.0
                wind_gust = record.values.get("wind_gust", 0.0) or 0.0
                wind_avg = record.values.get("wind_avg", 0.0) or 0.0
                max_wind = max(wind_gust, wind_avg)

                hourly_aggregates[date_key]["precip_accum_mm"] += precip
                if max_wind > hourly_aggregates[date_key]["max_wind_ms"]:
                    hourly_aggregates[date_key]["max_wind_ms"] = max_wind

        results = []
        for table in daily_tables:
            for record in table.records:
                rec_time = record.get_time()
                date_key = rec_time.strftime("%Y-%m-%d")
                day_name = rec_time.strftime("%a")

                hourly_data = hourly_aggregates.get(date_key, {"precip_accum_mm": 0.0, "max_wind_ms": 0.0})

                results.append({
                    "date": date_key,
                    "day_name": day_name,
                    "temp_max_f": c_to_f(record.values.get("air_temp_high")),
                    "temp_min_f": c_to_f(record.values.get("air_temp_low")),
                    "conditions": record.values.get("conditions", "Unknown"),
                    "icon": record.values.get("icon", ""),
                    "precip_probability": record.values.get("precip_probability", 0),
                    "precip_accum_in": mm_to_inches(hourly_data["precip_accum_mm"]),
                    "max_wind_speed_mph": ms_to_mph(hourly_data["max_wind_ms"])
                })

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/weather/current")
async def get_current_weather() -> Dict[str, Any]:
    """
    Retrieves the latest observation and the current forecast conditions
    using separate queries to avoid schema collisions, then merges them.
    """
    obs_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs")
      |> last()
      |> keep(columns: ["_field", "_value"])
    '''
    
    forecast_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_current")
      |> last()
      |> keep(columns: ["_field", "_value"])
    '''
    
    try:
        async with get_async_influx_client() as client:
            query_api = client.query_api()
            # Await both queries
            obs_tables = await query_api.query(obs_query)
            forecast_tables = await query_api.query(forecast_query)

        raw_data = {}
        
        # Merge observation metrics (floats/ints)
        for table in obs_tables:
            for record in table.records:
                raw_data[record.get_field()] = record.get_value()
                
        # Merge forecast conditions (strings)
        for table in forecast_tables:
            for record in table.records:
                raw_data[record.get_field()] = record.get_value()

        return {
            "time": datetime.now(timezone.utc).isoformat(),
            "temp_f": c_to_f(raw_data.get("air_temperature")),
            "feels_like_f": c_to_f(raw_data.get("feels_like")),
            "dew_point_f": c_to_f(raw_data.get("dew_point")),
            "relative_humidity": raw_data.get("relative_humidity"),
            "wind_avg_mph": ms_to_mph(raw_data.get("wind_avg")),
            "wind_gust_mph": ms_to_mph(raw_data.get("wind_gust")),
            "wind_direction": raw_data.get("wind_direction_cardinal", ""),
            "precip_in": mm_to_inches(raw_data.get("precip_accum_local_day")),
            "sea_level_pressure_inhg": hpa_to_inhg(raw_data.get("calculated_sea_level_pressure")),
            "uv_index": raw_data.get("uv"),
            "solar_radiation": raw_data.get("solar_radiation"),
            "lightning_strike_count": raw_data.get("lightning_strike_count"),
            "lightning_strike_last_distance": raw_data.get("lightning_strike_last_distance"),
            "conditions": raw_data.get("conditions", "Unknown"),
            "icon": raw_data.get("icon", "unknown")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/forecast/hourly")
async def get_hourly_forecast() -> List[Dict[str, Any]]:
    """
    Retrieves the next 6 hours of forecast data, pivoted into single hourly objects,
    with units converted to Imperial standard (with dual pressure).
    """
    now = datetime.now(timezone.utc)
    start_time = now.replace(minute=0, second=0, microsecond=0)
    stop_time = start_time + timedelta(hours=7)
    
    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    stop_str = stop_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_str}, stop: {stop_str})
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_hourly")
      |> keep(columns: ["_time", "_field", "_value"])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    
    try:
        async with get_async_influx_client() as client:
            query_api = client.query_api()
            tables = await query_api.query(query)

        forecast_data = []
        for table in tables:
            for record in table.records:
                forecast_data.append({
                    "time": record.get_time().isoformat(),
                    "temp_f": c_to_f(record.values.get("air_temperature")),
                    "feels_like_f": c_to_f(record.values.get("feels_like")),
                    "conditions": record.values.get("conditions", "Unknown"),
                    "icon": record.values.get("icon", ""),
                    "precip_probability": record.values.get("precip_probability", 0),
                    "precip_in": mm_to_inches(record.values.get("precip")),
                    "wind_avg_mph": ms_to_mph(record.values.get("wind_avg")),
                    "wind_gust_mph": ms_to_mph(record.values.get("wind_gust")),
                    "wind_direction": record.values.get("wind_direction_cardinal", ""),
                    "sea_level_pressure_inhg": hpa_to_inhg(record.values.get("sea_level_pressure")),
                    "sea_level_pressure_mbar": record.values.get("sea_level_pressure"),
                    "relative_humidity": record.values.get("relative_humidity"),
                    "uv": record.values.get("uv")
                })

        return forecast_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/weather/forecast/accuracy")
async def get_forecast_accuracy() -> List[Dict[str, Any]]:
    """
    Calculates Mean Absolute Error (MAE) for high temperature and feels-like temperature,
    along with directional precipitation accuracy across lead days 0 through 3 over a rolling 14-day window.
    """
    accuracy_query = f'''
    obs = from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -14d)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs")
      |> filter(fn: (r) => r["_field"] == "air_temperature" or r["_field"] == "feels_like" or r["_field"] == "precip_total_1h")
      |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")

    forecast = from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -14d)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_hourly")
      |> filter(fn: (r) => r["_field"] == "air_temperature" or r["_field"] == "feels_like" or r["_field"] == "precip_probability")
      |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
      |> pivot(rowKey: ["_time", "number_of_days_out"], columnKey: ["_field"], valueColumn: "_value")

    join(tables: {{obs: obs, fcst: forecast}}, on: ["_time"])
    '''

    try:
        async with get_async_influx_client() as client:
            query_api = client.query_api()
            tables = await query_api.query(accuracy_query)

        # Structure metrics by lead day (0 to 3)
        lead_metrics = {i: {"temp_diffs": [], "feels_diffs": [], "precip_hits": 0, "total_samples": 0} for i in range(4)}

        for table in tables:
            for record in table.records:
                lead_day = record.values.get("number_of_days_out")
                try:
                    lead_day = int(lead_day)
                except (ValueError, TypeError):
                    continue

                if lead_day not in lead_metrics:
                    continue

                obs_temp = record.values.get("air_temperature_obs")
                fcst_temp = record.values.get("air_temperature_fcst")
                obs_feels = record.values.get("feels_like_obs")
                fcst_feels = record.values.get("feels_like_fcst")
                obs_precip = record.values.get("precip_total_1h_obs", 0.0) or 0.0
                fcst_prob = record.values.get("precip_probability_fcst", 0) or 0

                if obs_temp is not None and fcst_temp is not None:
                    lead_metrics[lead_day]["temp_diffs"].append(abs(c_to_f(obs_temp) - c_to_f(fcst_temp)))

                if obs_feels is not None and fcst_feels is not None:
                    lead_metrics[lead_day]["feels_diffs"].append(abs(c_to_f(obs_feels) - c_to_f(fcst_feels)))

                # Directional precip evaluation (hit if forecasted precip > 30% and rain occurred, or prob <= 30% and no rain)
                rain_occurred = obs_precip > 0.1
                predicted_rain = fcst_prob > 30
                if rain_occurred == predicted_rain:
                    lead_metrics[lead_day]["precip_hits"] += 1
                
                lead_metrics[lead_day]["total_samples"] += 1

        accuracy_results = []
        for lead_day in range(4):
            data = lead_metrics[lead_day]
            samples = data["total_samples"] or 1
            
            temp_mae = round(sum(data["temp_diffs"]) / len(data["temp_diffs"]), 1) if data["temp_diffs"] else 0.0
            feels_mae = round(sum(data["feels_diffs"]) / len(data["feels_diffs"]), 1) if data["feels_diffs"] else 0.0
            precip_acc = round((data["precip_hits"] / samples) * 100, 1)

            accuracy_results.append({
                "lead_days": lead_day,
                "temp_mae_f": temp_mae,
                "feels_like_mae_f": feels_mae,
                "precip_accuracy_pct": precip_acc
            })

        return accuracy_results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/advanced/current")
async def get_current_advanced() -> Dict[str, Any]:
    """Retrieves current advanced metrics including the 0-10 misery indexes."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs")
      |> last()
      |> keep(columns: ["_time", "_field", "_value"])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    
    try:
        async with get_async_influx_client() as client:
            tables = await client.query_api().query(query)

        for table in tables:
            for record in table.records:
                wbgt_c = record.values.get("wet_bulb_globe_temperature")
                vpd = record.values.get("calculated_vpd")
                return {
                    "time": record.get_time().isoformat(),
                    "wbgt_f": c_to_f(wbgt_c),
                    "heat_misery_index": calculate_heat_misery(wbgt_c),
                    "vpd_kpa": vpd,
                    "humidity_misery_index": calculate_humidity_misery(vpd),
                    "delta_t_c": record.values.get("delta_t"),
                    "air_density_kg_m3": record.values.get("air_density"),
                    "illuminance_lux": record.values.get("illuminance")
                }
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/advanced/hourly")
async def get_hourly_advanced() -> List[Dict[str, Any]]:
    """Retrieves 6-hour forecast for advanced metrics and misery indexes."""
    now = datetime.now(timezone.utc)
    start_time = now.replace(minute=0, second=0, microsecond=0)
    stop_time = start_time + timedelta(hours=7)
    
    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    stop_str = stop_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_str}, stop: {stop_str})
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_hourly")
      |> keep(columns: ["_time", "_field", "_value"])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    
    try:
        async with get_async_influx_client() as client:
            tables = await client.query_api().query(query)

        forecast_data = []
        for table in tables:
            for record in table.records:
                # Assuming WBGT isn't in forecast, fallback to Heat Index or feels_like
                feels_c = record.values.get("feels_like")
                vpd = record.values.get("calculated_vpd")
                
                # Approximate Heat Misery using Feels Like for future forecasts
                heat_misery = calculate_heat_misery(feels_c)
                
                forecast_data.append({
                    "time": record.get_time().isoformat(),
                    "heat_misery_index": heat_misery,
                    "vpd_kpa": vpd,
                    "humidity_misery_index": calculate_humidity_misery(vpd),
                })
        return forecast_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/aviation")
async def get_aviation_weather() -> Dict[str, Any]:
    """Retrieves critical flight metrics including a dynamic Density Altitude calculation."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs")
      |> last()
      |> keep(columns: ["_time", "_field", "_value"])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    
    try:
        async with get_async_influx_client() as client:
            tables = await client.query_api().query(query)

        for table in tables:
            for record in table.records:
                temp_c = record.values.get("air_temperature")
                dewpoint_c = record.values.get("dew_point")
                pressure_mb = record.values.get("station_pressure")
                
                da_ft = calculate_density_altitude(temp_c, dewpoint_c, pressure_mb)
                
                return {
                    "time": record.get_time().isoformat(),
                    "density_altitude_ft": da_ft,
                    "station_pressure_inhg": hpa_to_inhg(pressure_mb),
                    "station_pressure_mb": pressure_mb,
                    "sea_level_pressure_inhg": hpa_to_inhg(record.values.get("calculated_sea_level_pressure")),
                    "wind_avg_mph": ms_to_mph(record.values.get("wind_avg")),
                    "wind_gust_mph": ms_to_mph(record.values.get("wind_gust")),
                    "wind_direction": record.values.get("wind_direction_cardinal", ""),
                    "visibility_index": record.values.get("calculated_visibility_index")
                }
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calc_vapor_pressure_inhg(temp_c: float | None) -> float | None:
    """Calculates vapor pressure in inHg using the Tetens formula."""
    if temp_c is None: 
        return None
    # Calculate mb first, then convert to inHg
    mb = 6.11 * (10 ** ((7.5 * temp_c) / (237.3 + temp_c)))
    return mb * 0.0295301

def calculate_evaporation_gallons(water_temp_c: float | None, dewpoint_c: float | None, wind_ms: float | None, hours: int) -> float:
    """Calculates pool evaporation in gallons using the Carrier mass transfer equation."""
    if water_temp_c is None or dewpoint_c is None or wind_ms is None: 
        return 0.0
    
    pw = calc_vapor_pressure_inhg(water_temp_c)
    pa = calc_vapor_pressure_inhg(dewpoint_c)
    
    # If air vapor pressure is higher than water vapor pressure, condensation occurs (no evaporation)
    if pw is None or pa is None or pw < pa: 
        return 0.0 
    
    wind_mph = ms_to_mph(wind_ms)
    if wind_mph is None: 
        wind_mph = 0.0
        
    wind_ft_min = wind_mph * 88
    
    # Carrier equation for lbs/hr
    w_lbs_hr = (450 * (pw - pa) * (95 + 0.425 * wind_ft_min)) / 1050
    gallons_hr = w_lbs_hr / 8.33
    
    return round(gallons_hr * hours, 1)

@app.get("/api/weather/pool")
async def get_pool_evaporation() -> Dict[str, Any]:
    """
    Calculates estimated pool evaporation and net water loss/gain 
    over the last 24, 48, and 72 hours.
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=3)
    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # We query the raw data for the last 3 days
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_str})
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs")
      |> filter(fn: (r) => r["_field"] == "air_temperature" or r["_field"] == "dew_point" or r["_field"] == "wind_avg" or r["_field"] == "local_daily_rain_accumulation")
      |> keep(columns: ["_time", "_field", "_value"])
    '''
    
    try:
        async with get_async_influx_client() as client:
            tables = await client.query_api().query(query)

        # Initialize lists to hold data for the 3 time windows
        data = {
            1: {"temp": [], "dew": [], "wind": [], "rain_maxes": {}},
            2: {"temp": [], "dew": [], "wind": [], "rain_maxes": {}},
            3: {"temp": [], "dew": [], "wind": [], "rain_maxes": {}}
        }

        for table in tables:
            for record in table.records:
                rec_time = record.get_time()
                field = record.get_field()
                val = record.get_value()
                
                if val is None: continue
                
                # Determine how many days ago this record was (1, 2, or 3)
                delta_hours = (now - rec_time).total_seconds() / 3600
                day_key = rec_time.strftime("%Y-%m-%d")

                # Add data to the appropriate rolling windows
                windows_to_update = []
                if delta_hours <= 24: windows_to_update.extend([1, 2, 3])
                elif delta_hours <= 48: windows_to_update.extend([2, 3])
                elif delta_hours <= 72: windows_to_update.append(3)

                for w in windows_to_update:
                    if field == "air_temperature": data[w]["temp"].append(val)
                    elif field == "dew_point": data[w]["dew"].append(val)
                    elif field == "wind_avg": data[w]["wind"].append(val)
                    elif field == "local_daily_rain_accumulation":
                        # Rain accumulates daily, so we track the max value reached each calendar day
                        current_max = data[w]["rain_maxes"].get(day_key, 0.0)
                        if val > current_max:
                            data[w]["rain_maxes"][day_key] = val

        results = {}
        for days in [1, 2, 3]:
            w_data = data[days]
            if not w_data["temp"]: 
                continue
                
            avg_temp = sum(w_data["temp"]) / len(w_data["temp"])
            avg_dew = sum(w_data["dew"]) / len(w_data["dew"])
            avg_wind = sum(w_data["wind"]) / len(w_data["wind"])
            
            # Sum the daily max rain accumulations (in mm, convert to inches)
            total_rain_mm = sum(w_data["rain_maxes"].values())
            total_rain_in = total_rain_mm / 25.4
            
            # 1 inch of rain over 1 sq ft = 0.623 gallons
            rain_gallons = round(total_rain_in * 450 * 0.623, 1)
            evap_gallons = calculate_evaporation_gallons(avg_temp, avg_dew, avg_wind, days * 24)
            
            net_gallons = round(rain_gallons - evap_gallons, 1)
            # Positive net_inches means pool level rose, negative means it dropped
            net_inches = round(net_gallons / (450 * 0.623), 2)
            
            results[f"last_{days}_days"] = {
                "estimated_water_temp_f": c_to_f(avg_temp),
                "evaporated_gallons": evap_gallons,
                "rain_added_gallons": rain_gallons,
                "net_volume_change_gallons": net_gallons,
                "net_level_change_inches": net_inches
            }

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/lightning/recent")
async def get_recent_lightning() -> List[Dict[str, Any]]:
    """Retrieves lightning strikes recorded within the last 60 minutes."""
    try:
        conn = await get_pg_conn()
        # Querying the last hour of strikes
        records = await conn.fetch('''
            SELECT lat, lon, timestamp
            FROM lightning_strikes
            WHERE timestamp >= NOW() - INTERVAL '1 hour'
            ORDER BY timestamp DESC
        ''')
        await conn.close()
        
        return [
            {
                "lat": safe_float(r["lat"]), 
                "lon": safe_float(r["lon"]), 
                "timestamp": r["timestamp"].isoformat()
            } 
            for r in records
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weather/stormcells/active")
async def get_active_stormcells() -> List[Dict[str, Any]]:
    """
    Retrieves active storm cells plotted in the last 30 minutes, 
    complete with movement vectors and forecast cone coordinates.
    """
    try:
        conn = await get_pg_conn()
        records = await conn.fetch('''
            SELECT cell_id, lat, lon, heading_deg, speed_kts, tvs, mda, vil, 
                   height_ft, top_ft, hail_prob, hail_prob_severe, hail_max_size_in, 
                   forecast_cone_narrow, forecast_cone_wide, traits, timestamp
            FROM storm_cells
            WHERE timestamp >= NOW() - INTERVAL '30 minutes'
        ''')
        await conn.close()

        cells = []
        for r in records:
            # Parse JSONB text strings back into standard Python lists/dicts for Leaflet
            cone_narrow = json.loads(r["forecast_cone_narrow"]) if r["forecast_cone_narrow"] else None
            cone_wide = json.loads(r["forecast_cone_wide"]) if r["forecast_cone_wide"] else None
            traits = json.loads(r["traits"]) if r["traits"] else None

            cells.append({
                "cell_id": r["cell_id"],
                "timestamp": r["timestamp"].isoformat(),
                "location": {
                    "lat": safe_float(r["lat"]),
                    "lon": safe_float(r["lon"])
                },
                "movement": {
                    "heading_deg": safe_float(r["heading_deg"]),
                    "speed_kts": safe_float(r["speed_kts"]),
                    "speed_mph": ms_to_mph(safe_float(r["speed_kts"]) * 1.15078) if r["speed_kts"] else None
                },
                "severity": {
                    "tornadic_vortex_signature": r["tvs"],
                    "mesocyclone_mda": safe_float(r["mda"]),
                    "vertically_integrated_liquid": safe_float(r["vil"]),
                    "max_hail_size_in": safe_float(r["hail_max_size_in"]),
                    "hail_prob_pct": safe_float(r["hail_prob"]),
                    "hail_severe_pct": safe_float(r["hail_prob_severe"])
                },
                "structure": {
                    "base_height_ft": safe_float(r["height_ft"]),
                    "top_height_ft": safe_float(r["top_ft"])
                },
                "forecast_polygons": {
                    "narrow": cone_narrow,
                    "wide": cone_wide
                },
                "traits": traits
            })
        return cells
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weather/tropics/active")
async def get_active_tropics() -> List[Dict[str, Any]]:
    """Retrieves currently active named tropical storms and their forecast tracks."""
    try:
        conn = await get_pg_conn()
        records = await conn.fetch('''
            SELECT id, name, category, lat, lon, wind_speed_mph, gust_speed_mph, 
                   pressure_mb, advisory_number, movement_dir_deg, movement_speed_mph, 
                   wind_radii, forecast_track, breakpoint_alerts, timestamp
            FROM tropical_storms
            WHERE is_active = TRUE
        ''')
        await conn.close()

        storms = []
        for r in records:
            storms.append({
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "last_updated": r["timestamp"].isoformat(),
                "advisory_number": r["advisory_number"],
                "location": {
                    "lat": safe_float(r["lat"]),
                    "lon": safe_float(r["lon"])
                },
                "intensity": {
                    "wind_speed_mph": safe_float(r["wind_speed_mph"]),
                    "gust_speed_mph": safe_float(r["gust_speed_mph"]),
                    "pressure_mb": safe_float(r["pressure_mb"]),
                    "pressure_inhg": hpa_to_inhg(safe_float(r["pressure_mb"]))
                },
                "movement": {
                    "heading_deg": safe_float(r["movement_dir_deg"]),
                    "speed_mph": safe_float(r["movement_speed_mph"])
                },
                # JSONB columns parsed to native objects
                "wind_radii": json.loads(r["wind_radii"]) if r["wind_radii"] else None,
                "forecast_track": json.loads(r["forecast_track"]) if r["forecast_track"] else [],
                "breakpoint_alerts": json.loads(r["breakpoint_alerts"]) if r["breakpoint_alerts"] else []
            })
        return storms
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weather/tropics/outlook")
async def get_tropics_outlook() -> Dict[str, Any]:
    """Retrieves the latest regional development favorability and outlook probabilities."""
    try:
        conn = await get_pg_conn()
        # Grab the single most recently updated row to retrieve the broader outlook stats
        record = await conn.fetchrow('''
            SELECT atlantic_favor, carrib_favor, gulf_favor, 
                   outlook_2day_pct, outlook_7day_pct, timestamp
            FROM tropical_storms
            ORDER BY timestamp DESC
            LIMIT 1
        ''')
        await conn.close()

        if record:
            return {
                "regional_favorability": {
                    "atlantic": record["atlantic_favor"],
                    "caribbean": record["carrib_favor"],
                    "gulf_of_mexico": record["gulf_favor"]
                },
                "development_probabilities": {
                    "48_hour_pct": record["outlook_2day_pct"],
                    "7_day_pct": record["outlook_7day_pct"]
                },
                "last_updated": record["timestamp"].isoformat()
            }
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))