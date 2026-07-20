"""Theme for Consumer Harm / Opportunity Harm dashboard."""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

INK = "#0f172a"
CREAM = "#f8fafc"
PAPER = "#f1f5f9"
ACCENT = "#dc2626"
AMBER = "#d97706"
TEAL = "#0d9488"
MUTED = "#64748b"
GRID = "#e2e8f0"

INDUSTRY_COLORS = {
    "Credit card": "#dc2626",
    "Mortgage": "#7c3aed",
    "Bank accounts": "#2563eb",
    "Debt collection": "#ea580c",
    "Student loan": "#0891b2",
    "Auto loan/lease": "#4f46e5",
    "Payday/personal loan": "#be123c",
    "Money transfer/crypto": "#0d9488",
    "Prepaid card": "#9333ea",
}

PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[ACCENT, AMBER, TEAL, "#7c3aed", "#2563eb", "#64748b"],
        margin=dict(l=24, r=24, t=48, b=24),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
)

pio.templates["consumer_harm"] = PLOTLY_TEMPLATE
pio.templates.default = "consumer_harm"

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:ital,wght@0,500;0,600;1,400&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.stApp { background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%); color: #0f172a; }
.main .block-container { color: #0f172a; }
.main .stMarkdown, .main .stMarkdown p, .main .stMarkdown li { color: #0f172a !important; }
.block-container { padding-top: 2rem; max-width: 1100px; }

h1, h2, h3, .story-chapter { font-family: 'IBM Plex Serif', Georgia, serif !important; }

.story-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #f8fafc;
    padding: 3rem 2.5rem;
    border-radius: 6px;
    margin-bottom: 2rem;
    border-left: 6px solid #dc2626;
}
.story-hero h1 { color: #f8fafc !important; font-size: 2.6rem; font-weight: 600; }
.story-hero p { color: #cbd5e1; font-size: 1.1rem; line-height: 1.7; max-width: 760px; }

.story-chapter { font-size: 1.7rem; font-weight: 600; margin: 2rem 0 0.25rem 0; }
.story-lede { font-size: 1.05rem; color: #475569; line-height: 1.65; margin-bottom: 1.25rem; max-width: 780px; }

.story-insight {
    background: #fff;
    border-left: 4px solid #dc2626;
    padding: 1rem 1.25rem;
    margin: 1rem 0 1.5rem 0;
    color: #334155;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06);
}

.story-caveat {
    background: #fff7ed;
    border-left: 4px solid #d97706;
    padding: 1rem 1.25rem;
    margin: 1rem 0;
    color: #9a3412;
    font-size: 0.95rem;
}

.metric-card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 1.2rem 1rem;
    text-align: center;
}
.metric-card .value { font-size: 2rem; font-weight: 700; color: #dc2626; }
.metric-card .label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.3rem; }

div[data-testid="stSidebar"] { background: #0f172a; }
div[data-testid="stSidebar"] .stMarkdown p,
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] span { color: #f8fafc !important; }
</style>
"""


def metric_card_html(value: str, label: str) -> str:
    return f'<div class="metric-card"><div class="value">{value}</div><div class="label">{label}</div></div>'
