-- ============================================================
-- Migration 0002: Event-driven realtime triggers
--
-- Uses realtime.send() (not realtime.broadcast_changes()) because
-- our broadcast payloads need enriched fields (room_id, label,
-- type, watts) that live on devices/rooms, not on device_events
-- alone. See docs/api-contract.md Section 2 for exact payload shapes.
--
-- Channels are PUBLIC (private = false): this app has no auth
-- system, so there's nothing to authorize against. Anyone with the
-- publishable key can subscribe. Acceptable for this hackathon
-- demo; would need Realtime Authorization + private channels added
-- before any real production deployment.
-- ============================================================

-- ---------------------------------------------------------------
-- 1. devices status change -> device_events row + "office-updates" broadcast
--
-- Application contract: callers UPDATE devices SET status = ?,
-- last_changed = <simulated_ts> WHERE id = ?. They never write to
-- device_events or call realtime.send() directly — this trigger is
-- the only path, so the event log can never drift from device state.
-- ---------------------------------------------------------------

create or replace function public.handle_device_status_change()
returns trigger
security definer
language plpgsql
as $$
declare
  v_room_id uuid;
begin
  -- Only act when status actually changed (last_changed may be
  -- touched for other reasons in the future; guard against no-op broadcasts)
  if NEW.status is distinct from OLD.status then

    insert into public.device_events (device_id, prev_status, new_status, ts)
    values (NEW.id, OLD.status, NEW.status, NEW.last_changed);

    select room_id into v_room_id from public.devices where id = NEW.id;

    perform realtime.send(
      jsonb_build_object(
        'event', 'device_status_changed',
        'payload', jsonb_build_object(
          'device_id', NEW.id,
          'room_id', v_room_id,
          'label', NEW.label,
          'type', NEW.type,
          'new_status', NEW.status,
          'watts', NEW.watts,
          'ts', NEW.last_changed
        )
      ),
      'device_status_changed',   -- event name
      'office-updates',          -- fixed topic per api-contract.md
      false                      -- public channel, no auth required
    );

  end if;

  return NEW;
end;
$$;

create trigger trg_device_status_change
after update on public.devices
for each row
execute function public.handle_device_status_change();

-- ---------------------------------------------------------------
-- 2. alerts insert -> "alert_raised" broadcast on "office-alerts"
-- ---------------------------------------------------------------

create or replace function public.handle_alert_raised()
returns trigger
security definer
language plpgsql
as $$
begin
  perform realtime.send(
    jsonb_build_object(
      'event', 'alert_raised',
      'payload', jsonb_build_object(
        'id', NEW.id,
        'type', NEW.type,
        'room_id', NEW.room_id,
        'device_id', NEW.device_id,
        'message', NEW.message,
        'raised_at', NEW.raised_at,
        'cleared_at', NEW.cleared_at
      )
    ),
    'alert_raised',
    'office-alerts',
    false
  );
  return NEW;
end;
$$;

create trigger trg_alert_raised
after insert on public.alerts
for each row
execute function public.handle_alert_raised();

-- ---------------------------------------------------------------
-- 3. alerts cleared_at set -> "alert_cleared" broadcast on "office-alerts"
-- ---------------------------------------------------------------

create or replace function public.handle_alert_cleared()
returns trigger
security definer
language plpgsql
as $$
begin
  if OLD.cleared_at is null and NEW.cleared_at is not null then
    perform realtime.send(
      jsonb_build_object(
        'event', 'alert_cleared',
        'payload', jsonb_build_object(
          'id', NEW.id,
          'type', NEW.type,
          'room_id', NEW.room_id,
          'device_id', NEW.device_id,
          'message', NEW.message,
          'raised_at', NEW.raised_at,
          'cleared_at', NEW.cleared_at
        )
      ),
      'alert_cleared',
      'office-alerts',
      false
    );
  end if;
  return NEW;
end;
$$;

create trigger trg_alert_cleared
after update on public.alerts
for each row
execute function public.handle_alert_cleared();