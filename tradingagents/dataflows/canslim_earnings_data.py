"""Typed, point-in-time-filtered earnings history for the CANSLIM C+A scorer."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.alpha_vantage_fundamentals import get_earnings as get_av_earnings
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.symbol_utils import NoMarketDataError, normalize_symbol

ANNUAL_REPORT_LAG_DAYS = 90


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


def load_earnings_history(symbol: str, curr_date: str, config: dict | None = None) -> EarningsHistory:
    """Load point-in-time quarterly/annual EPS via the configured fundamental_data vendor."""
    vendor = (config or get_config()).get("data_vendors", {}).get("fundamental_data")
    canonical = normalize_symbol(symbol)
    if vendor == "yfinance":
        return _load_yfinance(symbol, canonical, curr_date)
    if vendor == "alpha_vantage":
        return _load_alpha_vantage(symbol, canonical, curr_date)
    raise ValueError(
        f"CANSLIM earnings history has no adapter for fundamental_data vendor {vendor!r}"
    )


def _load_yfinance(symbol: str, canonical: str, curr_date: str) -> EarningsHistory:
    ticker = yf.Ticker(canonical)
    frame = yf_retry(lambda: ticker.get_earnings_dates(limit=28))
    if frame is None or frame.empty:
        raise NoMarketDataError(symbol, canonical, "no earnings dates returned")
    cutoff = pd.Timestamp(curr_date)
    quarters = []
    for stamp, row in frame.iterrows():
        reported = pd.Timestamp(stamp).tz_localize(None).normalize()
        eps = row.get("Reported EPS")
        if pd.isna(eps) or reported > cutoff:
            continue
        quarters.append(QuarterEps(None, reported.strftime("%Y-%m-%d"), float(eps)))
    quarters.sort(key=lambda q: q.reported_date, reverse=True)
    annual = []
    income = yf_retry(lambda: ticker.income_stmt)
    if income is not None and not income.empty and "Diluted EPS" in income.index:
        for column, value in income.loc["Diluted EPS"].items():
            fiscal_end = pd.Timestamp(column)
            # yfinance annual statements carry no report date; approximate the
            # 10-K filing window so a just-ended fiscal year is not leaked.
            if pd.isna(value) or fiscal_end + pd.Timedelta(days=ANNUAL_REPORT_LAG_DAYS) > cutoff:
                continue
            annual.append(AnnualEps(fiscal_end.strftime("%Y-%m-%d"), float(value)))
    annual.sort(key=lambda item: item.fiscal_year, reverse=True)
    return EarningsHistory(quarters=quarters, annual=annual)


def _load_alpha_vantage(symbol: str, canonical: str, curr_date: str) -> EarningsHistory:
    data = get_av_earnings(canonical)
    if not isinstance(data, dict) or "quarterlyEarnings" not in data:
        raise NoMarketDataError(symbol, canonical, "no EARNINGS payload returned")
    quarters = []
    for entry in data.get("quarterlyEarnings", []):
        reported = entry.get("reportedDate") or ""
        if not reported or reported > curr_date:
            continue
        try:
            eps = float(entry.get("reportedEPS"))
        except (TypeError, ValueError):
            continue
        quarters.append(QuarterEps(entry.get("fiscalDateEnding"), reported, eps))
    quarters.sort(key=lambda q: q.reported_date, reverse=True)
    covered = {q.fiscal_end for q in quarters if q.fiscal_end}
    annual = []
    for entry in data.get("annualEarnings", []):
        fiscal_year = entry.get("fiscalDateEnding") or ""
        try:
            eps = float(entry.get("reportedEPS"))
        except (TypeError, ValueError):
            continue
        # An annual figure is public only once its Q4/FY report has landed:
        # require a reported quarter whose fiscal end is at/after this year end.
        if fiscal_year and any(end >= fiscal_year for end in covered):
            annual.append(AnnualEps(fiscal_year, eps))
    annual.sort(key=lambda item: item.fiscal_year, reverse=True)
    return EarningsHistory(quarters=quarters, annual=annual)
