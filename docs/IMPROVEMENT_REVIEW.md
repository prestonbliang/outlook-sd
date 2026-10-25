# Outlook SD product and engineering improvement review

This pass improves the existing environmental-hazard application. The maintainer confirmed this scope after the supplied brief described a different energy/outage product. No energy features, accounts, persistent application servers, paid APIs, or new dependencies were added.

## Audit and prioritized work

The repository contains a statically exported Next.js frontend, five LightGBM hazard models, a Python ingestion/inference/scoring pipeline, FastAPI contracts used during static export, a SQLite forecast log, public geospatial assets, and anonymous Supabase community observations. The Vercel web service serves exported JSON. Model training is an explicit offline operation; community submissions never train or change a forecast.

Reviewed the application routes, shared components/hooks, data contracts, source adapters, model/evaluation boundaries, storage and validation helpers, database permissions, deployment scripts/workflows and tests. Existing model weights and published evaluation results were preserved. This is an engineering audit and desk research, not a claim of new model validation, resident interviews, or a penetration test.

| Priority | Verified weakness | Change |
| --- | --- | --- |
| P0 | A forecast can still look current after one of its shorter-lived inputs expires; static source health flags never age in the browser. | Export reference timestamps and source-specific expiry budgets, including state fallback ratings on mixed-source heat maps; recompute freshness using one shared browser clock. Preserve original source times and missing-data states. |
| P0 | State CalHeatScore issue dates were interpreted as UTC in source health but Pacific midnight in the forecast, making them appear stale hours early. | Normalize the issue-date reference to Pacific midnight consistently and add a regression test. Expiry budgets are unchanged. |
| P0 | A real morning refresh exposed an Air feature-calendar gap: the lag frame ended at yesterday's completed AQI and never included today's issue row. One empty pollutant frame then aborted the whole Air forecast. | Extend only the calendar index, without filling any observations, and skip an empty pollutant frame independently. Add tests that mutate issue-day/future observations to verify they do not enter forecast-time features. Model weights and published evaluation scores are unchanged. |
| P0 | Old model ratings can trigger the multi-hazard planning banner; old official warnings and incident markers can outlive their source check. | Only current forecasts trigger the compound banner. Carry warning expiry/feed checks; qualify old warnings and hide expired incident context. |
| P0 | A successful deploy can still lack reporting environment variables; build-time coverage can expire before a hosted check. | Add an opt-in `--require-reporting` check and re-evaluate actual forecast payloads at check time. Include the What-if page and scenario JSON in packaging/hosted checks. |
| P0 | Forks do not inherit release assets, leaving the hourly job without state and code builds using an older upstream snapshot. | Bootstrap the fork's real processed state; prefer the deploying repository's archive with a shared fallback only for a missing asset. Preserve explicit archive overrides and fail closed on other download errors. |
| P1 | Residents must open several hazard/detail pages to review upcoming days. | Add a three-day planning brief with local hazard preferences, beach/outdoor presets, explicit unknowns and links to the exact map day. No weighted safety score. |
| P1 | Saved neighborhoods only act as navigation shortcuts. | Add an on-demand comparison of today's five hazards across up to eight saved places, with per-place errors, cancellation and refresh. |
| P1 | Missing scenario artifacts can leave an apparently empty page. Errors have no recovery, zero baselines create invalid widths, and hardcoded sliders can exceed available data. | Validate each scenario independently, show explicit empty states, provide retry, derive controls from actual scenario points and preserve visual zero. Date recorded river-flow context rather than implying it is live. |
| P1 | Open snapshots can keep yesterday's day strip, detail window/advice or implicit map selection after Pacific midnight. | Advance the current-day verdict, dated advice and implicit map day together; preserve explicit shared dates and filter past day-strip entries. |
| P1 | The Data page conflates pipeline-imported report counts with the live browser reporting connection and promises hourly updates even when publishing is not configured. | Add publication metadata and a separate live community-read status. Explain the actual update paths and show source refresh failures without raw operational errors. |
| P2 | Export repeatedly reads unchanged Parquet tables. | Use a bounded, timestamp-invalidated read cache with independent frames for callers. SQLite reads remain fresh and connections close normally. |
| P2 | Vercel Git builds record no source revision because only `GITHUB_SHA` was recognized. | Accept `VERCEL_GIT_COMMIT_SHA` as a fallback in public publication metadata. |

## Research and product rationale

The County's [Beach and Bay program](https://www.sandiegocounty.gov/content/sdc/deh/lwqd/beachandbay.html) directs residents to current advisories and closures. That supports prominent official links and clearly dated model outputs; an older model estimate should never substitute for an official closure status.

The County's [extreme-heat resources](https://www.sandiegocounty.gov/hhsa/programs/phs/extreme_heat/) connect heat planning with cooling resources. The [CDC heat overview](https://www.cdc.gov/heat-health/about/) points residents to both heat and air-quality information. This motivates reviewing several hazards together, while keeping their different measurements separate. The planner is a navigation and attention aid, not personalized medical advice or a new hazard model.

## Innovation analysis

Usefulness, originality and impact below are product judgments (H = high, M = medium, L = low), not measured engagement or novelty claims. Existing features are extended where practical.

| Candidate | Usefulness / originality | Feasibility and required data/infrastructure | Effort | User impact | Decision |
| --- | --- | --- | --- | --- | --- |
| 1. Hazard-focused three-day planning brief | H / M | High; existing outlook JSON and local preferences | M | H | Implemented; preserve missing data and separate hazard units |
| 2. Compare family/work/saved neighborhoods | H / M | High; existing saved IDs and bounded static reads | M | H | Implemented; no additional requests until opened |
| 3. Time-aware source expiry while a page stays open | H / M | High; source timestamps and existing expiry budgets | M | H | Implemented; a clock does not manufacture new data |
| 4. Separate publication health from live report connectivity | H / M | High; build manifest and existing aggregate RPC | L | H | Implemented; makes deployment failures understandable |
| 5. Partial-data scenario recovery and honest zero baselines | H / L | High; existing scenario artifacts | L | M | Implemented; completes the existing workflow |
| 6. Current-only multi-hazard warnings | H / M | High; existing ratings and official alert expiry | M | H | Implemented; no composite probability |
| 7. Cool Zone directions and access details | H / M | Medium; maintained County facility records, verified hours/accessibility | M | H | Next; data verification comes before destination recommendations |
| 8. Official beach closure/advisory overlay | H / M | Medium; a documented, reliable County status feed and provenance | M | H | Next; current model water risk is a different product |
| 9. Neighborhood alert digests | H / M | Medium; opt-in delivery service, consent and operational ownership | H | H | Defer until publishing reliability is established |
| 10. Reviewed Spanish-language interface and guidance | H / L | Medium; complete translations and bilingual review of risk language | H | H | High-value next phase; avoid partial machine-translated safety copy |
| 11. Reporting-gap prompts for places already being viewed | M / M | High; existing distinct-browser summaries | L | M | Existing feature retained; never ask people to travel into hazards |
| 12. Stronger independent-report corroboration | H / M | Medium; sufficient observations and abuse-resistant identity without precise tracking | H | H | Defer; browser IDs are not verified people |
| 13. Share a planning focus with a dated map link | M / M | High; URL state and existing share controls | L | M | Next; no account or private profile required |
| 14. Printable preparedness/forecast summary | M / M | Medium; print layout, explicit publication and expiry timestamps | M | M | Defer until offline/stale messaging is tested carefully |
| 15. Publish-pipeline failure notifications | H / L | Medium; configured state/archive access, deployment credentials and an authorized recipient | M | H | Operational priority; no unsolicited notifications created |
| 16. Live calibration and model-drift reporting | H / H | Medium; matured outcomes, archived weather and sufficient live forecasts | H | H | Preserve existing track record; expand only with legitimate outcomes |
| 17. Combined hazard map overlays | M / M | Medium; existing layers, separate legends and substantial usability testing | H | M | Defer; avoid visually implying comparable numeric risk scales |
| 18. Community observation trends by neighborhood | M / M | Medium; enough real aggregate observations and reporting-bias explanations | M | M | Defer until participation supports meaningful interpretation |

## Technical decisions and limits

- Keep static hosting, the existing model pipeline and Supabase RLS. No new runtime API, authentication system or subscriptions are required.
- Attention is an explicit count of current Moderate-or-higher ratings (air starts at Unhealthy for sensitive groups). It is not a weighted cross-hazard score, model confidence, or a safety guarantee. Unrated, missing and stale forecasts cannot create an all-clear.
- Mobile Today keeps the existing current-condition cards first, with a quick link to the three-day brief. New planning controls do not displace the primary hazard workflow.
- Official warnings remain visible even when their status cannot be reconfirmed, with links to the authority and a recorded-warning qualification. Incident markers whose feed check expires are hidden rather than presented as current.
- One clock services freshness consumers, pauses updates when the document is hidden, rechecks on focus/visibility, and removes its timer/listeners after the last subscriber. It does not poll weather providers or make idle pages consume source quotas.
- Saved comparisons load only after user interaction, fetch at most eight known neighborhoods, preserve independent failures and abort unfinished reads when closed or changed.
- Parquet caching is bounded to 12 entries, keyed by path and nanosecond modification time, with copies returned to callers. Do not extrapolate a local export timing into a production latency guarantee. A SQL-cache experiment was discarded because it added memory and did not improve the measured export.
- Community write policies, repeat limits, public-key handling and privacy guarantees remain intact. No test observations were inserted into the live project. Planning preferences and saved places remain on the device.
- No model was retrained, no history gap was filled synthetically, and no model validation result was changed. Existing provisional water evaluation, delayed outcome labels and fire-rank limitations still apply.

## Verification

Validation results and commands are recorded after execution in `docs/STATUS.md`. Regression coverage includes source expiry before forecast expiry, invalid values, alert expiration, source-cache isolation/invalidation, SQLite WAL updates, focus persistence, exact-day map navigation, partial comparison recovery, scenario errors and empty states, zero bars, publication diagnostics and required deployment assets.

Existing browser tests continue to cover reporting success/duplicate rejection, accessibility, map assets, responsive layouts, browser history, storage errors, charts and all major routes. Browser fixtures are intercepted test data only and are never imported by production code.

## Remaining release blockers

The hosted browser build now reports `reporting: configured`, and the supplied Supabase project answered read-only aggregate queries with raw-report reads denied. A real resident observation still needs to verify the deployed write journey. No QA reports were inserted into production. Use `python scripts/check_deployment.py https://outlook-sd-kof2.vercel.app --require-reporting` after the code deployment to verify configuration and current forecasts together.

A real source refresh on October 25 produced Flood 4, Water 524, Heat 136, Fire 444 and, after fixing the calendar gap, Air 64 forecast rows. The exported snapshot has some current coverage for all five hazards. The public AirNow hourly backup worked without an API key; FIRMS remains unavailable without its key and is not presented as current. The validated archive was uploaded to the fork's `state` release. Code builds prefer that repository-owned state when Vercel Git metadata is enabled; a custom archive override remains available.

This bootstrap is a point-in-time refresh, not a working hourly publisher. The fork still needs Vercel deployment credentials for its existing workflow, appropriate provider/contact settings, and a successful strict hosted check after the code deployment. Keep freshness failures visible until that operational setup is complete.

## Five highest-impact next steps

1. Finish operational setup: current source data, an owned state archive, hourly publishing, reporting variables and a successful strict hosted check.
2. Add verified official beach closures/advisories beside model forecasts, with source and timestamps.
3. Add reviewed Spanish-language navigation and hazard guidance; test with bilingual San Diego residents.
4. Expand nearby cooling-resource access details and verified opening hours, including smoke/heat overlap.
5. Run resident usability sessions and a limited real reporting pilot; use that evidence before adding corroboration or notifications.

## Congressional App Challenge assessment

The defensible strengths are local relevance, five transparent model-backed hazards, held-out and live scoring, privacy-conscious community observations, accessible maps and planning across days/places. A reliable demonstration can show the chosen neighborhood, focus preset, exact-day map link, model limits and a genuine user observation within a minute.

The main weakness remains operations: an interactive app with stale inputs or disconnected reporting is not a finished live service. The improvements make those limits visible and testable; they do not eliminate the need for credentials, source access, real participation or user research. Describe this as a tested release candidate until the strict hosted and real-report checks succeed.
