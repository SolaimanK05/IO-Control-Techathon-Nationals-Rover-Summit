"""GET /room/{room_id} — one room + its active alerts. See api-contract.md §3."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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


@router.get("/room/{room_id}")
async def get_room(room_id: str, request: Request):
    supabase = request.app.state.supabase

    resp = await supabase.table("rooms").select("*, devices(*)").eq("id", room_id).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Room not found")
    room = rows[0]

    devices = room.get("devices") or []
    room_power_watts = sum(d["watts"] for d in devices if d["status"])

    alerts_resp = await (
        supabase.table("alerts")
        .select("id, type, message, raised_at")
        .eq("room_id", room_id)
        .is_("cleared_at", "null")
        .execute()
    )
    active_alerts = alerts_resp.data or []

    return {
        "room_id": room["id"],
        "room_name": room["name"],
        "devices": [_device_out(d) for d in devices],
        "room_power_watts": room_power_watts,
        "active_alerts": active_alerts,
    }
