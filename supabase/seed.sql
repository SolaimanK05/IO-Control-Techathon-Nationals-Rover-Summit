-- ============================================================
-- Seed data: 3 rooms, 15 devices (2 fans + 3 lights each), all OFF.
-- svg_id values are taken verbatim from Office_PNG.svg — see
-- docs/api-contract.md Section 1.2.1 for the source-of-truth table.
-- ============================================================

insert into public.rooms (name) values
  ('Drawing Room'),
  ('Work Room 1'),
  ('Work Room 2');

-- Drawing Room
insert into public.devices (room_id, type, label, svg_id, status, watts, last_changed)
select id, 'fan',   'Fan 1',   'd-fan-top',          false, 60, now() from public.rooms where name = 'Drawing Room'
union all
select id, 'fan',   'Fan 2',   'd-fan-bottom',       false, 60, now() from public.rooms where name = 'Drawing Room'
union all
select id, 'light', 'Light 1', 'd-light-top-left',   false, 15, now() from public.rooms where name = 'Drawing Room'
union all
select id, 'light', 'Light 2', 'd-light-top-right',  false, 15, now() from public.rooms where name = 'Drawing Room'
union all
select id, 'light', 'Light 3', 'd-light-bottom',     false, 15, now() from public.rooms where name = 'Drawing Room';

-- Work Room 1
insert into public.devices (room_id, type, label, svg_id, status, watts, last_changed)
select id, 'fan',   'Fan 1',   'w1-fan-top',         false, 60, now() from public.rooms where name = 'Work Room 1'
union all
select id, 'fan',   'Fan 2',   'w1-fan-bottom',      false, 60, now() from public.rooms where name = 'Work Room 1'
union all
select id, 'light', 'Light 1', 'w1-light-top-left',  false, 15, now() from public.rooms where name = 'Work Room 1'
union all
select id, 'light', 'Light 2', 'w1-light-top-right', false, 15, now() from public.rooms where name = 'Work Room 1'
union all
select id, 'light', 'Light 3', 'w1-light-bottom',    false, 15, now() from public.rooms where name = 'Work Room 1';

-- Work Room 2
insert into public.devices (room_id, type, label, svg_id, status, watts, last_changed)
select id, 'fan',   'Fan 1',   'w2-fan-top',         false, 60, now() from public.rooms where name = 'Work Room 2'
union all
select id, 'fan',   'Fan 2',   'w2-fan-bottom',      false, 60, now() from public.rooms where name = 'Work Room 2'
union all
select id, 'light', 'Light 1', 'w2-light-top-left',  false, 15, now() from public.rooms where name = 'Work Room 2'
union all
select id, 'light', 'Light 2', 'w2-light-top-right', false, 15, now() from public.rooms where name = 'Work Room 2'
union all
select id, 'light', 'Light 3', 'w2-light-bottom',    false, 15, now() from public.rooms where name = 'Work Room 2';