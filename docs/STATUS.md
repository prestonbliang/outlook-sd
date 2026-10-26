# Release status

Verified October 25, 2026 (Pacific time). This is the current status record; older audit and design documents describe their respective development stages.

## Deployment

- Public app: **https://outlook-sd.vercel.app/**.
- Live-site source and scheduled publishing: **prestonbliang/outlook-sd**, branch `main`.
- The original repository is a shared source copy. Its hourly workflow remains disabled; it does not publish this website. This v1.0 documentation/version update is fork-only.
- Supabase reporting is configured. The observation-options and report-management migrations were applied, and live read-only capability/summary calls succeeded.
- Hourly publishing completed successfully: [verified run](https://github.com/prestonbliang/outlook-sd/actions/runs/40252530921). Both deployment and the public-site check passed.
- The runtime `state` release contains processed source data and the forecast log. It is separate from versioned source-code releases and is updated by the pipeline.

The deployment check verifies six pages, JSON endpoints, scenario/map data, 110 neighborhoods, publication freshness, some current forecast coverage and PMTiles byte ranges. The hourly check additionally compares the exact published source commit and snapshot timestamp with the build. It does not guarantee every feed or hazard is current everywhere.

## Verification evidence

Application behavior and the corrected deployment path were verified at commit `6741ed1`. The v1.0 release retains that behavior and updates documentation and version metadata.

| Check | Recorded result |
| --- | --- |
| Local Python suite with restored source tables | 115 passed; 17 subtests passed |
| Frontend unit tests | 52 passed |
| Playwright | 198 passed across Chromium, Firefox and WebKit |
| PostgreSQL 17 | Schema reapplied; validation, ownership, withdrawal, limits, deduplication and moderation tests passed |
| Build and static packaging | Passed |
| TypeScript and Ruff | Passed |
| Dependency audit | npm audit reported zero vulnerabilities for the tested dependency set |
| Public deployment with reporting required | Passed |

[Verified fork CI run](https://github.com/prestonbliang/outlook-sd/actions/runs/40252528996). Clean CI checkouts skip the nine historical-table tests when those uncommitted datasets are absent; browser reporting tests run against intercepted fixtures, not production submissions. Two existing Python deprecation warnings remain nonblocking.

Browser coverage includes the major routes, four viewport widths, automated WCAG checks, keyboard navigation, charts, saved places, planning, source expiry, storage/network failures and community reporting. These checks do not replace physical-device, assistive-technology or resident usability testing.

No synthetic observations were submitted to the live database during QA. Submission/withdrawal behavior was exercised with browser fixtures and an isolated database; live checks used read-only reporting RPCs.

## Known limits

- Models have different coverage, evaluation dates and weaknesses. Water evaluation remains provisional. [Details](MODELS.md).
- Provider refreshes can fail even when publishing succeeds. The verified fork used AirNow's public backup; FIRMS refresh requires its own key. Inspect Data for current source health.
- Anonymous browser codes and private removal tokens are not identity or truth verification. Resetting storage can bypass browser-code limits; stronger bot resistance requires additional server-verified controls. [Safeguards](COMMUNITY_SAFEGUARDS.md).
- Real-device/user testing, the competition application and video, and an accurate account of student and AI contributions remain submission responsibilities. A software release does not certify competition eligibility.
