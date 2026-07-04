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
    """Low-frequency random toggling across all devices during 9-5,
    bounded so total office power stays plausible. Purpose: the
    dashboard always shows *some* live movement, not just during the
    two scripted scenarios (Section 4.2 of the Implementation Plan).

    exclude_room: if provided, devices in that room are skipped so
    they don't disrupt an active meeting burst that needs all-on
    continuity to trigger the room_continuous_2h alert.
    """

    def __init__(self, toggle_probability_per_tick: float = 0.05):
        self.toggle_probability_per_tick = toggle_probability_per_tick

    def tick(self, clock: SimulatedClock, store: DeviceStore, exclude_room: str | None = None) -> None:
        if not clock.is_daytime():
            return
        if random.random() > self.toggle_probability_per_tick:
            return

        # Skip devices in the burst room so we don't break its continuity streak.
        available_ids = [
            d_id for d_id in store.all_ids()
            if exclude_room is None or store.get(d_id).room_name != exclude_room
        ]
        if not available_ids:
            return

        device_id = random.choice(available_ids)
        device = store.get(device_id)
        max_on = int(len(store.all_ids()) * MAX_CONCURRENT_ON_RATIO)

        if device.status:
            # Always allow turning something off — never blocked by the cap.
            store.set_status(device_id, False, clock.now())
        else:
            if store.count_on() < max_on:
                store.set_status(device_id, True, clock.now())
            # else: at the cap, skip this tick rather than force an off elsewhere


class ForgottenDeviceScenario:
    """Scenario A (Section 4.3): guarantees 'after_hours' alerts every
    single simulated night. At 5 PM, pick 2–4 random devices, force
    everything else off, leave the selected devices on overnight. At
    9 AM, turn them all off ('someone noticed them in the morning').
    Repeats with a newly chosen set each night.

    Using 2–4 devices (not just 1) ensures multiple after_hours alerts
    fire simultaneously, giving a more realistic after-hours scenario.
    """

    def __init__(self):
        self._last_5pm_day: int | None = None
        self._last_9am_day: int | None = None
        self._forgotten_device_ids: list[str] = []

    def tick(self, clock: SimulatedClock, store: DeviceStore) -> None:
        now = clock.now()
        day = clock.simulated_day_index()

        if now.hour == 17 and self._last_5pm_day != day:
            self._last_5pm_day = day
            # Leave 2–4 devices on after hours (more realistic than just 1)
            n = random.randint(2, 4)
            all_ids = store.all_ids()
            self._forgotten_device_ids = random.sample(all_ids, min(n, len(all_ids)))
            forgotten_set = set(self._forgotten_device_ids)
            for device_id in all_ids:
                store.set_status(device_id, device_id in forgotten_set, now)
            print(
                f"[forgotten-device] {len(self._forgotten_device_ids)} devices left on after hours"
            )

        elif now.hour == 9 and self._last_9am_day != day and self._forgotten_device_ids:
            self._last_9am_day = day
            for device_id in self._forgotten_device_ids:
                store.set_status(device_id, False, now)
            print(
                f"[forgotten-device] {len(self._forgotten_device_ids)} devices turned off (morning)"
            )
            self._forgotten_device_ids = []


class MeetingBurstScenario:
    """Scenario B (Section 4.4): guarantees a 'room_continuous_2h' alert
    on days it's triggered. Once per simulated day, at a random daytime
    hour, one random room's all 5 devices switch on together. Normally
    resolves quickly; on a subset of days (or always, if
    FORCE_DEMO_SCENARIOS=true) it's allowed to run past the 2-hour mark.

    active_room property is exposed so DaytimeRandomToggle can exclude
    that room from random toggling, keeping the all-on streak intact.
    """

    def __init__(self, force_demo_scenarios: bool, long_burst_probability: float = 1.0):
        self.force_demo_scenarios = force_demo_scenarios
        self.long_burst_probability = long_burst_probability

        self._planned_day: int | None = None
        self._planned_hour: int | None = None
        self._is_long_burst: bool = False
        self._burst_room: str | None = None
        self._burst_start: object | None = None  # datetime, simulated
        # Tracks "have I already triggered today", independent of
        # _burst_room. Without this, a SHORT burst (resolve_after=0.5h)
        # can resolve and still be within the same _planned_hour window,
        # and the trigger condition below would fire all over again --
        # producing repeated on/off/on cycles instead of one burst per day.
        self._triggered_today: bool = False

    @property
    def active_room(self) -> str | None:
        """Returns the room name currently in a burst, or None."""
        return self._burst_room

    def _plan_for_day(self, day: int) -> None:
        self._planned_day = day
        self._planned_hour = random.randint(9, 14)  # leave room for burst to run before 5 PM
        self._is_long_burst = self.force_demo_scenarios or (
            random.random() < self.long_burst_probability
        )
        self._burst_room = None
        self._burst_start = None
        self._triggered_today = False

    def tick(self, clock: SimulatedClock, store: DeviceStore) -> None:
        now = clock.now()
        day = clock.simulated_day_index()

        if self._planned_day != day:
            self._plan_for_day(day)

        # Trigger the burst -- gated on _triggered_today, not just
        # _burst_room is None, so a resolved short burst can't immediately
        # re-trigger while the clock is still inside the same planned hour.
        if (
            not self._triggered_today
            and self._burst_room is None
            and now.hour == self._planned_hour
            and clock.is_daytime()
        ):
            self._triggered_today = True
            self._burst_room = store.random_room_name()
            self._burst_start = now
            burst_type = "LONG (>=2h)" if self._is_long_burst else "short (<2h)"
            print(f"[meeting-burst] {burst_type} burst started in '{self._burst_room}'")
            for device_id in store.ids_in_room(self._burst_room):
                store.set_status(device_id, True, now)
            return

        # Resolve the burst
        if self._burst_room is not None:
            elapsed_hours = (now - self._burst_start).total_seconds() / 3600
            # Long bursts run for 2.5 sim hours (well past the 2h threshold).
            # Short bursts resolve at 0.5 sim hours (well under threshold).
            resolve_after = 2.5 if self._is_long_burst else 0.5

            if elapsed_hours >= resolve_after:
                print(
                    f"[meeting-burst] burst in '{self._burst_room}' resolved "
                    f"after {elapsed_hours:.2f} sim hours"
                )
                for device_id in store.ids_in_room(self._burst_room):
                    store.set_status(device_id, False, now)
                self._burst_room = None
                self._burst_start = None