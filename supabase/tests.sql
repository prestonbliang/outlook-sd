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
