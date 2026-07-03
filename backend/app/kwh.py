"""
Time-weighted kWh integral over device_events.

Per api-contract.md Section 3 / Implementation Plan Section 4.5:
    estimated_kwh_today = sum(watts * duration_on) per device, per on/off
    interval — never avg_power * hours_elapsed, since toggles are irregular.

Design note (flagged in the Implementation Plan as a Phase 3 question):
the simulator has its own copy of this same logic in Python, and ideally it
would live once as a shared Postgres function/view so both processes read
from a single source of truth. For this phase we keep it as a pure-Python
function against device_events (the one thing both processes already share),
since that's the language-agnostic contract between them. A `kwh_today()`
SQL function consuming the same devices/device_events tables would be a
reasonable follow-up if Phase 1's owner wants to collapse the duplication.

This module has no knowledge of which/how many rooms or devices exist —
it operates on whatever device rows and event rows it's handed.
"""

from __future__ import annotations

from datetime import datetime


def parse_ts(ts) -> datetime:
    """Accepts either a datetime or an ISO-8601 string (with trailing 'Z')."""
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def compute_kwh_for_day(
    devices: list[dict],
    events_by_device: dict[str, list[dict]],
    day_start: datetime,
    as_of: datetime,
) -> float:
    """
    devices: rows from `devices` (must include id, watts, status).
    events_by_device: device_id -> list of device_events rows
        (prev_status, new_status, ts), for ts in [day_start, as_of].
        Order does not need to be pre-sorted; this function sorts internally.
    day_start: start of the simulated calendar day being measured.
    as_of: the instant to integrate up to (the "now" of the snapshot).

    Returns estimated kWh for the day, walked as a step function per device
    rather than averaged.
    """
    total_wh = 0.0

    for device in devices:
        watts = float(device["watts"])
        events = sorted(
            events_by_device.get(device["id"], []),
            key=lambda e: parse_ts(e["ts"]),
        )

        if events:
            # Status held constant from day_start until the first event
            # inside the window is exactly what that event's prev_status
            # captures.
            current_status = bool(events[0]["prev_status"])
        else:
            # No toggles today at all -> whatever it's on/off right now is
            # what it's been since before today started.
            current_status = bool(device["status"])

        cursor = day_start
        for event in events:
            ts = parse_ts(event["ts"])
            if ts < day_start:
                continue
            duration_hours = (ts - cursor).total_seconds() / 3600.0
            if current_status and duration_hours > 0:
                total_wh += watts * duration_hours
            cursor = ts
            current_status = bool(event["new_status"])

        tail_hours = (as_of - cursor).total_seconds() / 3600.0
        if current_status and tail_hours > 0:
            total_wh += watts * tail_hours

    return total_wh / 1000.0
