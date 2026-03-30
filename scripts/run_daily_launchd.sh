#!/usr/bin/env bash
# LaunchAgent entrypoint: load repo .env, then run the daily cycle.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
exec "${REPO_ROOT}/.venv/bin/python3" -m src.main
