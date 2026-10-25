-- Community summaries and protected withdrawal. Run this entire file in Supabase SQL Editor.
-- Additive and repeatable: existing reports and browser rate-limit history are preserved.
begin;

alter table public.reports add column if not exists withdrawal_hash text
  check (withdrawal_hash ~ '^[0-9a-f]{64}$');
alter table public.reports add column if not exists withdrawn_at timestamptz;
alter table public.reports add column if not exists hidden_at timestamptz;
-- Only the hash can be supplied on insert. Public users cannot set moderation/withdrawal timestamps.
grant insert (withdrawal_hash) on public.reports to anon;

create or replace function public.report_features()
returns jsonb language sql immutable set search_path = '' as $$
  select '{"version":1,"withdrawal":true}'::jsonb
$$;
revoke all on function public.report_features() from public, anon, authenticated;
grant execute on function public.report_features() to anon;

-- The browser keeps a random 256-bit secret; the database only stores its SHA-256 hash.
-- Knowing another browser UUID or an aggregate count does not grant access to its reports.
create or replace function public.my_report_options(browser_id uuid, browser_token text)
returns table (place_id text, hazard text, kind text, created_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if browser_token is null or browser_token !~ '^[0-9a-f]{64}$' then return; end if;
  return query
    select r.place_id, r.hazard, r.kind, max(r.created_at)
    from public.reports r
    where r.client_id = browser_id
      and r.withdrawal_hash = encode(sha256(convert_to(browser_token, 'UTF8')), 'hex')
      and r.withdrawn_at is null and r.hidden_at is null
      and r.created_at > now() - interval '24 hours'
    group by r.place_id, r.hazard, r.kind
    order by max(r.created_at) desc limit 250;
end $$;
revoke all on function public.my_report_options(uuid, text) from public, anon, authenticated;
grant execute on function public.my_report_options(uuid, text) to anon;

create or replace function public.withdraw_report_option(
  browser_id uuid, browser_token text, target_place text, target_kind text
) returns boolean language plpgsql security definer set search_path = '' as $$
declare token_hash text;
begin
  if browser_token is null or browser_token !~ '^[0-9a-f]{64}$' then return false; end if;
  token_hash := encode(sha256(convert_to(browser_token, 'UTF8')), 'hex');
  perform pg_advisory_xact_lock(hashtextextended(browser_id::text, 0));
  update public.reports r set withdrawn_at = now()
    where r.client_id = browser_id and r.withdrawal_hash = token_hash
      and r.place_id = target_place and r.kind = target_kind and r.withdrawn_at is null
      and r.created_at > now() - interval '24 hours';
  -- Idempotent retry after a lost response. A wrong secret always returns false.
  return exists (select 1 from public.reports r
    where r.client_id = browser_id and r.withdrawal_hash = token_hash
      and r.place_id = target_place and r.kind = target_kind and r.withdrawn_at is not null
      and r.created_at > now() - interval '24 hours');
end $$;
revoke all on function public.withdraw_report_option(uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.withdraw_report_option(uuid, text, text, text) to anon;

-- One browser's repeated choice counts only once per summary window, never as corroboration.
-- Withdrawn/moderated rows remain available to the existing rate-limit trigger, but not aggregates.
create or replace function public.report_summary(hours int default 24)
returns table (place_id text, hazard text, total bigint, reporters bigint,
               problem_reports bigint, clear_reports bigint, last_report_at timestamptz, kinds jsonb)
language sql stable security definer set search_path = '' as $$
  with recent as (
    select r.place_id, r.hazard, r.kind, r.client_id, max(r.created_at) as created_at
    from public.reports r
    where r.created_at > now() - make_interval(hours => least(greatest(hours, 1), 168))
      and r.withdrawn_at is null and r.hidden_at is null
    group by r.place_id, r.hazard, r.kind, r.client_id
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
revoke all on function public.report_summary(int) from public, anon, authenticated;
grant execute on function public.report_summary(int) to anon;

create or replace function public.report_counts(days int default 7)
returns table (place_id text, hazard text, kind text, day date, n bigint)
language sql stable security definer set search_path = '' as $$
  select r.place_id, r.hazard, r.kind, (r.created_at at time zone 'America/Los_Angeles')::date as day,
         count(distinct r.client_id) as n
  from public.reports r
  where r.created_at > now() - make_interval(days => least(greatest(days, 1), 30))
    and r.withdrawn_at is null and r.hidden_at is null
  group by 1, 2, 3, 4
$$;
revoke all on function public.report_counts(int) from public, anon, authenticated;
grant execute on function public.report_counts(int) to anon;

notify pgrst, 'reload schema';
commit;
