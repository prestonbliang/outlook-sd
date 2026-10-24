-- Apply schema.sql first. This transaction rolls back every test observation.
begin;

-- Raw report rows must never be readable through public roles.
do $$
begin
  if has_table_privilege('anon', 'public.reports', 'SELECT') then
    raise exception 'anon can read raw reports';
  end if;
  if not has_function_privilege('anon', 'public.report_summary(int)', 'EXECUTE') then
    raise exception 'anon cannot read coverage summaries';
  end if;
  if has_table_privilege('anon', 'public.reports', 'UPDATE') or has_table_privilege('anon', 'public.reports', 'DELETE') then
    raise exception 'anon can modify existing reports';
  end if;
  if has_column_privilege('anon', 'public.reports', 'created_at', 'INSERT') then
    raise exception 'anon can supply a report timestamp';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'public.reports'::regclass) then
    raise exception 'reports row-level security is not enabled';
  end if;
end $$;

set local role anon;
insert into public.reports (place_id, hazard, kind, client_id) values
  ('imperial-beach', 'water', 'water_sewage', '00000000-0000-4000-a000-000000000001'),
  ('imperial-beach', 'water', 'water_ok', '00000000-0000-4000-a000-000000000001'),
  ('imperial-beach', 'water', 'water_ok', '00000000-0000-4000-a000-000000000002');

do $$
begin
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('imperial-beach', 'water', 'water_ok', '00000000-0000-4000-a000-000000000002');
    raise exception 'Expected a repeat-report rejection';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'You already sent this report%' then raise; end if;
  end;
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('not-a-real-place', 'air', 'air_smoke', '00000000-0000-4000-a000-000000000003');
    raise exception 'Expected an unknown-place rejection';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'Choose a listed%' then raise; end if;
  end;
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('alpine', 'water', 'water_ok', '00000000-0000-4000-a000-000000000003');
    raise exception 'Expected an inland-water rejection';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'Choose a coastal%' then raise; end if;
  end;
  begin
    perform count(*) from public.reports;
    raise exception 'Expected raw report reads to be denied';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('imperial-beach', 'air', 'water_ok', '00000000-0000-4000-a000-000000000003');
    raise exception 'Expected mismatched hazard/type to be rejected';
  exception when check_violation then null;
  end;
end $$;

-- Ten distinct observations are allowed; the eleventh is denied even for another hazard.
insert into public.reports (place_id, hazard, kind, client_id)
select 'imperial-beach', split_part(kind, '_', 1), kind, '00000000-0000-4000-a000-000000000004'::uuid
from unnest(array['water_sewage', 'water_sign', 'water_ok', 'air_smoke', 'air_ok', 'heat_extreme', 'heat_ok',
                  'flood_street', 'flood_overtop', 'flood_ok']) as types(kind);
do $$
begin
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('imperial-beach', 'fire', 'fire_smoke', '00000000-0000-4000-a000-000000000004');
    raise exception 'Expected hourly report cap';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'Too many reports from this device%' then raise; end if;
  end;
end $$;
reset role;

-- Scope the final assertion to these browser codes, independent of existing user data.
do $$
declare n int; browsers int;
begin
  select count(*), count(distinct client_id) into n, browsers from public.reports
  where client_id in ('00000000-0000-4000-a000-000000000001', '00000000-0000-4000-a000-000000000002');
  if n <> 3 or browsers <> 2 then raise exception 'Expected three reports from two browsers'; end if;
  if not exists (select 1 from public.report_summary(24) where place_id='imperial-beach' and hazard='water' and total >= 3 and reporters >= 2) then
    raise exception 'Coverage summary is missing the submitted observations';
  end if;
end $$;
rollback;
