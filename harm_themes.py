"""Map CFPB credit-card issue/sub-issue pairs to harm themes for granular analysis."""

from __future__ import annotations

import math

THEME_ORDER: list[str] = [
    "APR & interest",
    "Denial & access",
    "Fees",
    "Credit limits",
    "Unauthorized card opening",
    "Billing & disputes",
]

THEME_DESCRIPTIONS: dict[str, str] = {
    "APR & interest": "Rate increases, interest charges, APR disputes",
    "Denial & access": "Application denied, credit determination, processing delays",
    "Fees": "Late fees, overlimit, cash advance, and other fee disputes",
    "Credit limits": "Limit increases/decreases refused or mishandled",
    "Unauthorized card opening": "Cards opened without consent or via identity theft",
    "Billing & disputes": "Statement errors, purchase disputes, billing fights",
}

# Sub-issue matches take precedence when listed here.
_SUBISSUE_THEME: dict[str, str] = {
    "Application denied": "Denial & access",
    "Delay in processing application": "Denial & access",
    "Charged too much interest": "APR & interest",
    "Unexpected increase in interest rate": "APR & interest",
    "Problem with fees": "Fees",
    "Card opened without my consent or knowledge": "Unauthorized card opening",
    "Card opened as result of identity theft or fraud": "Unauthorized card opening",
    "Sent card you never applied for": "Unauthorized card opening",
    "Credit card company won't increase or decrease your credit limit": "Credit limits",
    "Credit card company isn't resolving a dispute about a purchase on your statement": "Billing & disputes",
    "Card was charged for something you did not purchase with the card": "Billing & disputes",
}

_ISSUE_THEME: dict[str, str] = {
    "APR or interest rate": "APR & interest",
    "Credit determination": "Denial & access",
    "Application processing delay": "Denial & access",
    "Problem getting a card or closing an account": "Denial & access",
    "Late fee": "Fees",
    "Unexpected or other fees": "Fees",
    "Other fee": "Fees",
    "Overlimit fee": "Fees",
    "Balance transfer fee": "Fees",
    "Cash advance fee": "Fees",
    "Credit line increase/decrease": "Credit limits",
    "Billing disputes": "Billing & disputes",
    "Problem with a purchase shown on your statement": "Billing & disputes",
}


def _norm_text(value: object) -> str:
    """Coerce CFPB/pandas values (None, NaN, empty) to a clean string."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def classify_harm_theme(issue: str | None, sub_issue: str | None) -> str | None:
    sub = _norm_text(sub_issue) or "(none)"
    iss = _norm_text(issue)
    if sub in _SUBISSUE_THEME:
        return _SUBISSUE_THEME[sub]
    if iss in _ISSUE_THEME:
        return _ISSUE_THEME[iss]
    if iss == "Getting a credit card" and sub in {
        "Problem getting a working replacement card",
        "Trouble getting, activating, or registering a card",
    }:
        return "Denial & access"
    if iss == "Fees or interest" and sub == "(none)":
        return "Fees"
    return None


def theme_for_display(theme: str) -> str:
    return theme
