# Outlook SD visual design

Design rationale and verification from the redesign stage. The audit describes the interface before these changes; historical test counts below are superseded by [STATUS.md](STATUS.md).

## Before the redesign

The static Next.js app already has neighborhood selection, five hazard forecasts, an interactive map, planning preferences, saved comparisons, anonymous Supabase reporting, historical scenarios and model/source transparency. Preserve these contracts and the existing Python export and Vercel build paths.

The existing interface is visually dominated by a narrow scrolling list and a full-height map. The homepage has no clear introduction, headings and controls compete for attention, source tables are dense, and repeated CSS overrides produce inconsistent spacing and component treatments. Charts have accessible data tables but little interactive exploration. Report deep links target content that appears after hydration and do not reliably scroll to it.

## Direction and implementation plan

1. Establish a coastal identity: deep teal ink, warm neutral canvas, white surfaces and restrained amber accents. Retain the established hazard/AQI colors and explicit text labels.
2. Rebuild the homepage hierarchy with a distinct typographic hero, actual neighborhood map, prominent local-outlook entry, a responsive forecast grid, a three-day planning workspace and a community contribution section.
3. Use shared SVG icons, page introductions, controls, status treatments, spacing, borders and elevation across navigation, maps, details, scenarios, reporting and source/model pages.
4. Improve purposeful interactions: disclosure feedback, map/report navigation, chart value exploration, visible focus and loading states. Use short transitions; respect reduced motion.
5. Verify existing journeys, responsive layouts, keyboard interaction, automated accessibility, real data/empty/error states and deployment. Inspect desktop/mobile screenshots and refine the implementation.

## System

- Typography: locally served Public Sans, weights 400/600; display sizes respond to viewport, body text stays readable and numeric values use tabular figures. No external font requests.
- Spacing: a 4 px base, with 8/12/16/24/32/48/64 px composition steps.
- Surfaces: quiet borders, three purposeful corner radii, restrained shadows and meaningful contrast. No decorative gradients or fabricated weather illustrations.
- Motion: short opacity, color and transform transitions. Content remains accessible without animation, and reduced-motion users receive no animated movement.
- Semantics: native radio groups, buttons, fieldsets, disclosures, headings and tables. Decorative icons are hidden from assistive technology; status and risk are never color-only.
- Trust: preserve original data timestamps, unavailable states, official warnings, scientific limitations, anonymous reporting and all existing validation. A visually polished page must not turn old data into a live claim.

This redesign adds no outage, energy or GridLab features: those are not part of the existing environmental-hazard product. No new runtime service, database migration or dependency is required.

## Executed verification

- Production static build and strict TypeScript passed; Vercel packaging preserves the existing static web service and all API JSON.
- Full Playwright suite: **168 passed**, none skipped, across Chromium, Firefox and WebKit. Existing reporting, duplicate rejection, maps, saved comparisons, planning, source status and scenario journeys remain covered. Added coverage for the hero-to-outlook journey, delayed report-anchor navigation, keyboard chart inspection and reduced motion.
- Responsive checks cover all six major routes at 320, 390, 768 and 1440 px. Automated WCAG A/AA checks pass, including the expanded reporting controls. Desktop and mobile screenshots were visually reviewed; mobile planning, tap targets and sticky-header spacing were refined before the final full run.
- **49 frontend unit tests** and **106 Python tests** (15 subtests) passed. The Python suite reports two existing dependency/source deprecations, not new application failures.
- No dependencies, model artifacts, database schema, reporting permissions, environment values or deployment configuration were changed in this redesign. No production reports were submitted during QA.
