"""Typed, point-in-time-filtered earnings history for the CANSLIM C+A scorer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuarterEps:
    """One reported quarter. ``fiscal_end`` is None when the vendor lacks it (yfinance)."""

    fiscal_end: str | None
    reported_date: str
    eps: float


@dataclass(frozen=True)
class AnnualEps:
    fiscal_year: str
    eps: float


@dataclass(frozen=True)
class EarningsHistory:
    """Quarterly and annual EPS series, both newest-first, already curr_date-filtered."""

    quarters: list[QuarterEps]
    annual: list[AnnualEps]
