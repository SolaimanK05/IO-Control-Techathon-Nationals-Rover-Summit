-- ============================================================
-- Migration 0006: Allow clients to clear alerts directly
--
-- Decision (explicit, per your call): the dashboard's "Clear" button
-- writes directly from the browser using the publishable key, rather
-- than going through a server route with service_role. This requires
-- loosening the write grant that 0004 deliberately restricted to
-- service_role only.
--
-- To avoid turning this into "anyone can rewrite any alert's message/
-- room/device", the grant is UPDATE-only (no INSERT/DELETE), and a
-- BEFORE UPDATE guard trigger silently pins every column except
-- cleared_at back to its OLD value — so even a malicious or buggy
-- client can only ever set cleared_at, nothing else, regardless of
-- what they submit in the UPDATE statement.
-- ============================================================

grant update (cleared_at) on public.alerts to anon, authenticated;

create or replace function public.guard_alert_update()
returns trigger
language plpgsql
as $$
begin
  -- Pin every column except cleared_at back to its previous value.
  -- This runs BEFORE the write lands, so it's not a validation error —
  -- it just makes any attempted change to these columns a no-op.
  NEW.type       := OLD.type;
  NEW.room_id    := OLD.room_id;
  NEW.device_id  := OLD.device_id;
  NEW.message    := OLD.message;
  NEW.raised_at  := OLD.raised_at;
  -- cleared_at is intentionally NOT reset here — it's the one column
  -- clients are allowed to set.
  return NEW;
end;
$$;

drop trigger if exists trg_guard_alert_update on public.alerts;

create trigger trg_guard_alert_update
before update on public.alerts
for each row
execute function public.guard_alert_update();