"""
OpenRouter client wrapper — Implementation Plan Section 7.

Reliability layer required given the free tier's ~20 RPM cap:
  - Token-bucket limiter capped below 20 RPM (default 15/min).
  - Exponential backoff + jitter on 429, capped retry count.
  - Short-TTL cache (~12s) for identical command+data combos.
  - Templated fallback if OpenRouter is unreachable/quota-exhausted —
    the bot must never go silent because of this dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections import OrderedDict

import httpx

logger = logging.getLogger("openrouter_client")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-4-scout:free")
MAX_RETRIES = 3
CACHE_TTL_SECONDS = 12
RATE_LIMIT_PER_MINUTE = int(os.environ.get("OPENROUTER_RATE_LIMIT_PER_MIN", "15"))


class TokenBucket:
    """Simple async token bucket; caps outbound requests below the free-tier RPM."""

    def __init__(self, rate_per_minute: int):
        self.capacity = rate_per_minute
        self.tokens = float(rate_per_minute)
        self.rate_per_second = rate_per_minute / 60.0
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.updated_at
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
                self.updated_at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.rate_per_second
                await asyncio.sleep(wait)


class TTLCache:
    """Tiny in-memory TTL cache — office state doesn't change every second,
    so repeated identical commands within the window skip OpenRouter entirely."""

    def __init__(self, ttl_seconds: int, max_size: int = 256):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._store: "OrderedDict[str, tuple[float, str]]" = OrderedDict()

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)


class OpenRouterClient:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.model = DEFAULT_MODEL
        self.bucket = TokenBucket(RATE_LIMIT_PER_MINUTE)
        self.cache = TTLCache(CACHE_TTL_SECONDS)
        self._client = httpx.AsyncClient(timeout=15)

    async def close(self) -> None:
        await self._client.aclose()

    async def humanize(self, command: str, data: dict, fallback_text: str) -> str:
        """Returns a friendly phrasing of `data` for `command`, or
        `fallback_text` if OpenRouter is unavailable/exhausted/misconfigured.
        Never raises — this must be safe to call from any command handler."""
        cache_key = f"{command}:{json.dumps(data, sort_keys=True, default=str)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        if not self.api_key:
            return fallback_text

        prompt = self._build_prompt(command, data)

        for attempt in range(MAX_RETRIES):
            await self.bucket.acquire()
            try:
                response = await self._client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": os.environ.get("BOT_SITE_URL", "https://example.com"),
                        "X-Title": "Office Monitor Discord Bot",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a concise office-monitoring assistant. "
                                    "Rephrase the given office data into one short, "
                                    "friendly Discord message. Do not invent numbers "
                                    "that aren't in the data."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 200,
                    },
                )
            except httpx.HTTPError:
                logger.warning("OpenRouter request failed (attempt %s)", attempt + 1)
                await self._backoff(attempt)
                continue

            if response.status_code == 429:
                logger.warning("OpenRouter rate-limited us (attempt %s)", attempt + 1)
                await self._backoff(attempt)
                continue

            if response.status_code != 200:
                logger.warning(
                    "OpenRouter returned %s: %s", response.status_code, response.text[:200]
                )
                break

            try:
                body = response.json()
                text = body["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, ValueError):
                logger.warning("Unexpected OpenRouter response shape: %s", response.text[:200])
                break

            if text:
                self.cache.set(cache_key, text)
                return text
            break

        return fallback_text

    async def _backoff(self, attempt: int) -> None:
        delay = min(2 ** attempt, 8) + random.uniform(0, 0.5)
        await asyncio.sleep(delay)

    def _build_prompt(self, command: str, data: dict) -> str:
        return f"Command: {command}\nData: {json.dumps(data, default=str)}"
