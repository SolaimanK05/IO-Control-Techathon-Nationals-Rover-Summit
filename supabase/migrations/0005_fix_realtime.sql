-- ============================================================
-- Migration 0005: Fix double-nested realtime.send() payload
--
-- Bug: the trigger functions in 0002 wrapped the enriched payload
-- inside a jsonb object shaped like { event: ..., payload: {...} }
-- and passed THAT WHOLE OBJECT as realtime.send()'s first argument
-- (the payload arg) -- while *also* correctly passing the event
-- name and topic as args 2/3.
--
-- realtime.send()'s signature is:
--   realtime.send(payload jsonb, event text, topic text, private boolean)
-- The first argument IS what the client receives as message.payload.
-- There is no wrapping needed -- event/topic are already separate args.
--
-- Effect of the bug: clients received
--   message.payload = { event: "device_status_changed", payload: { device_id: ..., ... } }
-- instead of
--   message.payload = { device_id: ..., ... }
-- so `message.payload.device_id` was always undefined, the
-- OfficeDevicesProvider's .map() never matched a device by id, and
-- setDevices() silently no-op'd on every broadcast. The channel
-- subscribed fine and the trigger fired fine -- which is why it
-- looked like "realtime isn't working" rather than a payload bug.
--
-- Fix: pass the enriched fields object directly as the payload arg,
-- with no outer 'event'/'payload' wrapper. Behavior is otherwise
-- identical -- same topics, same event names, same public channels.
-- ============================================================

create or replace function public.handle_device_status_change()
returns trigger
security definer
language plpgsql
as $$
declare
  v_room_id uuid;
begin
  if NEW.status is distinct from OLD.status then

    insert into public.device_events (device_id, prev_status, new_status, ts)
    values (NEW.id, OLD.status, NEW.status, NEW.last_changed);

    select room_id into v_room_id from public.devices where id = NEW.id;

    perform realtime.send(
      jsonb_build_object(
        'device_id', NEW.id,
        'room_id', v_room_id,
        'label', NEW.label,
        'type', NEW.type,
        'new_status', NEW.status,
        'watts', NEW.watts,
        'ts', NEW.last_changed
      ),
      'device_status_changed',   -- event name
      'office-updates',          -- fixed topic per api-contract.md
      false                      -- public channel, no auth required
    );

  end if;

  return NEW;
end;
$$;

create or replace function public.handle_alert_raised()
returns trigger
security definer
language plpgsql
as $$
begin
  perform realtime.send(
    jsonb_build_object(
      'id', NEW.id,
      'type', NEW.type,
      'room_id', NEW.room_id,
      'device_id', NEW.device_id,
      'message', NEW.message,
      'raised_at', NEW.raised_at,
      'cleared_at', NEW.cleared_at
    ),
    'alert_raised',
    'office-alerts',
    false
  );
  return NEW;
end;
$$;

create or replace function public.handle_alert_cleared()
returns trigger
security definer
language plpgsql
as $$
begin
  if OLD.cleared_at is null and NEW.cleared_at is not null then
    perform realtime.send(
      jsonb_build_object(
        'id', NEW.id,
        'type', NEW.type,
        'room_id', NEW.room_id,
        'device_id', NEW.device_id,
        'message', NEW.message,
        'raised_at', NEW.raised_at,
        'cleared_at', NEW.cleared_at
      ),
      'alert_cleared',
      'office-alerts',
      false
    );
  end if;
  return NEW;
end;
$$;

-- Triggers themselves are unchanged (still AFTER UPDATE/INSERT on the same
-- tables, still execute these same-named functions) -- create or replace
-- function is sufficient, no need to drop/recreate the trigger objects.