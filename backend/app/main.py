"""
FastAPI entrypoint — Phase 3 (Backend).

On startup: opens one AsyncClient to Supabase (shared by every route via
app.state.supabase) and subscribes it to the `office-updates` broadcast
topic so the alert engine runs event-driven, never on a poll loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import find_dotenv, load_dotenv

# Load the nearest .env walking upward from this file — works whether
# uvicorn is launched from backend/ or the repo root.
load_dotenv(find_dotenv(usecwd=False))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import AsyncClient, acreate_client

from .alerts.rules import check_room_continuous_all, reconcile_alerts
from .realtime_listener import start_listener
from .routes import room, status, usage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("office-monitor-backend")


async def _periodic_room_check(supabase) -> None:
    """Runs check_room_continuous_all every 3 real seconds.

    The room_continuous_2h alert cannot be caught by the event-driven path
    alone: if a burst room stays fully ON with no new device events, no
    office-updates broadcast fires, so evaluate_event() is never called for
    that room. This task polls on a tight loop using the latest simulated
    timestamp from device_events so it catches the 2-hour crossing within
    a few seconds of it happening.
    """
    while True:
        await asyncio.sleep(3)
        try:
            await check_room_continuous_all(supabase)
        except Exception:
            logger.exception("Periodic room-continuous check failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    supabase_url = os.environ["SUPABASE_URL"]
    # Secret key (new naming, replaces legacy service_role key): the backend
    # evaluates/raises/clears alerts directly against Postgres and needs to
    # bypass RLS to do so reliably. Backend/simulator only — never expose this.
    supabase_key = os.environ["SUPABASE_SECRET_KEY"]

    supabase: AsyncClient = await acreate_client(supabase_url, supabase_key)
    app.state.supabase = supabase

    channel = await start_listener(supabase)
    await reconcile_alerts(supabase)

    # Periodic check for room_continuous_2h — runs every 3 real seconds.
    periodic_task = asyncio.create_task(_periodic_room_check(supabase))
    logger.info("Periodic room-continuous check started (every 3s)")

    try:
        yield
    finally:
        periodic_task.cancel()
        await channel.unsubscribe()


app = FastAPI(title="Office Monitor Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(room.router)
app.include_router(usage.router)


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    # `python -m app.main` reads BACKEND_HOST/BACKEND_PORT from .env directly.
    # For hot-reload during development, prefer:
    #   uvicorn app.main:app --reload --host $BACKEND_HOST --port $BACKEND_PORT
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("BACKEND_HOST", "0.0.0.0"),
        port=int(os.environ.get("BACKEND_PORT", "8000")),
    )
