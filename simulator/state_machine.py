"""
state_machine.py

Two responsibilities, deliberately separated:

- SimulatedClock: pure time logic. Converts real elapsed wall-clock
  time into simulated time, at a configurable rate. Everything that
  reasons about "9 AM" / "5 PM" / "which simulated day is it" goes
  through this class -- no other module should touch datetime.now()
  directly for simulated-time purposes.

- DeviceStore: the in-memory mirror of the `devices` table, plus the
  one function that writes a status change back to Supabase. This is
  the ONLY place that calls `.update()` on the devices table -- every
  other module goes through `DeviceStore.set_status()`, so there's a
  single choke point to audit if something's wrong with writes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class SimulatedClock:
    def __init__(self, hours_per_real_second: float, start_time: datetime | None = None):
        self.hours_per_real_second = hours_per_real_second
        self._start_real = datetime.now(timezone.utc)
        # Simulated day 0 starts at midnight, "today", in UTC -- arbitrary
        # but consistent choice; see Implementation notes for rationale.
        self._start_sim = start_time or datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def now(self) -> datetime:
        real_elapsed = (datetime.now(timezone.utc) - self._start_real).total_seconds()
        sim_elapsed_hours = real_elapsed * self.hours_per_real_second
        return self._start_sim + timedelta(hours=sim_elapsed_hours)

    def is_daytime(self) -> bool:
        """Office hours: 9 AM - 5 PM simulated, per problem spec."""
        return 9 <= self.now().hour < 17

    def simulated_day_index(self) -> int:
        """0 on the first simulated day, 1 on the second, etc. Used to
        detect day-boundary transitions (new day => reset per-day flags)."""
        return (self.now() - self._start_sim).days


@dataclass
class Device:
    id: str
    room_id: str
    room_name: str
    type: str  # 'fan' | 'light'
    label: str
    watts: float
    status: bool
    last_changed: datetime


class DeviceStore:
    def __init__(self, supabase_client):
        self._sb = supabase_client
        self._devices: dict[str, Device] = {}

    def load(self) -> None:
        """One-time load at startup. Joins devices -> rooms so we don't
        need a second round-trip later to know a device's room name."""
        resp = (
            self._sb.table("devices")
            .select("id, room_id, type, label, watts, status, last_changed, rooms(name)")
            .execute()
        )
        self._devices = {}
        for row in resp.data:
            self._devices[row["id"]] = Device(
                id=row["id"],
                room_id=row["room_id"],
                room_name=row["rooms"]["name"],
                type=row["type"],
                label=row["label"],
                watts=row["watts"],
                status=row["status"],
                last_changed=datetime.fromisoformat(row["last_changed"]),
            )
        if len(self._devices) != 15:
            raise RuntimeError(
                f"Expected 15 devices after seeding, found {len(self._devices)}. "
                "Check that supabase/seed.sql ran successfully."
            )

    def all_ids(self) -> list[str]:
        return list(self._devices.keys())

    def ids_in_room(self, room_name: str) -> list[str]:
        return [d.id for d in self._devices.values() if d.room_name == room_name]

    def room_names(self) -> list[str]:
        return sorted({d.room_name for d in self._devices.values()})

    def get(self, device_id: str) -> Device:
        return self._devices[device_id]

    def count_on(self) -> int:
        return sum(1 for d in self._devices.values() if d.status)

    def random_device_id(self) -> str:
        return random.choice(self.all_ids())

    def random_room_name(self) -> str:
        return random.choice(self.room_names())

    def set_status(self, device_id: str, new_status: bool, sim_ts: datetime) -> None:
        """The single write path. Updates devices.status + last_changed;
        the Postgres trigger from migration 0002 handles inserting the
        device_events row and firing the realtime broadcast -- this
        function does not (and must not) touch device_events directly."""
        device = self._devices[device_id]
        if device.status == new_status:
            return  # no-op, avoid a spurious trigger fire / broadcast

        self._sb.table("devices").update(
            {"status": new_status, "last_changed": sim_ts.isoformat()}
        ).eq("id", device_id).execute()

        device.status = new_status
        device.last_changed = sim_ts