# Outlook SD

Neighborhood environmental outlooks for San Diego County: **beach water, air quality, heat, coastal flooding and wildfire**.

**[Open the app](https://outlook-sd.vercel.app/) · [v1.0.0 release](https://github.com/prestonbliang/outlook-sd/releases/tag/v1.0.0)**

## Features

- Local forecasts with source timestamps, official warning links, interactive charts and a transparent track record.
- A San Diego map with hazard/date filters, neighborhood and ZIP search, shareable views and a list alternative to WebGL.
- Saved neighborhoods, side-by-side comparisons and a three-day planning brief.
- Community observations with 27 choices, plain-language summaries, reporting gaps and protected withdrawal of new reports within 24 hours.
- Historical river-flow and sea-level scenarios, nearby Cool Zones and a South Bay odor-complaint record.

Forecasts are estimates, not official advisories. Community reports are unverified and never change the forecasts. Missing reports do not establish safety. [Model results and limitations](docs/MODELS.md).

## Run locally

Requires **Python 3.12+, uv and Node.js 22**.

```bash
uv sync --frozen
npm --prefix web ci
test -f .env || cp .env.example .env
uv run python -m api.export
npm --prefix web run dev
```

A fresh clone has no live forecast data. This starts the app with explicit unavailable states; follow [Setup](docs/SETUP.md) to restore the existing `state` release and configure reporting. Do not retrain the committed models just to run the app. Never commit `.env` or use private Supabase keys in browser settings.

## Architecture and deployment

Python ingestion and LightGBM inference run in GitHub Actions. FastAPI assembles static JSON during the build; Next.js serves the exported site on Vercel. Supabase stores structured observations and enforces reporting permissions and limits.

This fork runs the live site and hourly publishing. Vercel Git builds use the root `vercel.json`; scheduled publishing uses Vercel's prebuilt static format. [Deployment guide](docs/VERCEL.md).

## Documentation

- [Verification and current status](docs/STATUS.md)
- [Release checks and demo guide](docs/RELEASE.md)
- [Community privacy, withdrawal and abuse controls](docs/COMMUNITY_SAFEGUARDS.md)
- [Model results and limitations](docs/MODELS.md)
- [Data, software and AI-use credits](CREDITS.md)

The repository includes tests for model/data boundaries, reporting permissions, deployment packaging, browser journeys, accessibility and responsive layouts. Reproduction commands are in the release guide.
