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

reconcile_alerts() is called once on startup to catch any alerts that should
already be active (e.g. after a backend restart mid-scenario). It re-evaluates
every device's current state against both rules without waiting for the next
device event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("alerts.rules")

AFTER_HOURS_START = 9   # 9 AM simulated
AFTER_HOURS_END = 17    # 5 PM simulated
CONTINUOUS_THRESHOLD_HOURS = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _is_after_hours(ts: datetime) -> bool:
    return not (AFTER_HOURS_START <= ts.hour < AFTER_HOURS_END)


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
    logger.info("Cleared alert id=%s at ts=%s", alert_id, ts.isoformat())


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
    logger.info(
        "Raised %s alert | room=%s device=%s | %s",
        alert_type, room_id, device_id, message,
    )


# ---------------------------------------------------------------------------
# Per-event evaluation (called by realtime_listener on every broadcast)
# ---------------------------------------------------------------------------

async def evaluate_event(supabase, payload: dict) -> None:
    """Entry point invoked by realtime_listener.py for every device_status_changed
    broadcast on the `office-updates` topic."""
    try:
        device_id = payload["device_id"]
        room_id = payload["room_id"]
        label = payload["label"]
        new_status = bool(payload["new_status"])
        ts = _parse_ts(payload["ts"])
    except KeyError as exc:
        logger.warning(
            "evaluate_event: missing key %s in payload — skipping. Full payload: %s",
            exc, payload,
        )
        return

    logger.debug(
        "evaluate_event: device=%s (%s) room=%s new_status=%s ts=%s",
        label, device_id, room_id, new_status, ts.isoformat(),
    )

    await _evaluate_after_hours(supabase, device_id, room_id, label, new_status, ts)
    await _evaluate_room_continuous(supabase, room_id, new_status, ts)


# ---------------------------------------------------------------------------
# Rule 1 — After-hours device left on
# ---------------------------------------------------------------------------

async def _evaluate_after_hours(supabase, device_id: str, room_id: str, label: str,
                                 new_status: bool, ts: datetime) -> None:
    existing = await _get_active_alert(supabase, room_id, "after_hours", device_id=device_id)

    if new_status and _is_after_hours(ts):
        # Device is ON outside business hours — raise if not already active.
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
        # else: already flagged — keep the existing alert open until device turns off.
    elif not new_status and existing is not None:
        # Device turned off — clear the after-hours alert.
        await _clear_alert(supabase, existing["id"], ts)


# ---------------------------------------------------------------------------
# Rule 2 — All devices in a room on continuously for > 2 hours
# ---------------------------------------------------------------------------

async def _evaluate_room_continuous(supabase, room_id: str, new_status: bool, ts: datetime) -> None:
    # room_continuous_2h alerts are NOT cleared when devices turn off.
    # Crossing the 2-hour threshold is a completed event — it stays on the
    # dashboard as a historical record until a human clears it manually.
    # Only skip evaluation if an active alert for THIS simulated day already exists.
    if not new_status:
        return  # device turning off doesn't clear or affect the 2h alert

    # Check if we already have an active (uncleared) alert for this room.
    # This prevents raising a duplicate within the same burst.
    existing = await _get_active_alert(supabase, room_id, "room_continuous_2h")
    if existing is not None:
        return  # already have an active alert — don't double-raise

    # Check if ALL devices in the room are currently ON.
    devices_resp = await supabase.table("devices").select("id, status").eq("room_id", room_id).execute()
    devices = devices_resp.data or []
    if not devices or not all(d["status"] for d in devices):
        return  # room isn't fully on yet

    # Find the most recent turn-ON event for each device — the room has been
    # "all on" only since the last device joined (slowest one sets the window start).
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
            # Device is ON but has no recorded transition-to-ON event — can't
            # establish a clean start time, so don't raise prematurely.
            return
        last_on_times.append(_parse_ts(rows[0]["ts"]))

    room_all_on_since = max(last_on_times)
    hours_on = (ts - room_all_on_since).total_seconds() / 3600.0

    logger.debug(
        "room_continuous check: room=%s all_on_since=%s hours_on=%.2f threshold=%s",
        room_id, room_all_on_since.isoformat(), hours_on, CONTINUOUS_THRESHOLD_HOURS,
    )

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


# ---------------------------------------------------------------------------
# Shared helper — latest simulated timestamp from device_events
# ---------------------------------------------------------------------------

async def _get_sim_now(supabase) -> datetime | None:
    """Returns the most recent simulated timestamp recorded in device_events,
    or None if no events exist yet. This is used as the simulated 'now' for
    time-based checks that run outside of a realtime event callback."""
    resp = await (
        supabase.table("device_events")
        .select("ts")
        .order("ts", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return _parse_ts(rows[0]["ts"]) if rows else None


# ---------------------------------------------------------------------------
# Periodic room-continuous check (background task, every few seconds)
# ---------------------------------------------------------------------------

async def check_room_continuous_all(supabase) -> None:
    """
    Checks every room for the room_continuous_2h condition using the latest
    known simulated timestamp.

    This MUST be called periodically (not just on events) because the
    'all devices on for 2+ hours' condition becomes true because TIME passes,
    not because a device state CHANGES. If a burst room stays fully ON with
    zero new events, the event-driven path in evaluate_event() never fires
    for that room — so this periodic sweep is the only path that catches it.

    Uses device_events.ts as simulated 'now' so the comparison is always
    between two simulated timestamps, never mixing real and simulated time.
    """
    sim_now = await _get_sim_now(supabase)
    if sim_now is None:
        return  # no events yet, nothing to check

    # Load all rooms with their devices in one query
    rooms_resp = await (
        supabase.table("rooms")
        .select("id, devices(id, status)")
        .execute()
    )

    for room in (rooms_resp.data or []):
        room_id = room["id"]
        devices = room.get("devices") or []

        # Skip rooms that aren't fully ON — no alert possible
        if not devices or not all(d["status"] for d in devices):
            continue

        # Find the most recent turn-ON event per device to establish
        # when this specific burst started
        last_on_times = []
        skip_room = False
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
                skip_room = True
                break
            last_on_times.append(_parse_ts(rows[0]["ts"]))

        if skip_room:
            continue

        # The room has been "all on" since the LAST device joined in
        room_all_on_since = max(last_on_times)
        hours_on = (sim_now - room_all_on_since).total_seconds() / 3600.0

        logger.debug(
            "periodic check room=%s all_on_since=%s sim_now=%s hours_on=%.2f",
            room_id, room_all_on_since.isoformat(), sim_now.isoformat(), hours_on,
        )

        if hours_on < CONTINUOUS_THRESHOLD_HOURS:
            continue  # threshold not yet crossed

        # Only skip if an alert was already raised for THIS specific burst window
        # (raised_at >= room_all_on_since). This allows a fresh alert on each new
        # burst even if a previous day's alert was never manually cleared.
        already_alerted_resp = await (
            supabase.table("alerts")
            .select("id")
            .eq("room_id", room_id)
            .eq("type", "room_continuous_2h")
            .gte("raised_at", room_all_on_since.isoformat())
            .limit(1)
            .execute()
        )
        if already_alerted_resp.data:
            continue  # already raised an alert for this burst window

        room_name = await _get_room_name(supabase, room_id)
        message = (
            f"All devices in {room_name} have been on continuously "
            f"for over {CONTINUOUS_THRESHOLD_HOURS} hours"
        )
        await _raise_alert(
            supabase,
            alert_type="room_continuous_2h",
            room_id=room_id,
            device_id=None,
            message=message,
            ts=sim_now,
        )


# ---------------------------------------------------------------------------
# Startup reconciliation sweep
# ---------------------------------------------------------------------------

async def reconcile_alerts(supabase) -> None:
    """
    Scans ALL current device states and raises any alerts that should already
    be active but aren't recorded yet.

    Handles backend restarts mid-scenario. Uses simulated time from
    device_events (not wall-clock UTC) so time comparisons are correct.
    """
    logger.info("Starting alert reconciliation sweep...")

    try:
        sim_now = await _get_sim_now(supabase)

        devices_resp = await (
            supabase.table("devices")
            .select("id, room_id, label, type, status, watts, last_changed")
            .execute()
        )
        devices = devices_resp.data or []

        if not devices:
            logger.info("Reconciliation: no devices found — skipping.")
            return

        # --- Rule 1: after_hours — any ON device outside 9AM-5PM simulated ---
        for device in devices:
            if not device["status"]:
                continue
            # Use the device's own last_changed as the simulated reference time
            dev_ts = _parse_ts(device["last_changed"]) if device["last_changed"] else sim_now
            if dev_ts is not None and _is_after_hours(dev_ts):
                existing = await _get_active_alert(
                    supabase, device["room_id"], "after_hours", device_id=device["id"]
                )
                if existing is None:
                    room_name = await _get_room_name(supabase, device["room_id"])
                    message = f"{device['label']} in {room_name} left on after hours"
                    await _raise_alert(
                        supabase,
                        alert_type="after_hours",
                        room_id=device["room_id"],
                        device_id=device["id"],
                        message=message,
                        ts=dev_ts,
                    )

        # --- Rule 2: room_continuous_2h — reuse the periodic checker ---
        if sim_now is not None:
            await check_room_continuous_all(supabase)

    except Exception:
        logger.exception("Reconciliation sweep failed — continuing startup anyway.")

    logger.info("Alert reconciliation sweep complete.")


