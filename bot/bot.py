"""
Discord bot entrypoint — Implementation Plan Section 7 / Phase 5.

- Commands (!status, !room, !usage) call FastAPI REST only.
- Subscribes directly to Supabase Realtime topic `office-alerts` for
  proactive posts — same push-based subscription pattern as the dashboard,
  no separate polling loop.
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands
from supabase import AsyncClient, acreate_client

from commands import register_commands
from openrouter_client import OpenRouterClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

ALERT_CHANNEL_ID = int(os.environ.get("DISCORD_ALERTS_CHANNEL_ID", "0"))
COMMAND_PREFIX = os.environ.get("DISCORD_COMMAND_PREFIX", "!")

intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
openrouter = OpenRouterClient()
http_client = register_commands(bot, openrouter)

_alerts_channel = None  # keeps the realtime channel handle alive


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)
    asyncio.create_task(_subscribe_alerts())

@bot.event
async def on_message(message):
    print(f"MESSAGE: {message.author} -> {message.content}")

    if message.author.bot:
        return

    await bot.process_commands(message)
async def _subscribe_alerts() -> None:
    global _alerts_channel

    supabase_url = os.environ["SUPABASE_URL"]
    # Publishable key (new naming, replaces legacy anon key) is enough here:
    # this connection only reads broadcast messages, it never writes to Postgres.
    supabase_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    supabase: AsyncClient = await acreate_client(supabase_url, supabase_key)

    channel = supabase.channel(
        "office-alerts",
        {"config": {"broadcast": {"self": False}, "private": True}},
    )

    def _make_handler(event_name: str):
        def _handler(message):
            data = message.get("payload", message) if isinstance(message, dict) else message
            asyncio.create_task(_post_alert(event_name, data))
        return _handler

    channel.on_broadcast("alert_raised", _make_handler("alert_raised"))
    channel.on_broadcast("alert_cleared", _make_handler("alert_cleared"))
    await channel.subscribe()

    _alerts_channel = channel
    logger.info("Subscribed to realtime topic 'office-alerts'")


async def _post_alert(event_name: str, data: dict) -> None:
    if ALERT_CHANNEL_ID == 0:
        logger.warning("DISCORD_ALERT_CHANNEL_ID not set; dropping alert post: %s", data)
        return

    discord_channel = bot.get_channel(ALERT_CHANNEL_ID)
    if discord_channel is None:
        logger.warning("Configured alert channel %s not found/visible", ALERT_CHANNEL_ID)
        return

    message = data.get("message", "an office alert")
    if event_name == "alert_cleared":
        text = f"\u2705 Cleared: {message}"
    else:
        text = f"\u26a0\ufe0f {message}"
    await discord_channel.send(text)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Usage: `{COMMAND_PREFIX}{ctx.command} <argument>`")
        return
    logger.exception("Command error", exc_info=error)
    await ctx.send("Something went wrong handling that command.")


async def _shutdown() -> None:
    await openrouter.close()
    await http_client.aclose()


def main() -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
    try:
        bot.run(token)
    finally:
        asyncio.run(_shutdown())


if __name__ == "__main__":
    main()
