"""Fixed CFPB study windows — not rolling relative to latest data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime


def _parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


@dataclass(frozen=True)
class StudyPeriod:
    """Inclusive calendar bounds for complaints and comparisons."""

    start: date
    end: date
    early_end: date
    recent_start: date

    def validate(self) -> None:
        if self.start > self.end:
            raise ValueError("study start must be on or before study end")
        if self.start > self.early_end or self.early_end > self.end:
            raise ValueError("early_end must fall within the study window")
        if self.recent_start > self.end or self.recent_start <= self.early_end:
            raise ValueError("recent_start must be after early_end and within study end")

    @property
    def study_label(self) -> str:
        return f"{self.start.year}–{self.end.year}"

    @property
    def early_label(self) -> str:
        return f"{self.start.year}–{self.early_end.year}"

    @property
    def recent_label(self) -> str:
        return f"{self.recent_start.year}–{self.end.year}"

    def to_meta(self) -> dict[str, str]:
        return {
            "study_start": self.start.isoformat(),
            "study_end": self.end.isoformat(),
            "early_end": self.early_end.isoformat(),
            "recent_start": self.recent_start.isoformat(),
            "study_label": self.study_label,
            "early_label": self.early_label,
            "recent_label": self.recent_label,
            "period_mode": "fixed_calendar",
        }

    @classmethod
    def from_meta(cls, meta: dict[str, str]) -> StudyPeriod | None:
        if not meta.get("study_start") or not meta.get("study_end"):
            return None
        return cls(
            start=_parse_date(meta["study_start"]),
            end=_parse_date(meta["study_end"]),
            early_end=_parse_date(meta.get("early_end") or meta["study_end"]),
            recent_start=_parse_date(meta.get("recent_start") or meta["study_start"]),
        )


def load_study_period() -> StudyPeriod:
    period = StudyPeriod(
        start=_parse_date(os.environ.get("CFPB_STUDY_START", "2011-01-01")),
        end=_parse_date(os.environ.get("CFPB_STUDY_END", "2024-12-31")),
        early_end=_parse_date(os.environ.get("CFPB_EARLY_END", "2017-12-31")),
        recent_start=_parse_date(os.environ.get("CFPB_RECENT_START", "2018-01-01")),
    )
    period.validate()
    return period


def month_in_range(month: str, start: date, end: date) -> bool:
    if not month or month == "unknown":
        return False
    start_ym = start.strftime("%Y-%m")
    end_ym = end.strftime("%Y-%m")
    return start_ym <= month <= end_ym
