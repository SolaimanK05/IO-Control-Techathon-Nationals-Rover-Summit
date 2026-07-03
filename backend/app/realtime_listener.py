"""
Subscribes to the `office-updates` Realtime Broadcast topic and runs the
alert engine against every incoming device_events insert.

This is push-based, per Implementation Plan Section 0 / Section 5: the
backend never polls `devices` or `device_events` on a timer. It reacts only
to events the Postgres trigger broadcasts.
"""

from __future__ import annotations

import asyncio
import logging

from .alerts.rules import evaluate_event

logger = logging.getLogger("realtime_listener")

CHANNEL_NAME = "office-updates"
EVENT_NAME = "device_status_changed"


async def start_listener(supabase):
    """Subscribes and returns the channel handle so the caller can
    unsubscribe cleanly on shutdown."""

    channel = supabase.channel(
        CHANNEL_NAME,
        {"config": {"broadcast": {"self": False}, "private": True}},
    )

    def _on_event(message):
        # realtime-py may hand the callback either the inner payload dict
        # directly, or the full {"event": ..., "payload": {...}} envelope
        # depending on client version — unwrap defensively either way.
        data = message.get("payload", message) if isinstance(message, dict) else message
        asyncio.create_task(_handle(supabase, data))

    channel.on_broadcast(EVENT_NAME, _on_event)
    await channel.subscribe()
    logger.info("Subscribed to realtime topic '%s'", CHANNEL_NAME)
    return channel


async def _handle(supabase, data: dict) -> None:
    try:
        await evaluate_event(supabase, data)
    except Exception:
        logger.exception("Alert evaluation failed for payload: %s", data)
