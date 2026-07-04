"""GET /status — full office snapshot, grouped by room. See api-contract.md §3."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


def _device_out(d: dict) -> dict:
    return {
        "device_id": d["id"],
        "label": d["label"],
        "svg_id": d["svg_id"],
        "type": d["type"],
        "status": d["status"],
        "watts": d["watts"],
        "last_changed": d["last_changed"],
    }


@router.get("/status")
async def get_status(request: Request):
    supabase = request.app.state.supabase

    # Embedded select: one round trip for every room + its devices, whatever
    # the current room/device count happens to be.
    resp = await supabase.table("rooms").select("*, devices(*)").execute()
    rooms_data = resp.data or []

    rooms = []
    total_power_watts = 0.0
    for room in rooms_data:
        devices = room.get("devices") or []
        room_power_watts = sum(d["watts"] for d in devices if d["status"])
        total_power_watts += room_power_watts
        rooms.append({
            "room_id": room["id"],
            "room_name": room["name"],
            "devices": [_device_out(d) for d in devices],
            "room_power_watts": room_power_watts,
        })

    return {
        "rooms": rooms,
        "total_power_watts": total_power_watts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
