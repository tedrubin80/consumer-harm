#!/bin/bash
# Download CFPB bulk CSV, rebuild summary DB, restart dashboard container (optional).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/period.env.example" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/period.env.example"
  set +a
fi

export OPPORTUNITY_HARM_DATA="${OPPORTUNITY_HARM_DATA:-$ROOT}"

echo "[refresh] Downloading CFPB complaints CSV…"
python3 "$ROOT/scripts/download_cfpb_complaints.py" --format csv

echo "[refresh] Building summary (fixed study window)…"
python3 "$ROOT/scripts/build_cfpb_summary.py"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx consumer-harm-dashboard; then
  echo "[refresh] Restarting consumer-harm-dashboard…"
  docker restart consumer-harm-dashboard
fi

echo "[refresh] Done."
