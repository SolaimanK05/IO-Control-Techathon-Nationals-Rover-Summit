"""
!status, !room <name>, !usage — Implementation Plan Section 7.

These call the FastAPI backend only (never Supabase directly, per
api-contract.md §5's phase table). `!room <name>` resolves a human-typed
room name to a room_id by scanning /status's room list — no hardcoded room
names, so this keeps working if rooms are added or renamed.
"""

from __future__ import annotations

import logging
import os

import httpx
from discord.ext import commands

logger = logging.getLogger("commands")

BACKEND_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")
UNREACHABLE_MESSAGE = "Couldn't reach the office backend right now — try again shortly."


def register_commands(bot: commands.Bot, openrouter) -> httpx.AsyncClient:
    http_client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=10)

    @bot.command(name="status")
    async def status_cmd(ctx: commands.Context):
        data = await _get(ctx, http_client, "/status")
        if data is None:
            return
        text = await openrouter.humanize("status", data, _fallback_status(data))
        await ctx.send(text)

    @bot.command(name="room")
    async def room_cmd(ctx: commands.Context, *, name: str):
        status_data = await _get(ctx, http_client, "/status")
        if status_data is None:
            return

        rooms = status_data.get("rooms", [])
        match = next((r for r in rooms if r["room_name"].lower() == name.lower()), None)
        if match is None:
            available = ", ".join(r["room_name"] for r in rooms) or "no rooms found"
            await ctx.send(f"I don't see a room called '{name}'. Available rooms: {available}")
            return

        data = await _get(ctx, http_client, f"/room/{match['room_id']}")
        if data is None:
            return
        text = await openrouter.humanize("room", data, _fallback_room(data))
        await ctx.send(text)

    @bot.command(name="usage")
    async def usage_cmd(ctx: commands.Context):
        data = await _get(ctx, http_client, "/usage")
        if data is None:
            return
        text = await openrouter.humanize("usage", data, _fallback_usage(data))
        await ctx.send(text)

    return http_client


async def _get(ctx: commands.Context, client: httpx.AsyncClient, path: str) -> dict | None:
    try:
        resp = await client.get(path)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        logger.warning("Backend request to %s failed", path)
        await ctx.send(UNREACHABLE_MESSAGE)
        return None


def _fallback_status(data: dict) -> str:
    lines = [f"**Office status** (simulated time {data.get('generated_at', 'unknown')})"]
    for room in data.get("rooms", []):
        on_devices = [d["label"] for d in room["devices"] if d["status"]]
        state = ", ".join(on_devices) if on_devices else "everything off"
        lines.append(f"- {room['room_name']}: {room['room_power_watts']}W — {state}")
    lines.append(f"Total power: {data.get('total_power_watts', 0)}W")
    return "\n".join(lines)


def _fallback_room(data: dict) -> str:
    lines = [f"**{data['room_name']}** — {data['room_power_watts']}W"]
    for d in data.get("devices", []):
        lines.append(f"- {d['label']}: {'ON' if d['status'] else 'off'}")
    alerts = data.get("active_alerts", [])
    if alerts:
        lines.append("Active alerts:")
        for a in alerts:
            lines.append(f"  \u26a0\ufe0f {a['message']}")
    return "\n".join(lines)


def _fallback_usage(data: dict) -> str:
    return (
        f"Current draw: {data.get('total_power_watts_now', 0)}W. "
        f"Estimated usage today: {data.get('estimated_kwh_today', 0)} kWh "
        f"(as of simulated time {data.get('as_of', 'unknown')})."
    )
