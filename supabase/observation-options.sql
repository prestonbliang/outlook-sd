-- Add 15 structured observation choices without changing existing reports, privacy or limits.
-- Run this entire file in Supabase -> SQL Editor. Safe to run more than once.
begin;

create or replace function public.report_kinds()
returns text[] language sql immutable set search_path = public as $$
  select array[
    'water_sewage', 'water_sign', 'water_debris', 'water_foam', 'water_oily', 'water_ok',
    'air_smoke', 'air_dust', 'air_odor', 'air_ash', 'air_ok',
    'heat_extreme', 'heat_shade', 'heat_cooling', 'heat_night', 'heat_ok',
    'flood_street', 'flood_overtop', 'flood_path', 'flood_drain', 'flood_road', 'flood_ok',
    'fire_smoke', 'fire_ash', 'fire_flames', 'fire_closure', 'fire_ok'
  ]::text[]
$$;
revoke all on function public.report_kinds() from public;
grant execute on function public.report_kinds() to anon;

alter table public.reports drop constraint if exists reports_kind_check;
alter table public.reports add constraint reports_kind_check
  check (kind = any(public.report_kinds()));

-- Make the new read-only options RPC available to the browser immediately.
notify pgrst, 'reload schema';
commit;
