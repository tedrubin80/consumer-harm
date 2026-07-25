#!/bin/sh
set -eu

BAK="/app/deploy/cfpb_summary.db"
DEST="/data/index/cfpb_summary.db"

mkdir -p /data/index

if [ -f "$BAK" ]; then
  if [ ! -f "$DEST" ] || [ "$(stat -c%s "$DEST" 2>/dev/null || echo 0)" -lt 100000 ]; then
    cp -f "$BAK" "$DEST"
  else
    python3 - <<'PY'
import shutil
import sqlite3
from pathlib import Path

bak = Path("/app/deploy/cfpb_summary.db")
dest = Path("/data/index/cfpb_summary.db")
try:
    n = sqlite3.connect(dest).execute("SELECT COUNT(*) FROM product_stats").fetchone()[0]
except Exception:
    n = 0
if n == 0 and bak.is_file():
    shutil.copy(bak, dest)
PY
  fi
fi

exec streamlit run dashboard/app.py \
  --server.port "${PORT}" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false
