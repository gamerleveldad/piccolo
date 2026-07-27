import os
import asyncpg
from typing import List, Dict, Any
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres_db")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "postgres")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DB}"

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

db = Database()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()

app = FastAPI(lifespan=lifespan, title="Maverick Flight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Endpoint for Uptime Kuma to verify the container and database connection are active.
    """
    try:
        async with db.pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return {"status": "up", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database connection failed")

@app.get("/api/flights/active")
async def get_active_flights(minutes_ago: int = 60) -> List[Dict[str, Any]]:
    """
    Retrieves active flights tracked within the specified time window.
    """
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_ago)
    
    query = """
        SELECT *
        FROM flights_overhead
        WHERE last_seen >= $1
    """
    
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, cutoff_time)
            results = []
            for row in rows:
                item = dict(row)
                # Convert datetime values to ISO format strings for JSON serialization
                for k, v in item.items():
                    if isinstance(v, datetime):
                        item[k] = v.isoformat()
                results.append(item)
            return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))