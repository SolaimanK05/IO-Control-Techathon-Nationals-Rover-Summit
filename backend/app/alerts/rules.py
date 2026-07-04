"""
Alert rules engine — Implementation Plan Section 5.

Both rules are generic over N rooms/devices: nothing here ever refers to a
room or device by fixed name. Everything is looked up by the ids present in
the incoming broadcast payload plus generic queries (`eq("room_id", ...)`,
never a hardcoded id or name).

Called once per incoming `office-updates` broadcast event — never on a timer.

Rules:
  after_hours          — a single device is ON outside 9AM-5PM simulated time.
  room_continuous_2h   — every device in a room has been ON continuously,
                          without interruption, for over 2 hours.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("alerts.rules")

AFTER_HOURS_START = 9   # 9 AM simulated
AFTER_HOURS_END = 17    # 5 PM simulated
CONTINUOUS_THRESHOLD_HOURS = 2


def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _is_after_hours(ts: datetime) -> bool:
    return not (AFTER_HOURS_START <= ts.hour < AFTER_HOURS_END)


async def evaluate_event(supabase, payload: dict) -> None:
    """Entry point invoked by realtime_listener.py for every device_events
    insert broadcast on the `office-updates` topic."""
    device_id = payload["device_id"]
    room_id = payload["room_id"]
    label = payload["label"]
    new_status = bool(payload["new_status"])
    ts = _parse_ts(payload["ts"])

    await _evaluate_after_hours(supabase, device_id, room_id, label, new_status, ts)
    await _evaluate_room_continuous(supabase, room_id, new_status, ts)


async def _get_active_alert(supabase, room_id: str, alert_type: str, device_id: str | None = None):
    query = (
        supabase.table("alerts")
        .select("*")
        .eq("room_id", room_id)
        .eq("type", alert_type)
        .is_("cleared_at", "null")
    )
    if device_id is not None:
        query = query.eq("device_id", device_id)
    resp = await query.execute()
    rows = resp.data or []
    return rows[0] if rows else None


async def _clear_alert(supabase, alert_id: str, ts: datetime) -> None:
    await (
        supabase.table("alerts")
        .update({"cleared_at": ts.isoformat()})
        .eq("id", alert_id)
        .execute()
    )


async def _get_room_name(supabase, room_id: str) -> str:
    resp = await supabase.table("rooms").select("name").eq("id", room_id).execute()
    rows = resp.data or []
    return rows[0]["name"] if rows else "an unknown room"


async def _raise_alert(supabase, *, alert_type: str, room_id: str, device_id: str | None,
                        message: str, ts: datetime) -> None:
    await (
        supabase.table("alerts")
        .insert({
            "type": alert_type,
            "room_id": room_id,
            "device_id": device_id,
            "message": message,
            "raised_at": ts.isoformat(),
            "cleared_at": None,
        })
        .execute()
    )
    logger.info("Raised %s alert for room=%s device=%s", alert_type, room_id, device_id)


async def _evaluate_after_hours(supabase, device_id: str, room_id: str, label: str,
                                 new_status: bool, ts: datetime) -> None:
    existing = await _get_active_alert(supabase, room_id, "after_hours", device_id=device_id)

    if new_status and _is_after_hours(ts):
        if existing is None:
            room_name = await _get_room_name(supabase, room_id)
            message = f"{label} in {room_name} left on after hours"
            await _raise_alert(
                supabase,
                alert_type="after_hours",
                room_id=room_id,
                device_id=device_id,
                message=message,
                ts=ts,
            )
        # else: already flagged, keep the existing alert open.
    elif not new_status and existing is not None:
        await _clear_alert(supabase, existing["id"], ts)


async def _evaluate_room_continuous(supabase, room_id: str, new_status: bool, ts: datetime) -> None:
    existing = await _get_active_alert(supabase, room_id, "room_continuous_2h")

    if not new_status:
        # Anything in the room turning off breaks the continuous-on streak.
        if existing is not None:
            await _clear_alert(supabase, existing["id"], ts)
        return

    if existing is not None:
        return  # already raised and still active — nothing new to evaluate

    devices_resp = await supabase.table("devices").select("id, status").eq("room_id", room_id).execute()
    devices = devices_resp.data or []
    if not devices or not all(d["status"] for d in devices):
        return  # room isn't fully on yet

    last_on_times = []
    for device in devices:
        ev_resp = await (
            supabase.table("device_events")
            .select("ts")
            .eq("device_id", device["id"])
            .eq("new_status", True)
            .order("ts", desc=True)
            .limit(1)
            .execute()
        )
        rows = ev_resp.data or []
        if not rows:
            # A device is ON with no recorded transition-to-ON event — can't
            # establish a clean start time yet, so don't raise prematurely.
            return
        last_on_times.append(_parse_ts(rows[0]["ts"]))

    # The room has been "all on" only since whichever device was last to
    # join in — the slowest one sets the start of the continuous window.
    room_all_on_since = max(last_on_times)
    hours_on = (ts - room_all_on_since).total_seconds() / 3600.0

    if hours_on >= CONTINUOUS_THRESHOLD_HOURS:
        room_name = await _get_room_name(supabase, room_id)
        message = f"All devices in {room_name} have been on continuously for over 2 hours"
        await _raise_alert(
            supabase,
            alert_type="room_continuous_2h",
            room_id=room_id,
            device_id=None,
            message=message,
            ts=ts,
        )
