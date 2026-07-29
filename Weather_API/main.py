import os
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient

# Initialize the application ONCE
app = FastAPI(title="Maverick Weather API")

# Attach CORS middleware to the active app instance
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

def get_influx_client():
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Endpoint for Uptime Kuma to monitor API health and InfluxDB connectivity.
    """
    try:
        client = get_influx_client()
        health = client.health()
        client.close()
        if health.status == "pass":
            return {"status": "up", "influxdb": "connected"}
        raise HTTPException(status_code=503, detail="InfluxDB unhealthy")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/api/weather/current")
async def get_current_weather() -> Dict[str, Any]:
    """
    Retrieves the latest observations from weatherflow_obs and weatherflow_evt_strike.
    """
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_obs" or r["_measurement"] == "weatherflow_evt_strike")
      |> last()
    '''
    try:
        client = get_influx_client()
        query_api = client.query_api()
        tables = query_api.query(query)
        client.close()

        result = {}
        for table in tables:
            for record in table.records:
                result[record.get_field()] = record.get_value()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weather/forecast/hourly")
async def get_hourly_forecast() -> List[Dict[str, Any]]:
    """
    Retrieves the next 6 hours of forecast data from weatherflow_forecast_hourly.
    """
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "weatherflow_forecast_hourly")
      |> last()
      |> limit(n: 6)
    '''
    try:
        client = get_influx_client()
        query_api = client.query_api()
        tables = query_api.query(query)
        client.close()

        forecast_data = []
        for table in tables:
            for record in table.records:
                forecast_data.append({
                    "time": record.get_time().isoformat(),
                    "field": record.get_field(),
                    "value": record.get_value()
                })

        return forecast_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))