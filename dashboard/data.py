"""Load CFPB summary aggregates — evolution vs. void framing."""

from __future__ import annotations

import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from harm_themes import THEME_DESCRIPTIONS, THEME_ORDER, classify_harm_theme
from paths import summary_db_path
from period_config import StudyPeriod, load_study_period, month_in_range

DB_PATH = Path(os.environ.get("CFPB_SUMMARY_DB", summary_db_path()))

BANKING_PRODUCTS = {
    "Credit card",
    "Prepaid card",
    "Mortgage",
    "Checking or savings account",
    "Student loan",
    "Vehicle loan or lease",
    "Payday loan, title loan, personal loan, or advance loan",
    "Money transfer, virtual currency, or money service",
}

INDUSTRY_LABELS = {
    "Credit card": "Credit card",
    "Prepaid card": "Prepaid card",
    "Mortgage": "Mortgage",
    "Checking or savings account": "Bank accounts",
    "Debt collection": "Debt collection",
    "Student loan": "Student loan",
    "Vehicle loan or lease": "Auto loan/lease",
    "Payday loan, title loan, personal loan, or advance loan": "Payday/personal loan",
    "Money transfer, virtual currency, or money service": "Money transfer/crypto",
    "Credit reporting or other personal consumer reports": "Credit reporting",
}


def db_available() -> bool:
    return DB_PATH.is_file()


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


@lru_cache(maxsize=1)
def meta() -> dict[str, str]:
    if not db_available():
        return {}
    conn = _conn()
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    conn.close()
    return dict(rows)


@lru_cache(maxsize=1)
def load_product_stats() -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM product_stats ORDER BY complaints DESC", _conn())
    if df.empty:
        return df
    total = df["complaints"].sum()
    df["share_pct"] = (100 * df["complaints"] / total).round(2)
    df["relief_total"] = df["monetary_relief"] + df["nonmonetary_relief"]
    df["relief_rate"] = (100 * df["relief_total"] / df["complaints"].replace(0, 1)).round(2)
    df["void_rate"] = (100 * df["explanation_only"] / df["complaints"].replace(0, 1)).round(2)
    df["narrative_rate"] = (100 * df["with_narrative"] / df["complaints"].replace(0, 1)).round(2)
    df["industry_label"] = df["product"].map(lambda p: INDUSTRY_LABELS.get(p, p[:40]))
    df["is_banking"] = df["product"].isin(BANKING_PRODUCTS)
    return df


@lru_cache(maxsize=1)
def load_banking_comparison() -> pd.DataFrame:
    df = load_product_stats()
    return df[df["is_banking"]].sort_values("complaints", ascending=False)


@lru_cache(maxsize=1)
def load_credit_card_subissues() -> pd.DataFrame:
    try:
        df = pd.read_sql(
            "SELECT * FROM credit_card_subissues ORDER BY complaints DESC", _conn()
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    for col in ("monetary_relief", "nonmonetary_relief", "explanation_only", "with_narrative"):
        if col not in df.columns:
            df[col] = 0
    df["relief_total"] = df["monetary_relief"] + df["nonmonetary_relief"]
    df["relief_rate"] = (100 * df["relief_total"] / df["complaints"].replace(0, 1)).round(1)
    df["void_rate"] = (100 * df["explanation_only"] / df["complaints"].replace(0, 1)).round(1)
    df["theme"] = df.apply(lambda r: classify_harm_theme(r["issue"], r["sub_issue"]), axis=1)
    return df


@lru_cache(maxsize=1)
def load_theme_monthly() -> pd.DataFrame:
    try:
        df = pd.read_sql(
            "SELECT * FROM credit_card_theme_monthly WHERE month != 'unknown' ORDER BY month",
            _conn(),
        )
        df = _clip_monthly_to_study(df)
    except Exception:
        df = pd.DataFrame()
    if not df.empty:
        df["relief_rate"] = (100 * df["relief"] / df["complaints"].replace(0, 1)).round(1)
        df["void_rate"] = (100 * df["explanation_only"] / df["complaints"].replace(0, 1)).round(1)
        return df
    # Fallback: roll up from subissues (counts only, no void over time)
    return pd.DataFrame()


@lru_cache(maxsize=1)
def load_harm_themes() -> pd.DataFrame:
    """Per-theme complaint volume and void/relief rates."""
    sub = load_credit_card_subissues()
    if sub.empty or "theme" not in sub.columns:
        return pd.DataFrame()
    themed = sub[sub["theme"].notna()].copy()
    if themed.empty:
        return pd.DataFrame()
    agg = (
        themed.groupby("theme", as_index=False)
        .agg(
            complaints=("complaints", "sum"),
            relief_total=("relief_total", "sum"),
            explanation_only=("explanation_only", "sum"),
            with_narrative=("with_narrative", "sum"),
        )
    )
    agg["relief_rate"] = (100 * agg["relief_total"] / agg["complaints"].replace(0, 1)).round(1)
    agg["void_rate"] = (100 * agg["explanation_only"] / agg["complaints"].replace(0, 1)).round(1)
    agg["narrative_rate"] = (100 * agg["with_narrative"] / agg["complaints"].replace(0, 1)).round(1)
    order = {t: i for i, t in enumerate(THEME_ORDER)}
    agg["sort"] = agg["theme"].map(lambda t: order.get(t, 99))
    return agg.sort_values("sort").drop(columns="sort")


def load_theme_subissues(theme: str) -> pd.DataFrame:
    sub = load_credit_card_subissues()
    if sub.empty:
        return sub
    return sub[sub["theme"] == theme].sort_values("complaints", ascending=False)


@lru_cache(maxsize=1)
def compute_theme_evolution() -> pd.DataFrame:
    tm = load_theme_monthly()
    if tm.empty:
        return pd.DataFrame()
    early, recent = _period_split(tm, months=36)
    rows = []
    for theme in THEME_ORDER:
        e = early[early["theme"] == theme]
        r = recent[recent["theme"] == theme]
        ev, rv = int(e["complaints"].sum()), int(r["complaints"].sum())
        er = round(100 * e["relief"].sum() / ev, 1) if ev else 0
        rr = round(100 * r["relief"].sum() / rv, 1) if rv else 0
        ev_void = round(100 * e["explanation_only"].sum() / ev, 1) if ev else 0
        rv_void = round(100 * r["explanation_only"].sum() / rv, 1) if rv else 0
        vol_chg = round(100 * (rv - ev) / ev, 1) if ev else 0
        rows.append(
            {
                "theme": theme,
                "early_volume": ev,
                "recent_volume": rv,
                "volume_change_pct": vol_chg,
                "early_relief_rate": er,
                "recent_relief_rate": rr,
                "relief_change_pts": round(rr - er, 1),
                "early_void_rate": ev_void,
                "recent_void_rate": rv_void,
                "void_change_pts": round(rv_void - ev_void, 1),
            }
        )
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def granular_focus_snapshot() -> dict:
    """Headline stats for APR and denial themes."""
    themes = load_harm_themes()
    if themes.empty:
        return {}
    out = {}
    for key, theme in [("apr", "APR & interest"), ("denial", "Denial & access")]:
        row = themes[themes["theme"] == theme]
        if row.empty:
            continue
        r = row.iloc[0]
        out[f"{key}_complaints"] = int(r["complaints"])
        out[f"{key}_void_rate"] = float(r["void_rate"])
        out[f"{key}_relief_rate"] = float(r["relief_rate"])
    evo = compute_theme_evolution()
    if not evo.empty:
        for key, theme in [("apr", "APR & interest"), ("denial", "Denial & access")]:
            row = evo[evo["theme"] == theme]
            if not row.empty:
                r = row.iloc[0]
                out[f"{key}_void_trend"] = float(r["void_change_pts"])
                out[f"{key}_relief_trend"] = float(r["relief_change_pts"])
    return out


@lru_cache(maxsize=1)
def load_credit_card_issues() -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM credit_card_issues ORDER BY complaints DESC", _conn())
    if not df.empty:
        df["relief_total"] = df["monetary_relief"] + df["nonmonetary_relief"]
        df["relief_rate"] = (100 * df["relief_total"] / df["complaints"].replace(0, 1)).round(2)
    return df


@lru_cache(maxsize=1)
def load_credit_card_companies() -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT * FROM credit_card_companies ORDER BY complaints DESC LIMIT 25", _conn()
    )
    if not df.empty:
        df["relief_total"] = df["monetary_relief"] + df["nonmonetary_relief"]
        df["relief_rate"] = (100 * df["relief_total"] / df["complaints"].replace(0, 1)).round(2)
        df["void_rate"] = (100 * df["explanation_only"] / df["complaints"].replace(0, 1)).round(2)
    return df


@lru_cache(maxsize=1)
def load_credit_card_monthly() -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT * FROM credit_card_monthly WHERE month != 'unknown' ORDER BY month", _conn()
    )
    df = _clip_monthly_to_study(df)
    if df.empty:
        return df
    for col in ("explanation_only", "in_progress"):
        if col not in df.columns:
            df[col] = 0
    df["relief_total"] = df["monetary_relief"] + df["nonmonetary_relief"]
    df["relief_rate"] = (100 * df["relief_total"] / df["complaints"].replace(0, 1)).round(2)
    df["void_rate"] = (100 * df["explanation_only"] / df["complaints"].replace(0, 1)).round(2)
    return df


@lru_cache(maxsize=1)
def load_company_monthly() -> pd.DataFrame:
    try:
        df = pd.read_sql(
            "SELECT * FROM credit_card_company_monthly WHERE month != 'unknown' ORDER BY month",
            _conn(),
        )
    except Exception:
        return pd.DataFrame()
    df = _clip_monthly_to_study(df)
    if not df.empty:
        df["relief_rate"] = (100 * df["relief"] / df["complaints"].replace(0, 1)).round(2)
    return df


@lru_cache(maxsize=1)
def load_issue_monthly() -> pd.DataFrame:
    try:
        df = pd.read_sql(
            "SELECT * FROM credit_card_issue_monthly WHERE month != 'unknown' ORDER BY month",
            _conn(),
        )
    except Exception:
        return pd.DataFrame()
    return _clip_monthly_to_study(df)


@lru_cache(maxsize=1)
def load_credit_card_responses() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT response, count FROM response_by_product WHERE product = 'Credit card' ORDER BY count DESC",
        _conn(),
    )


@lru_cache(maxsize=1)
def load_credit_card_channels() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT channel, count FROM channel_by_product WHERE product = 'Credit card' ORDER BY count DESC",
        _conn(),
    )


def study_period() -> StudyPeriod:
    loaded = StudyPeriod.from_meta(meta())
    return loaded or load_study_period()


def period_labels() -> dict[str, str]:
    p = study_period()
    m = meta()
    return {
        "study": m.get("study_label") or p.study_label,
        "early": m.get("early_label") or p.early_label,
        "recent": m.get("recent_label") or p.recent_label,
    }


def _clip_monthly_to_study(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "month" not in df.columns:
        return df
    p = study_period()
    return df[df["month"].apply(lambda mo: month_in_range(mo, p.start, p.end))]


def _period_split(df: pd.DataFrame, months: int = 36) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split monthly rows into fixed early vs recent calendar windows."""
    if df.empty:
        return df, df
    df = _clip_monthly_to_study(df)
    p = study_period()
    early = df[df["month"].apply(lambda mo: month_in_range(mo, p.start, p.early_end))]
    recent = df[df["month"].apply(lambda mo: month_in_range(mo, p.recent_start, p.end))]
    if not early.empty or not recent.empty:
        return early, recent
    # Legacy DBs without period meta: fall back to first/last N months in study clip only
    timeline = sorted(df["month"].unique())
    if len(timeline) <= months * 2:
        mid = len(timeline) // 2
        early_months, recent_months = set(timeline[:mid]), set(timeline[mid:])
    else:
        early_months, recent_months = set(timeline[:months]), set(timeline[-months:])
    return df[df["month"].isin(early_months)], df[df["month"].isin(recent_months)]


@lru_cache(maxsize=1)
def credit_card_void_snapshot() -> dict:
    ps = load_product_stats()
    cc = ps[ps["product"] == "Credit card"]
    if cc.empty:
        return {}
    row = cc.iloc[0]
    total = int(row["complaints"])
    relief = int(row["monetary_relief"] + row["nonmonetary_relief"])
    return {
        "total": total,
        "relief_pct": round(100 * relief / total, 1) if total else 0,
        "void_pct": round(float(row["explanation_only"]) / total * 100, 1) if total else 0,
        "in_progress_pct": round(float(row["in_progress"]) / total * 100, 1) if total else 0,
        "narrative_pct": round(float(row["narrative_rate"]), 1),
    }


@lru_cache(maxsize=1)
def story_headline() -> dict:
    monthly = load_credit_card_monthly()
    void = credit_card_void_snapshot()
    if monthly.empty:
        return void
    early, recent = _period_split(monthly)
    er = early["relief_rate"].mean() if not early.empty else 0
    rr = recent["relief_rate"].mean() if not recent.empty else 0
    ev = early["void_rate"].mean() if not early.empty else 0
    rv = recent["void_rate"].mean() if not recent.empty else 0
    return {
        **void,
        "early_relief_rate": round(float(er), 1),
        "recent_relief_rate": round(float(rr), 1),
        "early_void_rate": round(float(ev), 1),
        "recent_void_rate": round(float(rv), 1),
        "relief_trend": round(float(rr - er), 1),
        "void_trend": round(float(rv - ev), 1),
        **period_labels(),
    }


@lru_cache(maxsize=1)
def compute_issue_evolution(top_n: int = 8) -> pd.DataFrame:
    im = load_issue_monthly()
    if im.empty:
        issues = load_credit_card_issues().head(top_n)
        if issues.empty:
            return pd.DataFrame()
        return issues.rename(columns={"complaints": "recent"}).assign(early=0, change_pct=0.0)[
            ["issue", "early", "recent", "change_pct"]
        ]
    early, recent = _period_split(im)
    early_tot = early.groupby("issue")["complaints"].sum()
    recent_tot = recent.groupby("issue")["complaints"].sum()
    issues = (early_tot + recent_tot).sort_values(ascending=False).head(top_n).index
    rows = []
    for issue in issues:
        ev, rv = int(early_tot.get(issue, 0)), int(recent_tot.get(issue, 0))
        pct = round(100 * (rv - ev) / ev, 1) if ev else 100.0
        rows.append({"issue": issue, "early": ev, "recent": rv, "change_pct": pct})
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def compute_issuer_trajectories(top_n: int = 12) -> pd.DataFrame:
    cm = load_company_monthly()
    if cm.empty:
        return pd.DataFrame()
    early, recent = _period_split(cm)
    top = cm.groupby("company")["complaints"].sum().sort_values(ascending=False).head(top_n).index
    rows = []
    for company in top:
        e, r = early[early["company"] == company], recent[recent["company"] == company]
        ev, rv = int(e["complaints"].sum()), int(r["complaints"].sum())
        er = round(100 * e["relief"].sum() / ev, 1) if ev else 0
        rr = round(100 * r["relief"].sum() / rv, 1) if rv else 0
        vol_chg = round(100 * (rv - ev) / ev, 1) if ev else 0
        relief_chg = round(rr - er, 1)
        if relief_chg >= 3:
            signal = "More relief — possible learning"
        elif relief_chg <= -3:
            signal = "Less relief — deeper void"
        elif vol_chg >= 25:
            signal = "More complaints surfacing"
        elif vol_chg <= -25:
            signal = "Fewer complaints — cause unclear"
        else:
            signal = "Flat — same pattern"
        rows.append(
            {
                "company": company,
                "early_volume": ev,
                "recent_volume": rv,
                "volume_change_pct": vol_chg,
                "early_relief_rate": er,
                "recent_relief_rate": rr,
                "relief_change_pts": relief_chg,
                "signal": signal,
            }
        )
    return pd.DataFrame(rows)
