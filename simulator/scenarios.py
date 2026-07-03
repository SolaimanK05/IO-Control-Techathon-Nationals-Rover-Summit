"""
scenarios.py

Three independent behaviors, each implemented as a small class holding
only the state it needs to detect its own transitions. main.py calls
`.tick()` on each once per simulator loop iteration; they decide for
themselves whether to act this tick.

Design note: each scenario tracks "have I already acted for simulated
day N" via `simulated_day_index()`, so a day-boundary crossing (however
the tick interval lines up with it) triggers exactly once per day, not
once per tick during that whole hour.
"""

from __future__ import annotations

import random

from state_machine import SimulatedClock, DeviceStore

MAX_CONCURRENT_ON_RATIO = 0.4  # per spec: never more than ~40% of devices on during normal daytime toggling


class DaytimeRandomToggle:
    """Low-frequency random toggling across all 15 devices during 9-5,
    bounded so total office power stays plausible. Purpose: the
    dashboard always shows *some* live movement, not just during the
    two scripted scenarios (Section 4.2 of the Implementation Plan)."""

    def __init__(self, toggle_probability_per_tick: float = 0.05):
        self.toggle_probability_per_tick = toggle_probability_per_tick

    def tick(self, clock: SimulatedClock, store: DeviceStore) -> None:
        if not clock.is_daytime():
            return
        if random.random() > self.toggle_probability_per_tick:
            return

        device_id = store.random_device_id()
        device = store.get(device_id)
        max_on = int(len(store.all_ids()) * MAX_CONCURRENT_ON_RATIO)

        if device.status:
            # Always allow turning something off -- never blocked by the cap.
            store.set_status(device_id, False, clock.now())
        else:
            if store.count_on() < max_on:
                store.set_status(device_id, True, clock.now())
            # else: at the cap, skip this tick rather than force an off elsewhere


class ForgottenDeviceScenario:
    """Scenario A (Section 4.3): guarantees an 'after_hours' alert every
    single simulated night. At 5 PM, pick one random device, force
    everything else off, leave the selected device on overnight. At
    9 AM, turn it off ('someone noticed it in the morning'). Repeats
    with a newly chosen device each night."""

    def __init__(self):
        self._last_5pm_day: int | None = None
        self._last_9am_day: int | None = None
        self._forgotten_device_id: str | None = None

    def tick(self, clock: SimulatedClock, store: DeviceStore) -> None:
        now = clock.now()
        day = clock.simulated_day_index()

        if now.hour == 17 and self._last_5pm_day != day:
            self._last_5pm_day = day
            self._forgotten_device_id = store.random_device_id()
            for device_id in store.all_ids():
                store.set_status(
                    device_id, device_id == self._forgotten_device_id, now
                )

        elif now.hour == 9 and self._last_9am_day != day and self._forgotten_device_id:
            self._last_9am_day = day
            store.set_status(self._forgotten_device_id, False, now)
            self._forgotten_device_id = None


class MeetingBurstScenario:
    """Scenario B (Section 4.4): guarantees a 'room_continuous_2h' alert
    on days it's triggered. Once per simulated day, at a random daytime
    hour, one random room's all 5 devices switch on together. Normally
    resolves quickly; on a subset of days (or always, if
    FORCE_DEMO_SCENARIOS=true) it's allowed to run past the 2-hour mark."""

    def __init__(self, force_demo_scenarios: bool, long_burst_probability: float = 0.4):
        self.force_demo_scenarios = force_demo_scenarios
        self.long_burst_probability = long_burst_probability

        self._planned_day: int | None = None
        self._planned_hour: int | None = None
        self._is_long_burst: bool = False
        self._burst_room: str | None = None
        self._burst_start: object | None = None  # datetime, simulated

    def _plan_for_day(self, day: int) -> None:
        self._planned_day = day
        self._planned_hour = random.randint(9, 15)  # leave room for burst to run before 5 PM in the short case
        self._is_long_burst = self.force_demo_scenarios or (
            random.random() < self.long_burst_probability
        )
        self._burst_room = None
        self._burst_start = None

    def tick(self, clock: SimulatedClock, store: DeviceStore) -> None:
        now = clock.now()
        day = clock.simulated_day_index()

        if self._planned_day != day:
            self._plan_for_day(day)

        # Trigger the burst
        if (
            self._burst_room is None
            and now.hour == self._planned_hour
            and clock.is_daytime()
        ):
            self._burst_room = store.random_room_name()
            self._burst_start = now
            for device_id in store.ids_in_room(self._burst_room):
                store.set_status(device_id, True, now)
            return

        # Resolve the burst
        if self._burst_room is not None:
            elapsed_hours = (now - self._burst_start).total_seconds() / 3600
            resolve_after = 2.5 if self._is_long_burst else 0.5  # short bursts resolve well under the 2h threshold

            if elapsed_hours >= resolve_after:
                for device_id in store.ids_in_room(self._burst_room):
                    store.set_status(device_id, False, now)
                self._burst_room = None
                self._burst_start = None