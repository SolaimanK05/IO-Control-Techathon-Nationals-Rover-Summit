-- ============================================================
-- Migration 0004: Explicit Data API grants
--
-- As of 2026, new Supabase projects may default to NOT auto-exposing
-- tables to the Data API (PostgREST/GraphQL) -- previously this was
-- automatic. supabase-py (used by the simulator and backend) talks
-- to Postgres over the Data API, not a direct connection, so without
-- these grants, writes from Phase 2 onward could fail with a 42501
-- permission error even though the SQL Editor (direct connection)
-- worked fine in Phase 1's validation test.
--
-- service_role needs full access (simulator/backend write via secret key).
-- anon/authenticated get SELECT only, consistent with the RLS-less-but-
-- still-read-appropriate posture already in place.
-- ============================================================

grant select, insert, update, delete on public.rooms         to service_role;
grant select, insert, update, delete on public.devices       to service_role;
grant select, insert, update, delete on public.device_events to service_role;
grant select, insert, update, delete on public.alerts        to service_role;

grant select on public.rooms         to anon, authenticated;
grant select on public.devices       to anon, authenticated;
grant select on public.device_events to anon, authenticated;
grant select on public.alerts        to anon, authenticated;