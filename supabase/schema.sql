-- Outlook SD community reports. Run once in the Supabase SQL editor.
-- Structured, one-tap reports only: no free text, no exact location, no names or emails.
-- The public (anon) role can add reports and read daily counts; it can never read raw rows.

-- Canonical places from api/places.json. Re-run this file after updating that list.
create table if not exists public.report_places (id text primary key, coastal boolean not null);
alter table public.report_places enable row level security;
revoke all on public.report_places from public, anon, authenticated;
insert into public.report_places (id, coastal) values
  ('alpine', false),
  ('balboa-park', false),
  ('barrio-logan', true),
  ('black-mountain-ranch', false),
  ('bonita', false),
  ('bonsall', false),
  ('borrego-springs', false),
  ('bostonia', false),
  ('boulevard', false),
  ('camp-pendleton-mainside', false),
  ('camp-pendleton-south', true),
  ('campo', false),
  ('carlsbad', true),
  ('carmel-mountain-ranch', false),
  ('carmel-valley', false),
  ('casa-de-oro-mount-helix', false),
  ('chula-vista', true),
  ('clairemont-mesa', false),
  ('college-area', false),
  ('coronado', true),
  ('crest', false),
  ('del-mar', true),
  ('del-mar-mesa', false),
  ('descanso', false),
  ('downtown', true),
  ('east-elliott', false),
  ('el-cajon', false),
  ('elfin-forest', false),
  ('encanto-neighborhoods', false),
  ('encinitas', true),
  ('escondido', false),
  ('eucalyptus-hills', false),
  ('fairbanks-ranch', false),
  ('fairbanks-ranch-country-club', false),
  ('fallbrook', false),
  ('granite-hills', false),
  ('greater-golden-hill', false),
  ('harbison-canyon', false),
  ('harmony-grove', false),
  ('hidden-meadows', false),
  ('imperial-beach', true),
  ('jacumba', false),
  ('jamul', false),
  ('julian', false),
  ('kearny-mesa', false),
  ('la-jolla', true),
  ('la-mesa', false),
  ('la-presa', false),
  ('lake-san-marcos', false),
  ('lakeside', false),
  ('lemon-grove', false),
  ('linda-vista', false),
  ('los-penasquitos-canyon', false),
  ('mid-city-city-heights', false),
  ('mid-city-eastern-area', false),
  ('mid-city-kensington-talmadge', false),
  ('mid-city-normal-heights', false),
  ('midway-pacific-highway', true),
  ('military-facilities', false),
  ('mira-mesa', false),
  ('miramar-ranch-north', false),
  ('mission-bay-park', true),
  ('mission-beach', true),
  ('mission-valley', false),
  ('mount-laguna', false),
  ('national-city', true),
  ('navajo', false),
  ('north-park', false),
  ('ocean-beach', true),
  ('oceanside', true),
  ('old-town-san-diego', false),
  ('otay-mesa', false),
  ('otay-mesa-nestor', true),
  ('pacific-beach', true),
  ('pacific-highlands-ranch', false),
  ('pala', false),
  ('peninsula', true),
  ('pine-valley', false),
  ('potrero', false),
  ('poway', false),
  ('rainbow', false),
  ('ramona', false),
  ('rancho-bernardo', false),
  ('rancho-encantada', false),
  ('rancho-penasquitos', false),
  ('rancho-san-diego', false),
  ('rancho-santa-fe', false),
  ('sabre-springs', false),
  ('san-diego-country-estates', false),
  ('san-marcos', false),
  ('san-pasqual', false),
  ('san-ysidro', false),
  ('santee', false),
  ('scripps-miramar-ranch', false),
  ('serra-mesa', false),
  ('skyline-paradise-hills', false),
  ('solana-beach', true),
  ('southeastern-san-diego', false),
  ('spring-valley', false),
  ('tierrasanta', false),
  ('tijuana-river-valley', false),
  ('torrey-highlands', false),
  ('torrey-hills', false),
  ('torrey-pines', true),
  ('university', true),
  ('uptown', false),
  ('valley-center', false),
  ('via-de-la-valle', false),
  ('vista', false),
  ('winter-gardens', false)
on conflict (id) do update set coastal = excluded.coastal;

create table if not exists public.reports (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  place_id   text not null check (place_id ~ '^[a-z0-9-]{2,60}$'),
  hazard     text not null check (hazard in ('water', 'air', 'heat', 'flood', 'fire')),
  kind       text not null check (kind in (
               'water_sewage', 'water_sign', 'water_ok',
               'air_smoke', 'air_ok',
               'heat_extreme', 'heat_ok',
               'flood_street', 'flood_overtop', 'flood_ok',
               'fire_smoke', 'fire_ok')),
  client_id  uuid not null,  -- random ID kept in the reporter's browser; used only for rate limits
  check (split_part(kind, '_', 1) = hazard)
);
create index if not exists reports_recent on public.reports (created_at);
create index if not exists reports_client on public.reports (client_id, created_at);

alter table public.reports enable row level security;
drop policy if exists "anyone can add a report" on public.reports;
create policy "anyone can add a report" on public.reports for insert to anon with check (true);
-- No select/update/delete policy: raw rows are never readable or editable through the public API.

-- Rate limits: 10 reports per device per hour; the same report from the same device and place once per 6 hours.
create or replace function public.reports_rate_limit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- Serialize requests from the same browser, including requests arriving concurrently.
  perform pg_advisory_xact_lock(hashtextextended(new.client_id::text, 0));
  if not exists (select 1 from public.report_places where id = new.place_id) then
    raise exception 'Choose a listed San Diego neighborhood' using errcode = 'P0001';
  end if;
  if new.hazard = 'water' and not exists (
    select 1 from public.report_places where id = new.place_id and coastal
  ) then
    raise exception 'Choose a coastal neighborhood for a beach report' using errcode = 'P0001';
  end if;
  if (select count(*) from reports where client_id = new.client_id and created_at > now() - interval '1 hour') >= 10 then
    raise exception 'Too many reports from this device in the last hour' using errcode = 'P0001';
  end if;
  if exists (select 1 from reports where client_id = new.client_id and place_id = new.place_id and kind = new.kind
             and created_at > now() - interval '6 hours') then
    raise exception 'You already sent this report for this place in the last 6 hours' using errcode = 'P0001';
  end if;
  new.created_at := now();  -- clients cannot backdate reports
  return new;
end $$;
drop trigger if exists reports_rate_limit on public.reports;
create trigger reports_rate_limit before insert on public.reports for each row execute function public.reports_rate_limit();

-- Daily counts per place, hazard and report type (Pacific dates), last 1–30 days. No client IDs.
create or replace function public.report_counts(days int default 7)
returns table (place_id text, hazard text, kind text, day date, n bigint)
language sql stable security definer set search_path = public as $$
  select r.place_id, r.hazard, r.kind, (r.created_at at time zone 'America/Los_Angeles')::date as day, count(*) as n
  from reports r
  where r.created_at > now() - make_interval(days => least(greatest(days, 1), 30))
  group by 1, 2, 3, 4
$$;
revoke all on function public.report_counts(int) from public;
grant execute on function public.report_counts(int) to anon;

-- Recent coverage, with distinct browser counts for each neighborhood/hazard.
-- A browser code is a spam deterrent, not proof of a unique person.
create or replace function public.report_summary(hours int default 24)
returns table (place_id text, hazard text, total bigint, reporters bigint,
               problem_reports bigint, clear_reports bigint, last_report_at timestamptz, kinds jsonb)
language sql stable security definer set search_path = public as $$
  with recent as (
    select * from reports
    where created_at > now() - make_interval(hours => least(greatest(hours, 1), 168))
  ), grouped as (
    select r.place_id, r.hazard, count(*) as total, count(distinct r.client_id) as reporters,
           count(*) filter (where right(r.kind, 3) <> '_ok') as problem_reports,
           count(*) filter (where right(r.kind, 3) = '_ok') as clear_reports, max(r.created_at) as last_report_at
    from recent r group by 1, 2
  ), kinds as (
    select k.place_id, k.hazard, jsonb_object_agg(k.kind, k.n) as kinds
    from (select r.place_id, r.hazard, r.kind, count(*) as n from recent r group by 1, 2, 3) k
    group by 1, 2
  )
  select g.*, k.kinds from grouped g join kinds k using (place_id, hazard)
$$;
revoke all on function public.report_summary(int) from public;
grant execute on function public.report_summary(int) to anon;

-- Do not let callers use the table or trigger function outside the intended API.
revoke all on public.reports from public, anon, authenticated;
grant insert (place_id, hazard, kind, client_id) on public.reports to anon;
grant usage on sequence public.reports_id_seq to anon;
revoke all on function public.reports_rate_limit() from public;
