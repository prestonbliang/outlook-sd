#!/usr/bin/env bash
# Pipeline state between hourly runs: processed tables (minus training-only weather archives) + forecast log,
# stored as one asset on the GitHub release tagged "state". Usage: scripts/state.sh pack|unpack
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  pack)
    tar -czf state.tar.gz --exclude='data/processed/weather_g*' data/processed data/outlook.db
    ls -lh state.tar.gz ;;
  unpack)
    tar -xzf state.tar.gz && rm state.tar.gz ;;
  *) echo "usage: $0 pack|unpack" >&2; exit 2 ;;
esac
