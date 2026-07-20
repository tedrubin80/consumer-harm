#!/usr/bin/env python3
"""
Build aggregated CFPB complaint summaries for the Consumer Harm dashboard.

Scans complaints.csv in chunks (full file ~8GB) and writes SQLite aggregates.

Usage:
    python build_cfpb_summary.py
    python build_cfpb_summary.py --csv ~/opportunity_harm/cfpb/extracted/complaints.csv
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from harm_themes import classify_harm_theme
from paths import cfpb_csv_path, summary_db_path
from period_config import StudyPeriod, load_study_period

DEFAULT_CSV = cfpb_csv_path()
DEFAULT_DB = summary_db_path()

CHUNK = 200_000

# Products we treat as "financial industries" for comparison charts
INDUSTRY_ORDER = [
    "Credit card",
    "Prepaid card",
    "Mortgage",
    "Checking or savings account",
    "Debt collection",
    "Student loan",
    "Vehicle loan or lease",
    "Payday loan, title loan, personal loan, or advance loan",
    "Money transfer, virtual currency, or money service",
    "Credit reporting or other personal consumer reports",
]

RELIEF_RESPONSES = {
    "Closed with monetary relief",
    "Closed with non-monetary relief",
}

ACTION_RESPONSES = RELIEF_RESPONSES | {"Closed with explanation"}


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS product_stats;
        DROP TABLE IF EXISTS product_monthly;
        DROP TABLE IF EXISTS response_by_product;
        DROP TABLE IF EXISTS channel_by_product;
        DROP TABLE IF EXISTS credit_card_issues;
        DROP TABLE IF EXISTS credit_card_subissues;
        DROP TABLE IF EXISTS credit_card_companies;
        DROP TABLE IF EXISTS credit_card_monthly;
        DROP TABLE IF EXISTS credit_card_issue_response;
        DROP TABLE IF EXISTS credit_card_states;
        DROP TABLE IF EXISTS credit_card_subproducts;
        DROP TABLE IF EXISTS credit_card_company_monthly;
        DROP TABLE IF EXISTS credit_card_issue_monthly;
        DROP TABLE IF EXISTS credit_card_theme_monthly;
        DROP TABLE IF EXISTS credit_card_subissue_monthly;
        DROP TABLE IF EXISTS meta;

        CREATE TABLE product_stats (
            product TEXT PRIMARY KEY,
            complaints INTEGER,
            with_narrative INTEGER,
            timely_yes INTEGER,
            monetary_relief INTEGER,
            nonmonetary_relief INTEGER,
            explanation_only INTEGER,
            in_progress INTEGER,
            untimely INTEGER,
            with_public_response INTEGER
        );

        CREATE TABLE product_monthly (
            product TEXT,
            month TEXT,
            complaints INTEGER,
            PRIMARY KEY (product, month)
        );

        CREATE TABLE response_by_product (
            product TEXT,
            response TEXT,
            count INTEGER,
            PRIMARY KEY (product, response)
        );

        CREATE TABLE channel_by_product (
            product TEXT,
            channel TEXT,
            count INTEGER,
            PRIMARY KEY (product, channel)
        );

        CREATE TABLE credit_card_issues (
            issue TEXT PRIMARY KEY,
            complaints INTEGER,
            monetary_relief INTEGER,
            nonmonetary_relief INTEGER,
            with_narrative INTEGER
        );

        CREATE TABLE credit_card_subissues (
            issue TEXT,
            sub_issue TEXT,
            complaints INTEGER,
            monetary_relief INTEGER DEFAULT 0,
            nonmonetary_relief INTEGER DEFAULT 0,
            explanation_only INTEGER DEFAULT 0,
            with_narrative INTEGER DEFAULT 0,
            PRIMARY KEY (issue, sub_issue)
        );

        CREATE TABLE credit_card_companies (
            company TEXT PRIMARY KEY,
            complaints INTEGER,
            monetary_relief INTEGER,
            nonmonetary_relief INTEGER,
            explanation_only INTEGER
        );

        CREATE TABLE credit_card_monthly (
            month TEXT PRIMARY KEY,
            complaints INTEGER,
            monetary_relief INTEGER,
            nonmonetary_relief INTEGER,
            explanation_only INTEGER DEFAULT 0,
            in_progress INTEGER DEFAULT 0
        );

        CREATE TABLE credit_card_issue_response (
            issue TEXT,
            response TEXT,
            count INTEGER,
            PRIMARY KEY (issue, response)
        );

        CREATE TABLE credit_card_states (
            state TEXT PRIMARY KEY,
            complaints INTEGER
        );

        CREATE TABLE credit_card_subproducts (
            sub_product TEXT PRIMARY KEY,
            complaints INTEGER
        );

        CREATE TABLE credit_card_company_monthly (
            company TEXT,
            month TEXT,
            complaints INTEGER,
            relief INTEGER,
            PRIMARY KEY (company, month)
        );

        CREATE TABLE credit_card_issue_monthly (
            issue TEXT,
            month TEXT,
            complaints INTEGER,
            relief INTEGER,
            PRIMARY KEY (issue, month)
        );

        CREATE TABLE credit_card_theme_monthly (
            theme TEXT,
            month TEXT,
            complaints INTEGER,
            relief INTEGER,
            explanation_only INTEGER,
            PRIMARY KEY (theme, month)
        );

        CREATE TABLE credit_card_subissue_monthly (
            issue TEXT,
            sub_issue TEXT,
            month TEXT,
            complaints INTEGER,
            relief INTEGER,
            explanation_only INTEGER,
            PRIMARY KEY (issue, sub_issue, month)
        );

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )


def month_key(date_val) -> str:
    if pd.isna(date_val):
        return "unknown"
    try:
        return pd.Timestamp(date_val).strftime("%Y-%m")
    except (ValueError, TypeError):
        return "unknown"


def is_credit_card(product: str) -> bool:
    p = (product or "").strip().lower()
    return p == "credit card" or p.startswith("credit card")


def filter_study_period(df: pd.DataFrame, period: StudyPeriod) -> pd.DataFrame:
    if df.empty:
        return df
    received = pd.to_datetime(df["Date received"], errors="coerce")
    start = pd.Timestamp(period.start)
    end = pd.Timestamp(period.end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    mask = received.notna() & (received >= start) & (received <= end)
    return df.loc[mask].copy()


def process_chunk(df: pd.DataFrame, agg: dict) -> None:
    df = df.copy()
    df["month"] = df["Date received"].map(month_key)
    df["has_narrative"] = df["Consumer complaint narrative"].fillna("").str.strip().astype(bool)
    df["has_public"] = df["Company public response"].fillna("").str.strip().astype(bool)
    df["response"] = df["Company response to consumer"].fillna("Unknown")
    df["timely"] = df["Timely response?"].fillna("").str.lower() == "yes"

    for product, g in df.groupby("Product"):
        ps = agg["product_stats"][product]
        ps["complaints"] += len(g)
        ps["with_narrative"] += int(g["has_narrative"].sum())
        ps["timely_yes"] += int(g["timely"].sum())
        ps["with_public_response"] += int(g["has_public"].sum())

        for resp, c in g["response"].value_counts().items():
            agg["response_by_product"][(product, resp)] += int(c)
            if resp == "Closed with monetary relief":
                ps["monetary_relief"] += int(c)
            elif resp == "Closed with non-monetary relief":
                ps["nonmonetary_relief"] += int(c)
            elif resp == "Closed with explanation":
                ps["explanation_only"] += int(c)
            elif resp == "In progress":
                ps["in_progress"] += int(c)
            elif resp == "Untimely response":
                ps["untimely"] += int(c)

        for month, c in g["month"].value_counts().items():
            agg["product_monthly"][(product, month)] += int(c)

        for channel, c in g["Submitted via"].fillna("Unknown").value_counts().items():
            agg["channel_by_product"][(product, channel)] += int(c)

    cc = df[df["Product"].map(is_credit_card)]
    if cc.empty:
        return

    cc = cc.copy()
    cc["sub_issue_norm"] = cc["Sub-issue"].fillna("(none)").astype(str).str.strip().replace("", "(none)")
    cc["is_relief"] = cc["response"].isin(RELIEF_RESPONSES)
    cc["is_void"] = cc["response"] == "Closed with explanation"

    for issue, g in cc.groupby("Issue"):
        cs = agg["cc_issues"][issue]
        cs["complaints"] += len(g)
        cs["with_narrative"] += int(g["has_narrative"].sum())
        cs["monetary_relief"] += int((g["response"] == "Closed with monetary relief").sum())
        cs["nonmonetary_relief"] += int((g["response"] == "Closed with non-monetary relief").sum())
        for resp, c in g["response"].value_counts().items():
            agg["cc_issue_response"][(issue, resp)] += int(c)

    for (issue, sub), g in cc.groupby(["Issue", "sub_issue_norm"]):
        si = agg["cc_subissues"][(issue, sub)]
        si["complaints"] += len(g)
        si["with_narrative"] += int(g["has_narrative"].sum())
        si["monetary_relief"] += int((g["response"] == "Closed with monetary relief").sum())
        si["nonmonetary_relief"] += int((g["response"] == "Closed with non-monetary relief").sum())
        si["explanation_only"] += int((g["response"] == "Closed with explanation").sum())

    for (issue, sub, month), g in cc.groupby(["Issue", "sub_issue_norm", "month"]):
        sm = agg["cc_subissue_monthly"][(issue, sub, month)]
        sm["complaints"] += len(g)
        sm["relief"] += int(g["is_relief"].sum())
        sm["explanation_only"] += int(g["is_void"].sum())

    cc["harm_theme"] = cc.apply(
        lambda r: classify_harm_theme(r["Issue"], r["sub_issue_norm"]), axis=1
    )
    themed = cc[cc["harm_theme"].notna()]
    for (theme, month), g in themed.groupby(["harm_theme", "month"]):
        tm = agg["cc_theme_monthly"][(theme, month)]
        tm["complaints"] += len(g)
        tm["relief"] += int(g["is_relief"].sum())
        tm["explanation_only"] += int(g["is_void"].sum())

    for company, g in cc.groupby("Company"):
        co = agg["cc_companies"][company]
        co["complaints"] += len(g)
        co["monetary_relief"] += int((g["response"] == "Closed with monetary relief").sum())
        co["nonmonetary_relief"] += int((g["response"] == "Closed with non-monetary relief").sum())
        co["explanation_only"] += int((g["response"] == "Closed with explanation").sum())

    for month, g in cc.groupby("month"):
        cm = agg["cc_monthly"][month]
        cm["complaints"] += len(g)
        cm["monetary_relief"] += int((g["response"] == "Closed with monetary relief").sum())
        cm["nonmonetary_relief"] += int((g["response"] == "Closed with non-monetary relief").sum())
        cm["explanation_only"] += int((g["response"] == "Closed with explanation").sum())
        cm["in_progress"] += int((g["response"] == "In progress").sum())

    for state, c in cc["State"].fillna("Unknown").value_counts().items():
        agg["cc_states"][state] += int(c)

    for sub, c in cc["Sub-product"].fillna("(general)").value_counts().items():
        agg["cc_subproducts"][sub] += int(c)

    for (company, month), g in cc.groupby(["Company", "month"]):
        agg["cc_company_monthly"][(company, month)]["complaints"] += len(g)
        agg["cc_company_monthly"][(company, month)]["relief"] += int(g["is_relief"].sum())

    for (issue, month), g in cc.groupby(["Issue", "month"]):
        agg["cc_issue_monthly"][(issue, month)]["complaints"] += len(g)
        agg["cc_issue_monthly"][(issue, month)]["relief"] += int(g["is_relief"].sum())


def flush_agg(conn: sqlite3.Connection, agg: dict) -> None:
    for product, ps in agg["product_stats"].items():
        conn.execute(
            """
            INSERT INTO product_stats VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(product) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              with_narrative=with_narrative+excluded.with_narrative,
              timely_yes=timely_yes+excluded.timely_yes,
              monetary_relief=monetary_relief+excluded.monetary_relief,
              nonmonetary_relief=nonmonetary_relief+excluded.nonmonetary_relief,
              explanation_only=explanation_only+excluded.explanation_only,
              in_progress=in_progress+excluded.in_progress,
              untimely=untimely+excluded.untimely,
              with_public_response=with_public_response+excluded.with_public_response
            """,
            (
                product,
                ps["complaints"],
                ps["with_narrative"],
                ps["timely_yes"],
                ps["monetary_relief"],
                ps["nonmonetary_relief"],
                ps["explanation_only"],
                ps["in_progress"],
                ps["untimely"],
                ps["with_public_response"],
            ),
        )

    for (product, month), c in agg["product_monthly"].items():
        conn.execute(
            """
            INSERT INTO product_monthly VALUES (?,?,?)
            ON CONFLICT(product, month) DO UPDATE SET complaints=complaints+excluded.complaints
            """,
            (product, month, c),
        )

    for (product, resp), c in agg["response_by_product"].items():
        conn.execute(
            """
            INSERT INTO response_by_product VALUES (?,?,?)
            ON CONFLICT(product, response) DO UPDATE SET count=count+excluded.count
            """,
            (product, resp, c),
        )

    for (product, channel), c in agg["channel_by_product"].items():
        conn.execute(
            """
            INSERT INTO channel_by_product VALUES (?,?,?)
            ON CONFLICT(product, channel) DO UPDATE SET count=count+excluded.count
            """,
            (product, channel, c),
        )

    for issue, cs in agg["cc_issues"].items():
        conn.execute(
            """
            INSERT INTO credit_card_issues VALUES (?,?,?,?,?)
            ON CONFLICT(issue) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              monetary_relief=monetary_relief+excluded.monetary_relief,
              nonmonetary_relief=nonmonetary_relief+excluded.nonmonetary_relief,
              with_narrative=with_narrative+excluded.with_narrative
            """,
            (issue, cs["complaints"], cs["monetary_relief"], cs["nonmonetary_relief"], cs["with_narrative"]),
        )

    for (issue, sub), si in agg["cc_subissues"].items():
        conn.execute(
            """
            INSERT INTO credit_card_subissues VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(issue, sub_issue) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              monetary_relief=monetary_relief+excluded.monetary_relief,
              nonmonetary_relief=nonmonetary_relief+excluded.nonmonetary_relief,
              explanation_only=explanation_only+excluded.explanation_only,
              with_narrative=with_narrative+excluded.with_narrative
            """,
            (
                issue,
                sub,
                si["complaints"],
                si["monetary_relief"],
                si["nonmonetary_relief"],
                si["explanation_only"],
                si["with_narrative"],
            ),
        )

    for company, co in agg["cc_companies"].items():
        conn.execute(
            """
            INSERT INTO credit_card_companies VALUES (?,?,?,?,?)
            ON CONFLICT(company) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              monetary_relief=monetary_relief+excluded.monetary_relief,
              nonmonetary_relief=nonmonetary_relief+excluded.nonmonetary_relief,
              explanation_only=explanation_only+excluded.explanation_only
            """,
            (company, co["complaints"], co["monetary_relief"], co["nonmonetary_relief"], co["explanation_only"]),
        )

    for month, cm in agg["cc_monthly"].items():
        conn.execute(
            """
            INSERT INTO credit_card_monthly VALUES (?,?,?,?,?,?)
            ON CONFLICT(month) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              monetary_relief=monetary_relief+excluded.monetary_relief,
              nonmonetary_relief=nonmonetary_relief+excluded.nonmonetary_relief,
              explanation_only=explanation_only+excluded.explanation_only,
              in_progress=in_progress+excluded.in_progress
            """,
            (
                month,
                cm["complaints"],
                cm["monetary_relief"],
                cm["nonmonetary_relief"],
                cm.get("explanation_only", 0),
                cm.get("in_progress", 0),
            ),
        )

    for (issue, resp), c in agg["cc_issue_response"].items():
        conn.execute(
            """
            INSERT INTO credit_card_issue_response VALUES (?,?,?)
            ON CONFLICT(issue, response) DO UPDATE SET count=count+excluded.count
            """,
            (issue, resp, c),
        )

    for state, c in agg["cc_states"].items():
        conn.execute(
            """
            INSERT INTO credit_card_states VALUES (?,?)
            ON CONFLICT(state) DO UPDATE SET complaints=complaints+excluded.complaints
            """,
            (state, c),
        )

    for sub, c in agg["cc_subproducts"].items():
        conn.execute(
            """
            INSERT INTO credit_card_subproducts VALUES (?,?)
            ON CONFLICT(sub_product) DO UPDATE SET complaints=complaints+excluded.complaints
            """,
            (sub, c),
        )

    for (company, month), stats in agg["cc_company_monthly"].items():
        conn.execute(
            """
            INSERT INTO credit_card_company_monthly VALUES (?,?,?,?)
            ON CONFLICT(company, month) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              relief=relief+excluded.relief
            """,
            (company, month, stats["complaints"], stats["relief"]),
        )

    for (issue, month), stats in agg["cc_issue_monthly"].items():
        conn.execute(
            """
            INSERT INTO credit_card_issue_monthly VALUES (?,?,?,?)
            ON CONFLICT(issue, month) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              relief=relief+excluded.relief
            """,
            (issue, month, stats["complaints"], stats["relief"]),
        )

    for (theme, month), stats in agg["cc_theme_monthly"].items():
        conn.execute(
            """
            INSERT INTO credit_card_theme_monthly VALUES (?,?,?,?,?)
            ON CONFLICT(theme, month) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              relief=relief+excluded.relief,
              explanation_only=explanation_only+excluded.explanation_only
            """,
            (theme, month, stats["complaints"], stats["relief"], stats["explanation_only"]),
        )

    for (issue, sub, month), stats in agg["cc_subissue_monthly"].items():
        conn.execute(
            """
            INSERT INTO credit_card_subissue_monthly VALUES (?,?,?,?,?,?)
            ON CONFLICT(issue, sub_issue, month) DO UPDATE SET
              complaints=complaints+excluded.complaints,
              relief=relief+excluded.relief,
              explanation_only=explanation_only+excluded.explanation_only
            """,
            (issue, sub, month, stats["complaints"], stats["relief"], stats["explanation_only"]),
        )


def new_agg() -> dict:
    def counter_dict():
        return defaultdict(int)

    class Stats(dict):
        def __missing__(self, key):
            val = {
                "complaints": 0,
                "with_narrative": 0,
                "timely_yes": 0,
                "monetary_relief": 0,
                "nonmonetary_relief": 0,
                "explanation_only": 0,
                "in_progress": 0,
                "untimely": 0,
                "with_public_response": 0,
            }
            self[key] = val
            return val

    class MonthStats(dict):
        def __missing__(self, key):
            val = {
                "complaints": 0,
                "monetary_relief": 0,
                "nonmonetary_relief": 0,
                "explanation_only": 0,
                "in_progress": 0,
            }
            self[key] = val
            return val

    class MonthlyStats(dict):
        def __missing__(self, key):
            val = {"complaints": 0, "relief": 0}
            self[key] = val
            return val

    class SubissueStats(dict):
        def __missing__(self, key):
            val = {
                "complaints": 0,
                "monetary_relief": 0,
                "nonmonetary_relief": 0,
                "explanation_only": 0,
                "with_narrative": 0,
            }
            self[key] = val
            return val

    class ThemeMonthStats(dict):
        def __missing__(self, key):
            val = {"complaints": 0, "relief": 0, "explanation_only": 0}
            self[key] = val
            return val

    class SubissueMonthStats(dict):
        def __missing__(self, key):
            val = {"complaints": 0, "relief": 0, "explanation_only": 0}
            self[key] = val
            return val

    return {
        "product_stats": Stats(),
        "product_monthly": counter_dict(),
        "response_by_product": counter_dict(),
        "channel_by_product": counter_dict(),
        "cc_issues": Stats(),
        "cc_subissues": SubissueStats(),
        "cc_companies": Stats(),
        "cc_monthly": MonthStats(),
        "cc_issue_response": counter_dict(),
        "cc_states": counter_dict(),
        "cc_subproducts": counter_dict(),
        "cc_company_monthly": MonthlyStats(),
        "cc_issue_monthly": MonthlyStats(),
        "cc_theme_monthly": ThemeMonthStats(),
        "cc_subissue_monthly": SubissueMonthStats(),
    }


def build(csv_path: Path, db_path: Path, period: StudyPeriod | None = None) -> int:
    period = period or load_study_period()
    period.validate()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    init_db(conn)

    print(
        f"  Study window: {period.study_label} "
        f"(early {period.early_label}, recent {period.recent_label})"
    )
    usecols = [
        "Date received",
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "Consumer complaint narrative",
        "Company public response",
        "Company",
        "State",
        "Submitted via",
        "Company response to consumer",
        "Timely response?",
    ]

    total = 0
    agg = new_agg()
    for i, chunk in enumerate(pd.read_csv(csv_path, usecols=usecols, chunksize=CHUNK, low_memory=False)):
        chunk = filter_study_period(chunk, period)
        if chunk.empty:
            continue
        process_chunk(chunk, agg)
        total += len(chunk)
        if (i + 1) % 5 == 0:
            flush_agg(conn, agg)
            conn.commit()
            agg = new_agg()
            print(f"  … {total:,} rows processed")

    flush_agg(conn, agg)
    for key, value in period.to_meta().items():
        conn.execute("INSERT INTO meta VALUES (?, ?)", (key, value))
    conn.execute(
        "INSERT INTO meta VALUES (?, ?)",
        ("built_at", datetime.utcnow().isoformat()),
    )
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("total_complaints", str(total)))
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("source_csv", str(csv_path)))
    conn.commit()
    conn.close()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CFPB summary database for Consumer Harm dashboard")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--study-start", help="Inclusive study start (YYYY-MM-DD), default 2011-01-01")
    parser.add_argument("--study-end", help="Inclusive study end (YYYY-MM-DD), default 2024-12-31")
    parser.add_argument("--early-end", help="End of early comparison period, default 2017-12-31")
    parser.add_argument("--recent-start", help="Start of recent comparison period, default 2018-01-01")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}", file=__import__("sys").stderr)
        raise SystemExit(1)

    period = load_study_period()
    if any([args.study_start, args.study_end, args.early_end, args.recent_start]):
        from period_config import _parse_date

        period = StudyPeriod(
            start=_parse_date(args.study_start or period.start.isoformat()),
            end=_parse_date(args.study_end or period.end.isoformat()),
            early_end=_parse_date(args.early_end or period.early_end.isoformat()),
            recent_start=_parse_date(args.recent_start or period.recent_start.isoformat()),
        )
        period.validate()

    print(f"Building summary from {csv_path} …")
    total = build(csv_path, Path(args.db), period=period)
    print(f"Done: {total:,} complaints in study window → {args.db}")


if __name__ == "__main__":
    main()
