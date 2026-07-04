# IO Office Monitor

A real-time office device monitoring system built for the Techathon Nationals Rover Summit. The system simulates an office environment with 15 devices across 3 rooms, detects energy anomalies using an event-driven alert engine, and surfaces them on a live dashboard and a Discord bot — with zero polling anywhere in the critical path.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Environment Variables](#environment-variables)
6. [Database Setup](#database-setup)
7. [Running the Services](#running-the-services)
8. [How the Alert Engine Works](#how-the-alert-engine-works)
9. [Simulator Scenarios](#simulator-scenarios)
10. [API Reference](#api-reference)
11. [Troubleshooting](#troubleshooting)

---

## Architecture

The system is entirely event-driven. No component polls for state on a timer.

![System architecture](docs/system-diagram.svg)

Nothing in this pipeline uses setInterval or a polling loop. The backend's alert engine reacts to incoming Realtime events. The one exception is a lightweight 3-second background check for the room_continuous_2h rule, which is time-based (not state-change-based) and cannot be caught by events alone.

---

## Project Structure

```
IO/
|-- .env                        # Single source of truth for all env vars
|-- .env.example                # Template — copy this to .env and fill in
|-- requirements.txt            # Consolidated Python deps for all services
|-- venv/                       # Shared Python virtual environment
|
|-- backend/                    # FastAPI alert engine + REST API
|   |-- requirements.txt        # Redirect stub -> ../requirements.txt
|   `-- app/
|       |-- main.py             # FastAPI entrypoint, lifespan, Supabase client
|       |-- realtime_listener.py# Subscribes to office-updates broadcast
|       |-- kwh.py              # Time-weighted kWh integral
|       |-- alerts/
|       |   |-- rules.py        # after_hours + room_continuous_2h rules
|       `-- routes/
|           |-- status.py       # GET /status
|           |-- room.py         # GET /room/{room_id}
|           `-- usage.py        # GET /usage
|
|-- bot/                        # Discord bot
|   |-- requirements.txt        # Redirect stub -> ../requirements.txt
|   |-- bot.py                  # Realtime subscription + command prefix
|   |-- commands.py             # !status, !room, !usage
|   `-- openrouter_client.py    # Rate-limited OpenRouter wrapper
|
|-- simulator/                  # Office device state simulator
|   |-- requirements.txt        # Redirect stub -> ../requirements.txt
|   |-- main.py                 # Tick loop, wires scenarios together
|   |-- state_machine.py        # SimulatedClock + DeviceStore
|   `-- scenarios.py            # DaytimeRandom, ForgottenDevice, MeetingBurst
|
|-- dashboard/                  # Next.js live dashboard
|   |-- .env.local              # NEXT_PUBLIC_ vars (Supabase URL + publishable key)
|   |-- app/                    # Next.js App Router pages
|   |-- components/             # AlertsPanel, DeviceStatusPanel, PowerMeter, SVG
|   `-- lib/                    # Supabase client, hooks, types
|
|-- supabase/
|   |-- migrations/             # SQL migration files (schema + triggers)
|   `-- seed.sql                # 3 rooms, 15 devices, all initially OFF
|
`-- docs/
    |-- Implementation_Plan.md
    |-- api-contract.md
    `-- progress.md
```

---

## Prerequisites

| Tool    | Minimum version | Purpose                   |
| ------- | --------------- | ------------------------- |
| Python  | 3.11+           | Backend, bot, simulator   |
| Node.js | 18+             | Dashboard (Next.js)       |
| npm     | 9+              | Dashboard package manager |
| Git     | any             | Clone the repo            |

You also need:

- A **Supabase** project (free tier is fine) with the migrations applied
- A **Discord bot token** and a channel ID for alerts
- An **OpenRouter** API key (free tier) for the bot's humanized responses

---

## Installation

### 1. Clone the repository

```
git clone https://github.com/SolaimanK05/IO-Control-Techathon-Nationals-Rover-Summit.git
cd IO-Control-Techathon-Nationals-Rover-Summit
```

### 2. Create the shared Python virtual environment

All three Python services (backend, bot, simulator) share a single virtual environment at the repo root.

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

**Mac / Linux:**

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

That single install covers every dependency for the backend, bot, and simulator.

### 3. Install dashboard dependencies

```
cd dashboard
npm install
cd ..
```

### 4. Configure environment variables

Copy the template and fill in your values:

```
cp .env.example .env
```

See the [Environment Variables](#environment-variables) section below for the full reference.

The dashboard needs its own env file because Next.js requires `NEXT_PUBLIC_` prefixed variables to be inside the project folder:

```
cp dashboard/env.local.example dashboard/.env.local
```

Fill in `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.

### 5. Apply database migrations

In your Supabase project, open the SQL Editor and run each migration file in order:

```
supabase/migrations/20260101000001_schema.sql
supabase/migrations/20260101000002_realtime_triggers.sql
supabase/migrations/0004_data_api_grants.sql
supabase/migrations/0005_fix_realtime.sql
supabase/migrations/0006_client_alerts_clear.sql
```

Then run the seed file to populate the 3 rooms and 15 devices:

```
supabase/seed.sql
```

You can run all of these through the Supabase Dashboard SQL Editor or via the Supabase CLI.

---

## Environment Variables

All Python services read from the root `.env`. The dashboard reads from `dashboard/.env.local`.

### Root `.env`

```
# --- Supabase ---
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable-key>   # Safe for frontend. Never use this on the backend.
SUPABASE_SECRET_KEY=<service-role-key>       # Backend + simulator only. Never expose this.

# --- Simulator ---
SIM_HOURS_PER_REAL_SECOND=0.5    # 1 real second = 0.5 simulated hours (1 sim day = 48 real seconds)
FORCE_DEMO_SCENARIOS=true        # Forces meeting burst to always run long. Set false for random behaviour.
TICK_INTERVAL_SECONDS=2          # How often the simulator ticks (real seconds)

# --- Backend ---
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# --- Discord Bot ---
DISCORD_BOT_TOKEN=<your-bot-token>
DISCORD_ALERTS_CHANNEL_ID=<channel-id-integer>
BACKEND_BASE_URL=http://localhost:8000

# --- OpenRouter ---
OPENROUTER_API_KEY=sk-or-<key>
OPENROUTER_MODEL=<model-name>
OPENROUTER_RATE_LIMIT_PER_MIN=15
```

### `dashboard/.env.local`

```
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

Note: The publishable key (formerly called "anon key") is safe to embed in browser code. The secret/service_role key must never appear in `dashboard/.env.local`.

---

## Running the Services

All Python services use the shared root venv. Open a separate terminal for each service.

### Backend (FastAPI alert engine)

```powershell
# Windows
.\venv\Scripts\uvicorn app.main:app --reload --app-dir backend

# Mac / Linux
venv/bin/uvicorn app.main:app --reload --app-dir backend
```

Or from inside the backend directory:

```powershell
cd backend
..\venv\Scripts\uvicorn app.main:app --reload
```

The backend starts on `http://localhost:8000` by default. Confirm it is healthy:

```
curl http://localhost:8000/health
# {"ok": true}
```

On startup you should see:

```
INFO  Subscribed to realtime topic 'office-updates'
INFO  Starting alert reconciliation sweep...
INFO  Alert reconciliation sweep complete.
INFO  Periodic room-continuous check started (every 3s)
```

### Simulator

```powershell
# Windows — from repo root
.\venv\Scripts\python simulator\main.py

# Mac / Linux
venv/bin/python simulator/main.py
```

The simulator prints its simulated time and device-on count on every tick:

```
[simulator] sim time = 2026-07-04T09:00:00+00:00 | devices on = 3/15
[simulator] sim time = 2026-07-04T09:00:30+00:00 | devices on = 4/15
[meeting-burst] LONG (>=2h) burst started in 'Work Room 1'
```

### Discord Bot

```powershell
# Windows — from repo root
.\venv\Scripts\python bot\bot.py

# Mac / Linux
venv/bin/python bot/bot.py
```

### Dashboard

```
cd dashboard
npm run dev
```

Open `http://localhost:3000` in your browser.

### Starting all Python services at once (optional)

```powershell
# Windows PowerShell — runs all three in background jobs
Start-Job { cd C:\path\to\IO; .\venv\Scripts\uvicorn app.main:app --app-dir backend }
Start-Job { cd C:\path\to\IO; .\venv\Scripts\python simulator\main.py }
Start-Job { cd C:\path\to\IO; .\venv\Scripts\python bot\bot.py }
```

---

## How the Alert Engine Works

The backend evaluates two rules, both generic over N rooms and N devices — nothing is hardcoded.

### Rule 1: After Hours

**Condition:** A device has `status = true` and its `last_changed` timestamp falls outside 09:00-17:00 simulated time.

**Trigger path:** The simulator writes `UPDATE devices SET status = true, last_changed = <5PM sim time>`. The Postgres trigger inserts a `device_events` row and broadcasts to `office-updates`. The backend receives the event, reads the simulated hour from the payload timestamp, and inserts an `alerts` row if no active alert already exists for that device.

**Cleared:** Automatically when the device turns off (the next `status = false` event for that device).

**Discord:** Posts `Alert: <device> in <room> left on after hours` when raised. Silent on clear.

### Rule 2: Continuous Room 2h+

**Condition:** Every device in a room has been continuously ON for more than 2 simulated hours.

**Trigger path:** Unlike the after-hours rule, this condition becomes true because time passes, not because a state changes. The backend runs a 3-second periodic check that reads the latest simulated timestamp from `device_events` and compares it against each fully-ON room's `all_on_since` time (the most recent turn-ON event across all devices in the room).

**Cleared:** Not automatically cleared. The alert stays on the dashboard as a historical record of the event. A user can dismiss it manually via the Clear button.

**Discord:** Posts `Alert: All devices in <room> have been on continuously for over 2 hours` when raised.

---

## Simulator Scenarios

The simulator runs three independent behaviors on every tick.

### Daytime Random Toggle

During 09:00-17:00 simulated time, randomly toggles individual devices with a 5% probability per tick, bounded at 40% of devices on simultaneously. Devices in an active meeting-burst room are excluded so the burst streak stays unbroken.

### Scenario A: Forgotten Device (every night)

At 17:00 simulated, selects 2-4 random devices across the office, turns everything else off, and leaves those devices on overnight. At 09:00 the next simulated day, turns them off. Guarantees at least one `after_hours` alert every night.

### Scenario B: Meeting Burst (every day)

Once per simulated day at a random daytime hour (09:00-14:00), turns all 5 devices in one random room on simultaneously. The burst always runs for 2.5 simulated hours, guaranteeing a `room_continuous_2h` alert crosses the 2-hour threshold before the room powers down. Short bursts (0.5 sim hours) can also occur if `FORCE_DEMO_SCENARIOS=false`.

### Simulated Clock Speed

With `SIM_HOURS_PER_REAL_SECOND=0.5`:

| Real time  | Simulated time                                 |
| ---------- | ---------------------------------------------- |
| 1 second   | 30 simulated minutes                           |
| 2 seconds  | 1 simulated hour                               |
| 48 seconds | 1 full simulated day                           |
| 4 seconds  | 2 simulated hours (continuous alert threshold) |

Alerts should appear within seconds of starting both services.

---

## API Reference

Base URL: `http://localhost:8000`

All endpoints are read-only. The bot calls these exclusively — it never touches Supabase directly.

### GET /status

Returns the full office snapshot grouped by room.

```json
{
  "rooms": [
    {
      "room_id": "uuid",
      "room_name": "Work Room 1",
      "devices": [
        {
          "device_id": "uuid",
          "label": "Fan 1",
          "svg_id": "w1-fan-top",
          "type": "fan",
          "status": true,
          "watts": 60,
          "last_changed": "2026-07-04T17:30:00+00:00"
        }
      ],
      "room_power_watts": 195
    }
  ],
  "total_power_watts": 390,
  "generated_at": "2026-07-04T17:30:05+00:00"
}
```

### GET /room/{room_id}

Returns one room plus its active uncleared alerts.

```json
{
  "room_id": "uuid",
  "room_name": "Work Room 1",
  "devices": [ ... ],
  "room_power_watts": 195,
  "active_alerts": [
    {
      "id": "uuid",
      "type": "after_hours",
      "message": "Fan 1 in Work Room 1 left on after hours",
      "raised_at": "2026-07-04T17:00:00+00:00"
    }
  ]
}
```

### GET /usage

Returns instantaneous power and a time-weighted kWh estimate for the current simulated day.

```json
{
  "total_power_watts_now": 390,
  "estimated_kwh_today": 0.0325,
  "as_of": "2026-07-04T17:30:00+00:00"
}
```

The `estimated_kwh_today` value is computed as a time-weighted integral over `device_events` — the exact on/off durations for each device, not an average.

### GET /health

```json
{ "ok": true }
```

### Bot Commands

| Command        | Description                                                          |
| -------------- | -------------------------------------------------------------------- |
| `!status`      | Full office snapshot, all rooms and devices, humanized by OpenRouter |
| `!room <name>` | One room's status and active alerts. Name is fuzzy-matched.          |
| `!usage`       | Current power draw and kWh estimate for today                        |

---

## Troubleshooting

### Backend starts but no alerts appear

1. Check that the simulator is running and printing tick output.
2. Check the backend logs for `Subscribed to realtime topic 'office-updates'`. If missing, the Realtime subscription failed.
3. Verify `SUPABASE_SECRET_KEY` is the service_role key, not the publishable/anon key. The alert engine writes to the `alerts` table and needs elevated permissions.
4. In Supabase Dashboard, check Realtime is enabled for the `devices` table under Database -> Replication.

### Discord bot receives no alerts

1. Confirm `DISCORD_ALERTS_CHANNEL_ID` is the integer channel ID, not the channel name.
2. Confirm the bot has permission to send messages in that channel.
3. Check the bot logs for `Subscribed to realtime topic 'office-alerts'`.
4. Manually insert a row into `public.alerts` via the Supabase SQL Editor and check if the trigger fires — go to Database -> Webhooks or check Realtime Inspector.

### `room_continuous_2h` alert never fires

1. Confirm the backend is running (it runs the 3-second periodic check).
2. Check backend logs for `periodic check room=... hours_on=X.XX` — this confirms the check is running and what it sees.
3. Confirm `FORCE_DEMO_SCENARIOS=true` in root `.env` so the meeting burst always runs the full 2.5 sim hours.
4. Confirm `SIM_HOURS_PER_REAL_SECOND` is set high enough that 2 simulated hours elapse within a reasonable real-time window.

### Simulator cannot find `.env`

The simulator uses `find_dotenv()` which walks up from the `simulator/` folder until it finds a `.env` file. Make sure the root `.env` exists and is filled in. Do not create a separate `simulator/.env`.

### Dashboard shows stale data after a page refresh

The initial data load is a direct Supabase query; the live updates come from Realtime. If Realtime is disconnected (network hiccup), refresh the page — the initial fetch will resync state.

### `backend/venv` directory could not be deleted

If `uvicorn` was running, Windows locks the `.exe` files in the venv. Stop the backend process first, then delete the folder:

```powershell
Remove-Item -Path backend\venv -Recurse -Force
```

The shared root `venv/` is now the correct one to use for all services.

```

Made by Blueprint

```
