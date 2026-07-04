"""GET /usage — instantaneous power + time-weighted kWh today. api-contract.md §3."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..kwh import compute_kwh_for_day, parse_ts

router = APIRouter()


@router.get("/usage")
async def get_usage(request: Request):
    supabase = request.app.state.supabase

    devices_resp = await supabase.table("devices").select("*").execute()
    devices = devices_resp.data or []

    total_power_watts_now = sum(d["watts"] for d in devices if d["status"])

    # The backend doesn't own the simulated clock, so "now" for the purposes
    # of the integral is approximated as the most recent last_changed value
    # across all devices — the freshest simulated timestamp we actually have.
    last_changed_values = [d["last_changed"] for d in devices if d.get("last_changed")]
    as_of = max((parse_ts(v) for v in last_changed_values), default=datetime.now(timezone.utc))

    day_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)

    events_resp = await (
        supabase.table("device_events")
        .select("device_id, prev_status, new_status, ts")
        .gte("ts", day_start.isoformat())
        .lte("ts", as_of.isoformat())
        .order("ts")
        .execute()
    )
    events = events_resp.data or []

    events_by_device: dict[str, list[dict]] = {}
    for event in events:
        events_by_device.setdefault(event["device_id"], []).append(event)

    estimated_kwh_today = compute_kwh_for_day(devices, events_by_device, day_start, as_of)

    return {
        "total_power_watts_now": total_power_watts_now,
        "estimated_kwh_today": round(estimated_kwh_today, 4),
        "as_of": as_of.isoformat(),
    }
