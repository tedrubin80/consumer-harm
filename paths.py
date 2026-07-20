"""Resolve data directories (local, Docker volume, legacy ~/opportunity_harm)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def data_root() -> Path:
    if env := os.environ.get("OPPORTUNITY_HARM_DATA"):
        return Path(env)
    if (REPO_ROOT / "index" / "cfpb_summary.db").is_file():
        return REPO_ROOT
    legacy = Path.home() / "opportunity_harm"
    if legacy.is_dir() and (legacy / "index").is_dir():
        return legacy
    return REPO_ROOT / "data"


def cfpb_csv_path() -> Path:
    return data_root() / "cfpb" / "extracted" / "complaints.csv"


def summary_db_path() -> Path:
    return data_root() / "index" / "cfpb_summary.db"
