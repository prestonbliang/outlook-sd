-- Outlook SD community reports. Run once in the Supabase SQL editor.
-- Structured, one-tap reports only: no free text, no exact location, no names or emails.
-- The public (anon) role can add reports and read daily counts; it can never read raw rows.

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
