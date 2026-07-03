"""
Pydantic schemas mirroring docs/api-contract.md exactly.

These exist for response validation / OpenAPI docs. Route handlers build plain
dicts internally (Supabase already returns JSON-shaped rows), but returning
these models from the route functions gets us FastAPI's automatic response
validation + a correct /docs page for free.

Nothing here enumerates a specific room or device by name — shapes only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

DeviceType = Literal["fan", "light"]
AlertType = Literal["after_hours", "room_continuous_2h"]


class DeviceOut(BaseModel):
    device_id: str
    label: str
    svg_id: str
    type: DeviceType
    status: bool
    watts: float
    last_changed: datetime


class ActiveAlertOut(BaseModel):
    id: str
    type: AlertType
    message: str
    raised_at: datetime


class RoomStatusOut(BaseModel):
    room_id: str
    room_name: str
    devices: list[DeviceOut]
    room_power_watts: float


class StatusResponse(BaseModel):
    rooms: list[RoomStatusOut]
    total_power_watts: float
    generated_at: datetime


class RoomResponse(BaseModel):
    room_id: str
    room_name: str
    devices: list[DeviceOut]
    room_power_watts: float
    active_alerts: list[ActiveAlertOut]


class UsageResponse(BaseModel):
    total_power_watts_now: float
    estimated_kwh_today: float
    as_of: datetime
