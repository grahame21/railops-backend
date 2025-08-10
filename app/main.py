import asyncio
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from .settings import settings
from .trainfinder_client import client
from .transform import transform_trainfinder_payload

app = FastAPI(title="Train Tracker 2.0 Backend", version="1.0.0")

LATEST: Optional[dict] = None
LAST_ERROR: Optional[str] = None

async def updater_loop():
    global LATEST, LAST_ERROR
    while True:
        try:
            raw = await client.fetch_viewport()
            LATEST = transform_trainfinder_payload(raw)
            LAST_ERROR = None
        except Exception as e:
            LAST_ERROR = str(e)
        await asyncio.sleep(settings.UPDATE_INTERVAL)

@app.on_event("startup")
async def on_startup():
    # Kick off background updater
    asyncio.create_task(updater_loop())

@app.on_event("shutdown")
async def on_shutdown():
    await client.aclose()

@app.get("/healthz")
def healthz():
    if LAST_ERROR:
        return JSONResponse({"status": "degraded", "error": LAST_ERROR}, status_code=200)
    return {"status": "ok", "has_data": LATEST is not None}

@app.get("/trains.json")
def trains_json():
    if LATEST is None:
        # Fetch may not have completed yet
        raise HTTPException(status_code=503, detail="Data not ready yet")
    # Send JSON with caching disabled so your frontend always gets fresh data
    return JSONResponse(LATEST, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
    })
