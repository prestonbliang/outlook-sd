# Community summaries, withdrawal and trust

Outlook SD describes submitted observations, not verified environmental conditions. The summary is deterministic text derived only from the selected structured choices. It surfaces conflicting concern/no-concern submissions and states that browser codes do not establish unique people or independent witnesses. Counts remain available as supporting detail. Neither the summary nor participation levels change model forecasts or official advisories.

## Existing Supabase project upgrade

Run the complete `supabase/report-management.sql` in the existing project's SQL Editor. This additive transaction is repeatable and preserves reports and rate-limit history. Fresh installations can run `supabase/schema.sql`, which includes it. No new database, environment variable, authentication provider or dependency is required. Reload the app after applying the migration.

The browser checks the read-only `report_features()` RPC. A missing RPC (HTTP 404) preserves legacy submissions, with removal explicitly unavailable. A temporary network/server error blocks new submissions and offers retry instead of silently creating reports that cannot be managed. Do not describe removal as deployed until the migration and frontend are both released.

## Ownership and withdrawal

Before a new managed report is submitted, the browser persists a separate, cryptographically random 256-bit token in local storage. Its SHA-256 hash is inserted with the report. The raw token is never inserted into the report table, included in URLs, or returned in public aggregates.

`my_report_options(browser_id, browser_token)` returns only the caller's matching active choices from the past 24 hours. `withdraw_report_option(browser_id, browser_token, target_place, target_kind)` requires both the browser code and matching secret, withdraws all active repeats of that choice in that neighborhood within 24 hours, and supports retries after a lost response. Neither function accepts arbitrary SQL. Execution is limited to `anon`, their search paths are fixed, and all table references are schema-qualified. Raw table SELECT/UPDATE/DELETE remain forbidden to public callers.

Reports made before token support cannot be recovered or withdrawn through this UI. Clearing storage loses management access. Browser storage is specific to the website origin: a different Vercel URL does not share the token. Sharing a browser also shares its reports and removal access; this is capability-based ownership, not an account system. Protecting against a compromised browser or an XSS vulnerability requires separate defenses.

Withdrawal immediately excludes the choice from live aggregates. Rows remain stored so withdrawal cannot reset the ten-submissions-per-hour and six-hour duplicate limits. Historical aggregate snapshots reflect withdrawal on the next successful pipeline run. The historical refresh replaces the requested window, including missing/empty results, and preserves older history. Network errors or malformed responses must not erase that history.

## Abuse controls and their limits

- Database checks restrict neighborhood, coastal water reporting, hazard/type pairs and timestamps.
- The existing trigger serializes submissions by browser code and enforces duplicate/hourly limits, including withdrawn rows.
- A summary counts a browser's repeated choice once per requested window; daily history counts it once per day.
- Structured choices prevent arbitrary user HTML, links or free text from reaching the interface.
- Owner withdrawal and administrator moderation are excluded from public aggregates.

These controls deter casual repetition. They do **not** prevent a determined attacker from rotating browser codes, opening multiple browsers, or coordinating false reports. Browser counts, a majority, and a CAPTCHA cannot prove the observation is truthful. Stronger public-launch bot resistance requires a deliberately configured server-verified CAPTCHA and/or authenticated reporting with independent rate limits. This release does not claim those integrations are installed. Do not call reports verified or use them as all-clear messages.

## Administrator moderation

Only trusted project administrators should use the Supabase SQL Editor to inspect raw reports. Locate suspected reports by neighborhood/type/time; review evidence and context before excluding them. To hide an identified row, use a parameterized administrator query or the SQL Editor with its actual numeric ID:

```sql
update public.reports set hidden_at = now() where id = 123;
```

Replace `123` with the reviewed report ID. Setting `hidden_at = null` restores a mistaken moderation action unless the report was withdrawn. Public users cannot supply or update `hidden_at`. Do not disclose raw browser codes or token hashes in screenshots, logs or exports.

## Verification

Apply the schema twice in a disposable PostgreSQL 17 database, then run `supabase/tests.sql`, `supabase/observation-options.tests.sql` and `supabase/report-management.tests.sql`. These check permissions, ownership, forged-token rejection, withdrawal retries, repeat-limit preservation, deduplication and moderator exclusion; transactions roll back test records. Never run browser QA against production submissions: Playwright intercepts all reporting endpoints.
