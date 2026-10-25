-- Run after schema.sql; every observation below is rolled back.
begin;
set local role anon;

do $$
declare option text;
begin
  if cardinality(public.report_kinds()) <> 27 then raise exception 'Expected all 27 observation choices'; end if;
  foreach option in array public.report_kinds() loop
    insert into public.reports (place_id, hazard, kind, client_id)
      values ('la-jolla', split_part(option, '_', 1), option, gen_random_uuid());
  end loop;
  if not exists (select 1 from public.report_summary(24) where place_id = 'la-jolla'
    and hazard = 'water' and (kinds->>'water_debris')::int >= 1 and problem_reports >= 5 and clear_reports >= 1) then
    raise exception 'New observations must appear in aggregate counts with the correct classification';
  end if;
  begin
    insert into public.reports (place_id, hazard, kind, client_id)
      values ('la-jolla', 'water', 'water_unrecognized', gen_random_uuid());
    raise exception 'Expected unknown kind to fail';
  exception when check_violation then null;
  end;
  begin
    insert into public.reports (place_id, hazard, kind, client_id)
      values ('la-jolla', 'air', 'water_debris', gen_random_uuid());
    raise exception 'Expected mismatched hazard to fail';
  exception when check_violation then null;
  end;
  begin
    perform count(*) from public.reports;
    raise exception 'Expanded choices must not expose raw reports';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
rollback;
