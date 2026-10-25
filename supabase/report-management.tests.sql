-- Disposable database only. All test data rolls back.
begin;
set local role anon;

insert into public.reports (place_id, hazard, kind, client_id, withdrawal_hash) values
  ('alpine', 'heat', 'heat_shade', '10000000-0000-4000-a000-000000000001',
    encode(sha256(convert_to(repeat('a', 64), 'UTF8')), 'hex'));
do $$
begin
  if (select count(*) from public.my_report_options('10000000-0000-4000-a000-000000000001', repeat('a',64))) <> 1 then
    raise exception 'Owner must be able to recover active choices after reload';
  end if;
  if exists (select 1 from public.my_report_options('10000000-0000-4000-a000-000000000001', repeat('b',64))) then
    raise exception 'Knowing a browser UUID must not reveal its reports';
  end if;
  if public.withdraw_report_option('10000000-0000-4000-a000-000000000001', repeat('b',64), 'alpine', 'heat_shade') then
    raise exception 'Wrong secret withdrew another browser report';
  end if;
  if public.withdraw_report_option('10000000-0000-4000-a000-000000000002', repeat('a',64), 'alpine', 'heat_shade') then
    raise exception 'Wrong browser withdrew another browser report';
  end if;
  if not public.withdraw_report_option('10000000-0000-4000-a000-000000000001', repeat('a',64), 'alpine', 'heat_shade') then
    raise exception 'Owner withdrawal failed';
  end if;
  if not public.withdraw_report_option('10000000-0000-4000-a000-000000000001', repeat('a',64), 'alpine', 'heat_shade') then
    raise exception 'Withdrawal retry must be idempotent';
  end if;
  if exists (select 1 from public.my_report_options('10000000-0000-4000-a000-000000000001', repeat('a',64))) then
    raise exception 'Withdrawn choices remain in owner list';
  end if;
  if exists (select 1 from public.report_summary(24) where place_id='alpine') or
     exists (select 1 from public.report_counts(7) where place_id='alpine') then
    raise exception 'Withdrawn observations remain in public summaries';
  end if;
  begin
    insert into public.reports (place_id, hazard, kind, client_id) values
      ('alpine', 'heat', 'heat_shade', '10000000-0000-4000-a000-000000000001');
    raise exception 'Withdrawal must not bypass duplicate limits';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'You already sent this report%' then raise; end if;
  end;
  if has_table_privilege('anon','public.reports','SELECT') or
     has_table_privilege('anon','public.reports','UPDATE') or
     has_table_privilege('anon','public.reports','DELETE') or
     has_column_privilege('anon','public.reports','withdrawn_at','INSERT') or
     has_column_privilege('anon','public.reports','hidden_at','INSERT') then
    raise exception 'Management must not grant raw row access or timestamp spoofing';
  end if;
end $$;
reset role;

set local role anon;
insert into public.reports (place_id, hazard, kind, client_id, withdrawal_hash)
select 'la-jolla', split_part(kind,'_',1), kind, '10000000-0000-4000-a000-000000000004'::uuid,
       encode(sha256(convert_to(repeat('c',64),'UTF8')),'hex')
from unnest(array['water_sewage','water_sign','water_ok','air_smoke','air_ok','heat_extreme','heat_ok',
                  'flood_street','flood_overtop','flood_ok']) as choices(kind);
do $$
begin
  perform public.withdraw_report_option('10000000-0000-4000-a000-000000000004', repeat('c',64), 'la-jolla','water_sign');
  begin
    insert into public.reports (place_id,hazard,kind,client_id) values
      ('la-jolla','fire','fire_smoke','10000000-0000-4000-a000-000000000004');
    raise exception 'Withdrawal must not reset the hourly cap';
  exception when sqlstate 'P0001' then
    if sqlerrm not like 'Too many reports from this device%' then raise; end if;
  end;
  begin
    insert into public.reports (place_id,hazard,kind,client_id,withdrawal_hash) values
      ('la-jolla','fire','fire_smoke',gen_random_uuid(),'not-a-valid-hash');
    raise exception 'Invalid ownership hash was accepted';
  exception when check_violation then null;
  end;
end $$;
reset role;

-- A repeat after six hours is legal, but must not inflate the number choosing that option.
insert into public.reports (place_id,hazard,kind,client_id) values
  ('alpine','air','air_dust','10000000-0000-4000-a000-000000000003');
update public.reports set created_at=now()-interval '7 hours'
  where client_id='10000000-0000-4000-a000-000000000003';
set local role anon;
insert into public.reports (place_id,hazard,kind,client_id) values
  ('alpine','air','air_dust','10000000-0000-4000-a000-000000000003');
do $$
begin
  if not exists (select 1 from public.report_summary(24) where place_id='alpine' and hazard='air'
    and total=1 and reporters=1 and (kinds->>'air_dust')::int=1) then
    raise exception 'Repeated choices from one browser inflated the summary';
  end if;
end $$;
reset role;
update public.reports set hidden_at=now() where client_id='10000000-0000-4000-a000-000000000003';
set local role anon;
do $$
begin
  if exists (select 1 from public.report_summary(24) where place_id='alpine') then
    raise exception 'Moderated observations remain public';
  end if;
  if has_function_privilege('authenticated','public.withdraw_report_option(uuid,text,text,text)','EXECUTE') then
    raise exception 'Unexpected role has management access';
  end if;
end $$;
reset role;
rollback;
