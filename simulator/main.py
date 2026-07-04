"""
main.py -- Simulator entrypoint.

Run loop is deliberately dumb: load env + devices once, then loop
forever calling .tick() on each behavior at a fixed real-time interval.
All the actual decision-making lives in scenarios.py / state_machine.py --
this file just wires things together and handles startup/shutdown.
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from supabase import create_client

from state_machine import SimulatedClock, DeviceStore
from scenarios import DaytimeRandomToggle, ForgottenDeviceScenario, MeetingBurstScenario


def main() -> None:
    load_dotenv()

    supabase_url = _require_env("SUPABASE_URL")
    supabase_secret_key = _require_env("SUPABASE_SECRET_KEY")
    hours_per_real_second = float(os.environ.get("SIM_HOURS_PER_REAL_SECOND", "0.05"))
    tick_interval_seconds = float(os.environ.get("TICK_INTERVAL_SECONDS", "2"))
    force_demo_scenarios = os.environ.get("FORCE_DEMO_SCENARIOS", "false").lower() == "true"

    print(f"[simulator] connecting to {supabase_url}")
    supabase = create_client(supabase_url, supabase_secret_key)

    store = DeviceStore(supabase)
    store.load()
    print(f"[simulator] loaded {len(store.all_ids())} devices across {store.room_names()}")

    clock = SimulatedClock(hours_per_real_second=hours_per_real_second)

    daytime_toggle = DaytimeRandomToggle()
    forgotten_device = ForgottenDeviceScenario()
    meeting_burst = MeetingBurstScenario(force_demo_scenarios=force_demo_scenarios)

    print(
        f"[simulator] running. sim clock rate: {hours_per_real_second}h/real-second, "
        f"tick every {tick_interval_seconds}s, FORCE_DEMO_SCENARIOS={force_demo_scenarios}"
    )

    while True:
        now = clock.now()

        # Order matters: forgotten_device's 5PM blanket-off should win
        # over an in-progress meeting burst (see scenarios.py docstring
        # for why this is correct per the spec, not a bug).
        daytime_toggle.tick(clock, store, exclude_room=meeting_burst.active_room)
        forgotten_device.tick(clock, store)
        meeting_burst.tick(clock, store)

        print(
            f"[simulator] sim time = {now.isoformat()} | "
            f"devices on = {store.count_on()}/{len(store.all_ids())}"
        )

        time.sleep(tick_interval_seconds)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}. Check simulator/.env")
    return value


if __name__ == "__main__":
    main()