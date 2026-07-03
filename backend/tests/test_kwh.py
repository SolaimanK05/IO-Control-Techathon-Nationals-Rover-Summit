"""
Offline unit test for the time-weighted kWh integral. Doesn't touch Supabase —
just verifies the walk-the-event-log math against a hand-computed scenario.

Run with: python -m pytest backend/tests/test_kwh.py -v
(from the repo root, with backend/ on PYTHONPATH, e.g. `cd backend && pytest`)
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kwh import compute_kwh_for_day  # noqa: E402

DAY_START = datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc)


def test_device_on_whole_day_no_events():
    devices = [{"id": "d1", "watts": 60, "status": True}]
    as_of = DAY_START + timedelta(hours=10)
    kwh = compute_kwh_for_day(devices, {}, DAY_START, as_of)
    assert round(kwh, 3) == round(60 * 10 / 1000, 3)


def test_device_off_whole_day_no_events():
    devices = [{"id": "d1", "watts": 60, "status": False}]
    as_of = DAY_START + timedelta(hours=10)
    kwh = compute_kwh_for_day(devices, {}, DAY_START, as_of)
    assert kwh == 0.0


def test_single_toggle_mid_day():
    # Fan (60W) is OFF from day_start, turns ON at hour 4, stays on until as_of (hour 6).
    devices = [{"id": "d1", "watts": 60, "status": True}]
    events = {
        "d1": [
            {"prev_status": False, "new_status": True, "ts": (DAY_START + timedelta(hours=4)).isoformat()},
        ]
    }
    as_of = DAY_START + timedelta(hours=6)
    kwh = compute_kwh_for_day(devices, events, DAY_START, as_of)
    # 2 hours on at 60W = 120 Wh = 0.12 kWh
    assert round(kwh, 4) == 0.12


def test_multiple_toggles_two_devices():
    devices = [
        {"id": "fan", "watts": 60, "status": False},
        {"id": "light", "watts": 15, "status": True},
    ]
    events = {
        "fan": [
            {"prev_status": False, "new_status": True, "ts": (DAY_START + timedelta(hours=1)).isoformat()},
            {"prev_status": True, "new_status": False, "ts": (DAY_START + timedelta(hours=3)).isoformat()},
        ],
        "light": [
            {"prev_status": False, "new_status": True, "ts": (DAY_START + timedelta(hours=0.5)).isoformat()},
        ],
    }
    as_of = DAY_START + timedelta(hours=5)

    kwh = compute_kwh_for_day(devices, events, DAY_START, as_of)
    # fan: on for hours [1,3) = 2h * 60W = 120 Wh
    # light: off [0,0.5), on [0.5,5) = 4.5h * 15W = 67.5 Wh
    expected_wh = 120 + 67.5
    assert round(kwh, 4) == round(expected_wh / 1000, 4)


if __name__ == "__main__":
    test_device_on_whole_day_no_events()
    test_device_off_whole_day_no_events()
    test_single_toggle_mid_day()
    test_multiple_toggles_two_devices()
    print("All kwh tests passed.")
