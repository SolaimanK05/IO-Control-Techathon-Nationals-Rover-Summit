-- ============================================================
-- Migration 0001: Core schema
-- rooms, devices, device_events, alerts
-- ============================================================

create extension if not exists "pgcrypto"; -- for gen_random_uuid()

-- ---------------------------------------------------------------
-- rooms
-- ---------------------------------------------------------------
create table public.rooms (
  id   uuid primary key default gen_random_uuid(),
  name text not null unique
);

-- ---------------------------------------------------------------
-- devices
-- ---------------------------------------------------------------
create table public.devices (
  id           uuid primary key default gen_random_uuid(),
  room_id      uuid not null references public.rooms(id) on delete cascade,
  type         text not null check (type in ('fan', 'light')),
  label        text not null,        -- human-readable, e.g. "Fan 1" — scoped to room, not globally unique
  svg_id       text not null unique, -- exact id in the office layout SVG, e.g. "d-fan-top"
  status       boolean not null default false,
  watts        numeric not null check (watts > 0),
  last_changed timestamptz not null default now(),

  -- one label per room (e.g. only one "Fan 1" per room), enforced at the DB level
  unique (room_id, label)
);

create index idx_devices_room_id on public.devices(room_id);

-- ---------------------------------------------------------------
-- device_events (append-only)
-- Populated ONLY by the trigger in migration 0002 — application
-- code never inserts here directly. This guarantees the event log
-- can never drift from `devices.status`.
-- ---------------------------------------------------------------
create table public.device_events (
  id          uuid primary key default gen_random_uuid(),
  device_id   uuid not null references public.devices(id) on delete cascade,
  prev_status boolean not null,
  new_status  boolean not null,
  ts          timestamptz not null -- SIMULATED time, supplied by the app via devices.last_changed
);

create index idx_device_events_device_id_ts on public.device_events(device_id, ts);

-- ---------------------------------------------------------------
-- alerts (backend-owned; lifecycle is explicit via cleared_at)
-- ---------------------------------------------------------------
create table public.alerts (
  id         uuid primary key default gen_random_uuid(),
  type       text not null check (type in ('after_hours', 'room_continuous_2h')),
  room_id    uuid not null references public.rooms(id) on delete cascade,
  device_id  uuid references public.devices(id) on delete cascade, -- null for room-level alerts
  message    text not null,
  raised_at  timestamptz not null,
  cleared_at timestamptz
);

create index idx_alerts_room_id on public.alerts(room_id);
create index idx_alerts_active on public.alerts(room_id) where cleared_at is null;