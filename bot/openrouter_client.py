from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from collections import OrderedDict
from typing import Any

import httpx

# --- Configuration & Constants ---
logger = logging.getLogger("openrouter_client")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 3
CACHE_TTL_SECONDS = 12

# Redesigned to use positive constraints. Models respond better to "DO THIS" than "NEVER DO THIS".

# SYSTEM_PROMPT = """You are a playful, cheeky, and highly conversational Discord bot responsible for giving users a fun status update on their home or office devices. 

# ### Your Persona
# You are warm, expressive, and slightly sassy! You aren't afraid to playfully tease the user about their habits. You should sound like a witty friend who is keeping an eye on the place for them. 

# ### Your Task
# Take the provided raw status data or JSON and translate it into a completely humanized, flowing narrative that includes the current time, highlights active devices, and closes with a playful joke about their power usage.

# ### Critical Execution Rules (Bulletproof)

# *   **Strict Output-Only:** Output *only* the final message intended for the Discord users. Do not include any intro (e.g., "Here is your update:"), markdown code fences (` ``` `), wrapping quotes, or conversational filler. Absolutely no internal thoughts or reasoning are allowed.
# *   **Report "ON" States Only:** Completely ignore and omit any rooms, devices, or systems that are "off", "0W", or inactive. Focus exclusively on what is currently running.
# *   **Mandatory Conversational Prose:** Write exclusively in full, beautifully flowing human sentences. **Never** format the data as key-value pairs, bullet points, or short, robotic dashboard fragments. 
# *   **Time Framing:** Start the message by stating the current time naturally (e.g., "Right now at 3:40 PM...").
# *   **Playful Power Teasing:** Look at the total power usage and add a playful, teasing comment at the end. Jokingly scold them for using too much electricity or make a funny comment about what they are doing with all that power (e.g., "Are you trying to launch a spaceship?", "Do you just love using way too much electricity?").
# *   **Expressive Emoji Usage:** Scatter expressive emojis naturally throughout the response to match the active devices and your playful, shocked reaction to the power bill (e.g., 💡, 🌀, ⚡, 🫣).
# *   **Data Integrity:** Use the exact names and numbers provided for the active items and total power (e.g., "Light 3 in Work Room 1", "75.0W"). Do not invent or change the core metrics."""

SYSTEM_PROMPT = """    You are a playful, cheeky, and highly conversational Discord bot responsible for giving users a fun status update on their home or office devices.
    ### Your Task
    Take the provided raw status data or JSON and translate into a flowing narrative highlighting active devices and power usage.
    ### Critical Execution Rules (Bulletproof)
    *   **Strict Output-Only:** Output *only* the final message intended for the Discord users. Do not include any intro (e.g., "Here is your update:"), markdown
    code fences (` ``` `), wrapping quotes, or conversational filler. Absolutely no internal thoughts or reasoning are allowed.
    *   **Report "ON" States Only:** Completely ignore and omit any rooms, devices, or systems that are "off", "0W", or inactive. Focus exclusively on what is currently running.
    *   **Mandatory Conversational Prose:** Write exclusively in full, beautifully flowing human sentences. **Never** format the data as key-value pairs, bullet points, or short, robotic dashboard fragments.
    *   **Time Framing:** Use the correct current time in a human readable format
    *   **Data Integrity:** Use the exact names and numbers provided for the active items and total power (e.g., "Light 3 in Work Room 1", "75.0W"). Do not invent or change the core metrics.
"""

class TokenBucket:
    """Limits requests to ensure we don't exceed free-tier RPM."""
    def __init__(self, rate_per_minute: int):
        self.capacity = float(rate_per_minute)
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
                await asyncio.sleep((1 - self.tokens) / self.rate_per_second)

class TTLCache:
    """Caches responses to prevent redundant API calls."""
    def __init__(self, ttl_seconds: int, max_size: int = 256):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._store: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None: return None
        ts, value = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)

class OpenRouterClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
        self.bucket = TokenBucket(int(os.environ.get("OPENROUTER_RATE_LIMIT_PER_MIN", "15")))
        self.cache = TTLCache(CACHE_TTL_SECONDS)
        self._client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def humanize(self, command: str, data: dict, fallback_text: str) -> str:
        if not self.api_key:
            return fallback_text
        
        try:
            cache_key = f"{command}:{json.dumps(data, sort_keys=True, default=str)}"
        except (TypeError, ValueError):
            return fallback_text
            
        if (cached := self.cache.get(cache_key)) is not None:
            return cached

        prompt = f"Command: {command}\nData: {json.dumps(data, default=str)}\n\nGenerate the final Discord message now:"
        
        for attempt in range(MAX_RETRIES):
            await self.bucket.acquire()
            try:
                response = await self._post_request(prompt)
                
                if response.status_code == 429:
                    await self._backoff(attempt)
                    continue
                
                response.raise_for_status()
                
                if (result := self._extract_content(response)):
                    self.cache.set(cache_key, result)
                    return result
                break
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"OpenRouter HTTP error {e.response.status_code}")
                break 
            except (httpx.TimeoutException, httpx.ConnectError):
                await self._backoff(attempt)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

        return fallback_text

    async def _post_request(self, prompt: str) -> httpx.Response:
        return await self._client.post(
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
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 150,
                "temperature": 0.2,  # Added to heavily reduce AI rambling
                "top_p": 0.9
            },
        )

    def _extract_content(self, response: httpx.Response) -> str | None:
        try:
            raw_content = response.json()["choices"][0]["message"]["content"].strip()
            # Scrub any `<think> ... </think>` blocks natively generated by models like DeepSeek
            cleaned_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
            
            # Additional fallback safety: if the model still talks to itself and quotes a response, 
            # try to extract just the quoted part.
            if '"' in cleaned_content and len(cleaned_content.split('"')) >= 3:
                # Extracts text between the first set of quotes it finds
                match = re.search(r'"([^"]*)"', cleaned_content)
                if match:
                    return match.group(1).strip()
                    
            return cleaned_content
        except (KeyError, IndexError, ValueError):
            return None

    async def _backoff(self, attempt: int) -> None:
        delay = min(2 ** attempt, 8) + random.uniform(0, 0.5)
        await asyncio.sleep(delay)

    def _build_prompt(self, command: str, data: dict) -> str:
        return f"Command: {command}\nData: {json.dumps(data, default=str)}"
