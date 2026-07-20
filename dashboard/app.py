#!/usr/bin/env python3
"""
Consumer Harm — evolution or the void?

Credit card complaints through the CFPB: are issuers learning,
or do cases disappear into closed-with-explanation?

Run: streamlit run app.py  (port 8502)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_DASH = Path(__file__).resolve().parent
_REPO = _DASH.parent
sys.path.insert(0, str(_DASH))
sys.path.insert(0, str(_REPO))

from harm_themes import THEME_DESCRIPTIONS
from data import (
    compute_issuer_trajectories,
    compute_theme_evolution,
    credit_card_void_snapshot,
    db_available,
    granular_focus_snapshot,
    has_summary_data,
    load_banking_comparison,
    load_credit_card_channels,
    load_credit_card_companies,
    load_credit_card_monthly,
    load_credit_card_responses,
    load_harm_themes,
    load_product_stats,
    load_theme_monthly,
    load_theme_subissues,
    meta,
    period_labels,
    story_headline,
)
from theme import CUSTOM_CSS, INDUSTRY_COLORS, metric_card_html

st.set_page_config(page_title="Consumer Harm", page_icon="⚖️", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

CHAPTERS = [
    "Prologue — Evolution or the Void?",
    "Chapter I — The Arc of Credit Cards",
    "Chapter II — Into the Void",
    "Chapter III — Are Outcomes Changing?",
    "Chapter IV — APR, Denial & Granular Harm",
    "Chapter V — Issuer Patterns",
    "Appendix — Methodology",
]


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="story-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def chapter(title: str, lede: str) -> None:
    st.markdown(f'<div class="story-chapter">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="story-lede">{lede}</div>', unsafe_allow_html=True)


def insight(text: str) -> None:
    st.markdown(f'<div class="story-insight">{text}</div>', unsafe_allow_html=True)


def caveat(text: str) -> None:
    st.markdown(f'<div class="story-caveat">{text}</div>', unsafe_allow_html=True)


def require_data() -> bool:
    if has_summary_data():
        return True
    if db_available():
        st.error(
            "Summary database is present but empty. On Railway, mount a volume at `/data` with "
            "`index/cfpb_summary.db`, or run the refresh job from the repo README."
        )
    else:
        st.warning(
            "No summary database yet. Build it with `python3 scripts/build_cfpb_summary.py` "
            "(see GitHub: tedrubin80/consumer-harm)."
        )
    return False


def render_welcome_rail() -> None:
    """Engaging intro strip — always visible on Railway/Vercel landing."""
    st.markdown(
        """
        <div class="story-hero">
          <h1>Evolution or the Void?</h1>
          <p>Credit card complaints filed with the CFPB either end in relief — or close with
          an explanation and nothing else. This dashboard maps that split across issuers,
          issues, and fixed calendar windows (not rolling trends).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    pl = period_labels() if db_available() else {"study": "2011–2024", "early": "2011–2017", "recent": "2018–2024"}
    c1, c2, c3 = st.columns(3)
    c1.info(f"**Study period:** {pl['study']}")
    c2.info(f"**Early window:** {pl['early']}")
    c3.info(f"**Recent window:** {pl['recent']}")
    st.markdown(
        "Use the **sidebar** to walk the story — Prologue → credit card arc → the void → "
        "whether outcomes change → APR & denial themes → issuer patterns."
    )


def period_banner() -> None:
    if not db_available():
        return
    labels = period_labels()
    st.markdown(
        f'<div class="story-caveat"><strong>Fixed study period:</strong> '
        f'{labels["study"]} · Comparisons: early {labels["early"]} vs recent {labels["recent"]} '
        f'(calendar windows, not rolling).</div>',
        unsafe_allow_html=True,
    )


def render_prologue() -> None:
    chapter(
        "Prologue — The question",
        "In banking, the question is not a watch list — it is whether patterns of harm "
        "evolve or complaints disappear into a bureaucratic void without meaningful remediation.",
    )
    period_banner()
    if require_data():
        h = story_headline()
        early_l, recent_l = h.get("early", "early"), h.get("recent", "recent")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card_html(f"{h.get('relief_pct', 0)}%", "Get relief"), unsafe_allow_html=True)
        c2.markdown(metric_card_html(f"{h.get('void_pct', 0)}%", "Closed — explanation only"), unsafe_allow_html=True)
        c3.markdown(metric_card_html(f"{h.get('relief_trend', 0):+.1f}pp", f"Relief ({early_l}→{recent_l})"), unsafe_allow_html=True)
        c4.markdown(metric_card_html(f"{h.get('void_trend', 0):+.1f}pp", f"Void ({early_l}→{recent_l})"), unsafe_allow_html=True)
        if h.get("relief_trend", 0) > 0 and h.get("void_trend", 0) < 0:
            insight(
                f"In **{recent_l}**, credit card complaints show **more relief and fewer void closures** "
                f"than in **{early_l}** — a signal of evolution, not proof of reform."
            )
        elif h.get("void_trend", 0) > 0:
            insight("The **void is growing** — a larger share of credit card complaints now close with explanation only, without monetary or non-monetary relief.")
        else:
            insight("Outcomes are **flat** — credit card complaints may be handled the same way they were years ago.")


def render_arc() -> None:
    if not require_data():
        return
    chapter(
        "Chapter I — The arc of credit card complaints",
        "Volume and outcomes over time. Is the system processing more harm, and is the "
        "mix of responses changing?",
    )
    monthly = load_credit_card_monthly()
    if monthly.empty:
        st.info("Monthly timeline not in summary yet — rebuild after build completes.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["complaints"], name="Complaints", line=dict(color="#dc2626")))
    fig.update_layout(title=f"Credit card complaints ({period_labels()['study']})", height=360, xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.line(monthly, x="month", y="relief_rate", markers=True, title="Relief rate over time (%)")
        fig.update_layout(height=320, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        if monthly["void_rate"].sum() > 0:
            fig = px.line(monthly, x="month", y="void_rate", markers=True, title="Void rate over time (%)")
            fig.update_layout(height=320, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    banking = load_banking_comparison()
    cc = banking[banking["product"] == "Credit card"]
    if not cc.empty:
        row = cc.iloc[0]
        insight(
            f"Among banking products, credit cards show a **{row['relief_rate']}% relief rate** "
            f"and **{row['void_rate']}% explanation-only** closure rate — compare to mortgage "
            f"({banking[banking['product']=='Mortgage']['void_rate'].values[0] if len(banking[banking['product']=='Mortgage']) else '?'}% void) "
            "in the banking comparison (Appendix)."
        )


def render_void() -> None:
    if not require_data():
        return
    chapter(
        "Chapter II — Into the void",
        "The void is where a complaint is acknowledged, closed with an explanation, "
        "and leaves no trace of remediation. Relief — monetary or not — is the opposite signal.",
    )
    responses = load_credit_card_responses()
    void = credit_card_void_snapshot()
    pl = period_labels()

    st.markdown(
        f"""
**Credit card outcomes ({pl['study']}):**
- **{void.get('relief_pct', 0)}%** → monetary or non-monetary relief
- **{void.get('void_pct', 0)}%** → closed with explanation only *(the void)*
- **{void.get('in_progress_pct', 0)}%** → still in progress
- **{void.get('narrative_pct', 0)}%** → consumer published their story publicly
        """
    )

    color_map = {
        "Closed with explanation": "#94a3b8",
        "Closed with monetary relief": "#16a34a",
        "Closed with non-monetary relief": "#0d9488",
        "In progress": "#fbbf24",
        "Untimely response": "#dc2626",
    }
    fig = px.bar(
        responses,
        x="count",
        y="response",
        orientation="h",
        color="response",
        color_discrete_map=color_map,
        title="Where credit card complaints end up",
    )
    fig.update_layout(height=380, showlegend=False, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

    channels = load_credit_card_channels()
    fig2 = px.pie(channels, names="channel", values="count", hole=0.45, title="How consumers enter the pipeline")
    st.plotly_chart(fig2, use_container_width=True)

    caveat(
        "A closed file is not proof nothing happened — but **explanation-only** is the "
        "strongest observable signal that the consumer did not receive relief through this channel."
    )


def render_changing() -> None:
    if not require_data():
        return
    chapter(
        "Chapter III — Are outcomes changing?",
        f"Compare **{period_labels()['early']}** to **{period_labels()['recent']}** — fixed calendar "
        "windows, not a rolling last-N-months view. Learning would look like rising relief rates; "
        "stagnation looks like a steady void.",
    )
    h = story_headline()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**{h.get('early', 'Early')} (avg monthly relief/void)**")
        st.markdown(f"- Relief rate: **{h.get('early_relief_rate', '—')}%**")
        st.markdown(f"- Void rate: **{h.get('early_void_rate', '—')}%**")
    with col2:
        st.markdown(f"**{h.get('recent', 'Recent')} (avg monthly relief/void)**")
        st.markdown(f"- Relief rate: **{h.get('recent_relief_rate', '—')}%**")
        st.markdown(f"- Void rate: **{h.get('recent_void_rate', '—')}%**")

    fig = go.Figure(
        data=[
            go.Bar(name=h.get("early", "Early"), x=["Relief rate", "Void rate"], y=[h.get("early_relief_rate", 0), h.get("early_void_rate", 0)], marker_color="#64748b"),
            go.Bar(name=h.get("recent", "Recent"), x=["Relief rate", "Void rate"], y=[h.get("recent_relief_rate", 0), h.get("recent_void_rate", 0)], marker_color="#dc2626"),
        ]
    )
    fig.update_layout(
        barmode="group",
        title=f"Outcomes: {h.get('early', 'early')} vs {h.get('recent', 'recent')}",
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

    trajectories = compute_issuer_trajectories()
    if not trajectories.empty:
        st.markdown("**Issuer-level signals** (fixed early vs recent windows)")
        st.dataframe(
            trajectories[["company", "early_relief_rate", "recent_relief_rate", "relief_change_pts", "signal"]],
            use_container_width=True,
            hide_index=True,
        )


def render_granular_harm() -> None:
    if not require_data():
        return
    chapter(
        "Chapter IV — APR, denial, and granular harm",
        "Beyond headline volume: **interest rate fights**, **application denials**, **fee disputes**, "
        "and **credit access** — each with its own volume and void rate. "
        "Does the system evolve differently depending on the type of harm?",
    )

    themes = load_harm_themes()
    focus = granular_focus_snapshot()
    if themes.empty:
        st.info("Rebuild summary for theme-level void rates: `python3 ~/datascience/projects/build_cfpb_summary.py`")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        metric_card_html(f"{focus.get('apr_void_rate', '—')}%", "APR & interest → void"),
        unsafe_allow_html=True,
    )
    c2.markdown(
        metric_card_html(f"{focus.get('denial_void_rate', '—')}%", "Denial & access → void"),
        unsafe_allow_html=True,
    )
    c3.markdown(
        metric_card_html(f"{focus.get('apr_complaints', 0):,}", "APR-related complaints"),
        unsafe_allow_html=True,
    )
    c4.markdown(
        metric_card_html(f"{focus.get('denial_complaints', 0):,}", "Denial-related complaints"),
        unsafe_allow_html=True,
    )

    fig = px.bar(
        themes,
        x="void_rate",
        y="theme",
        orientation="h",
        color="relief_rate",
        color_continuous_scale=["#dc2626", "#94a3b8", "#16a34a"],
        title="Void rate by harm theme (color = relief rate)",
        labels={"void_rate": "Explanation-only %", "relief_rate": "Relief %"},
        hover_data={"complaints": True, "narrative_rate": True},
    )
    fig.update_layout(height=380, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

    tm = load_theme_monthly()
    if not tm.empty:
        top_themes = themes.nlargest(4, "complaints")["theme"].tolist()
        plot_df = tm[tm["theme"].isin(top_themes)]
        fig2 = px.line(
            plot_df,
            x="month",
            y="complaints",
            color="theme",
            markers=False,
            title="Complaint volume over time — top harm themes",
        )
        fig2.update_layout(height=340, xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig2, use_container_width=True)

        fig3 = px.line(
            plot_df,
            x="month",
            y="void_rate",
            color="theme",
            markers=False,
            title="Void rate over time — are APR/denial outcomes changing?",
        )
        fig3.update_layout(height=340, xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig3, use_container_width=True)

    evo = compute_theme_evolution()
    if not evo.empty:
        st.markdown("**Early vs recent — theme outcomes**")
        st.dataframe(
            evo[
                [
                    "theme",
                    "early_volume",
                    "recent_volume",
                    "volume_change_pct",
                    "early_void_rate",
                    "recent_void_rate",
                    "void_change_pts",
                    "relief_change_pts",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    col1, col2 = st.columns(2)
    for col, theme in [(col1, "APR & interest"), (col2, "Denial & access")]:
        with col:
            st.markdown(f"**{theme}** — sub-issues")
            st.caption(THEME_DESCRIPTIONS.get(theme, ""))
            subs = load_theme_subissues(theme).head(8)[
                ["issue", "sub_issue", "complaints", "void_rate", "relief_rate"]
            ]
            if not subs.empty:
                st.dataframe(subs, use_container_width=True, hide_index=True)

    apr_void = focus.get("apr_void_trend")
    denial_void = focus.get("denial_void_trend")
    if apr_void is not None and denial_void is not None:
        if denial_void > 2 and apr_void <= 0:
            insight(
                "**Denial complaints** are drifting deeper into the void while **APR disputes** hold steady — "
                "access harm may be harder to resolve through this channel than rate disputes."
            )
        elif apr_void > 2:
            insight(
                "**APR & interest** void rate is rising — rate disputes increasingly close with explanation only."
            )
        else:
            insight(
                "Theme-level void rates are relatively stable — evolution, if any, may be issuer-specific rather than issue-specific."
            )


def render_shifting_harm() -> None:
    render_granular_harm()


def render_issuers() -> None:
    if not require_data():
        return
    chapter(
        "Chapter V — Do issuers learn?",
        "Top issuers by complaint volume — relief rate vs. void rate. "
        "High volume with low relief is harm surfacing into the void.",
    )
    companies = load_credit_card_companies().head(15)
    fig = px.scatter(
        companies,
        x="void_rate",
        y="relief_rate",
        size="complaints",
        hover_name="company",
        title="Issuers: void rate vs. relief rate (size = volume)",
        labels={"void_rate": "Explanation-only %", "relief_rate": "Relief %"},
    )
    fig.add_hline(y=companies["relief_rate"].median(), line_dash="dot", line_color="#64748b")
    fig.add_vline(x=companies["void_rate"].median(), line_dash="dot", line_color="#64748b")
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)

    insight(
        "Issuers in the **upper-left** (high relief, low void) handle complaints differently "
        "than those in the **lower-right**. That gap is the story — not a regulatory list, "
        "but a spread of whether feedback produces change."
    )


def render_methodology() -> None:
    chapter("Appendix", "Definitions and limits.")
    m = meta()
    pl = period_labels()
    st.markdown(
        f"""
**Source:** [CFPB Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/)  
**Built:** {m.get('built_at', 'pending')} · **Rows in study window:** {m.get('total_complaints', '—')}

**Study period:** {pl['study']} (complaints with Date received in this range only)  
**Early comparison:** {pl['early']} · **Recent comparison:** {pl['recent']}

| Term | Meaning |
|------|---------|
| **Relief** | Closed with monetary or non-monetary relief |
| **APR & interest** | Rate increases, overcharges, APR disputes |
| **Denial & access** | Application denied, credit determination, processing delays |
| **The void** | Closed with explanation only — no relief recorded |
| **Evolution** | Rising relief or falling void rates from early to recent **fixed** windows |
| **Learning** | Interpretive — inferred from outcome trends, not confirmed reform |

**What this data cannot show:** enforcement actions, class actions, internal policy changes, 
or whether consumers stopped complaining because problems were fixed vs. because they gave up.

```bash
# Fixed windows (defaults: study 2011–2024, early through 2017, recent from 2018)
export CFPB_STUDY_START=2011-01-01
export CFPB_STUDY_END=2024-12-31
export CFPB_EARLY_END=2017-12-31
export CFPB_RECENT_START=2018-01-01
python3 scripts/build_cfpb_summary.py
docker compose up -d dashboard
```
        """
    )
    repo = os.environ.get("GITHUB_REPO", "https://github.com/tedrubin80/consumer-harm")
    st.markdown(f"**Source code:** [{repo}]({repo})")


def main() -> None:
    with st.sidebar:
        st.markdown("### Consumer Harm")
        pick = st.radio("Story", CHAPTERS, label_visibility="collapsed")
        if db_available():
            pl = period_labels()
            st.caption(f"Study: {pl['study']}")
            v = credit_card_void_snapshot()
            st.markdown(f"**{v.get('total', 0):,}** credit card complaints")
            st.caption(f"{v.get('void_pct', 0)}% into the void")
        repo = os.environ.get("GITHUB_REPO", "https://github.com/tedrubin80/consumer-harm")
        st.markdown(f"[GitHub]({repo})")

    routes = {
        "Prologue": render_prologue,
        "Chapter I": render_arc,
        "Chapter II": render_void,
        "Chapter III": render_changing,
        "Chapter IV": render_shifting_harm,
        "Chapter V": render_issuers,
        "Appendix": render_methodology,
    }
    for prefix, fn in routes.items():
        if pick.startswith(prefix):
            if pick.startswith("Prologue"):
                render_welcome_rail()
            fn()
            break


if __name__ == "__main__":
    main()
