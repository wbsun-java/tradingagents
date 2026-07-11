"""Unit tests for CANSLIM earnings-history loading and point-in-time filtering."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.canslim_earnings_data as ced
from tradingagents.dataflows.canslim_earnings_data import load_earnings_history


def _yf_config():
    return {"data_vendors": {"fundamental_data": "yfinance"}}


def _av_config():
    return {"data_vendors": {"fundamental_data": "alpha_vantage"}}


class _StubTicker:
    """Mimics the empirically verified yfinance shapes (tz-aware earnings index)."""

    def __init__(self, symbol):
        index = pd.DatetimeIndex(
            ["2026-07-30 16:00", "2026-04-30 16:00", "2026-01-29 16:00", "2025-10-30 16:00"],
            tz="America/New_York", name="Earnings Date",
        )
        self._earnings = pd.DataFrame(
            {"EPS Estimate": [1.89, 1.94, 2.67, 1.77],
             "Reported EPS": [float("nan"), 2.01, 2.84, 1.85],
             "Surprise(%)": [float("nan"), 3.46, 6.25, 4.52]},
            index=index,
        )
        self.income_stmt = pd.DataFrame(
            {pd.Timestamp("2025-09-30"): [7.46], pd.Timestamp("2024-09-30"): [6.08],
             pd.Timestamp("2023-09-30"): [6.13], pd.Timestamp("2022-09-30"): [float("nan")]},
            index=["Diluted EPS"],
        )

    def get_earnings_dates(self, limit=28):
        return self._earnings


@pytest.mark.unit
def test_yfinance_drops_future_and_nan_quarters(monkeypatch):
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    history = load_earnings_history("AAPL", "2026-05-15", config=_yf_config())
    assert [q.eps for q in history.quarters] == [2.01, 2.84, 1.85]
    assert history.quarters[0].reported_date == "2026-04-30"
    assert history.quarters[0].fiscal_end is None


@pytest.mark.unit
def test_yfinance_report_date_gate_excludes_recent_quarter(monkeypatch):
    # 2026-04-30 report excluded at curr_date 2026-04-10 even though Q ended in March
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    history = load_earnings_history("AAPL", "2026-04-10", config=_yf_config())
    assert [q.eps for q in history.quarters] == [2.84, 1.85]


@pytest.mark.unit
def test_yfinance_annual_gated_by_90_day_window_and_nan_dropped(monkeypatch):
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    # 2025-09-30 fiscal end + 90d = 2025-12-29 <= curr_date, so 3 usable years (2022 NaN)
    history = load_earnings_history("AAPL", "2026-05-15", config=_yf_config())
    assert [a.eps for a in history.annual] == [7.46, 6.08, 6.13]
    # at 2025-11-01 the FY2025 10-K window has not elapsed
    history = load_earnings_history("AAPL", "2025-11-01", config=_yf_config())
    assert [a.eps for a in history.annual] == [6.08, 6.13]


@pytest.mark.unit
def test_alpha_vantage_reported_date_gate(monkeypatch):
    payload = {
        "symbol": "TEST",
        "quarterlyEarnings": [
            {"fiscalDateEnding": "2026-03-31", "reportedDate": "2026-04-25", "reportedEPS": "2.10"},
            {"fiscalDateEnding": "2025-12-31", "reportedDate": "2026-01-28", "reportedEPS": "2.80"},
            {"fiscalDateEnding": "2025-09-30", "reportedDate": "2025-10-30", "reportedEPS": "1.90"},
            {"fiscalDateEnding": "2025-06-30", "reportedDate": "2025-07-31", "reportedEPS": "1.60"},
        ],
        "annualEarnings": [
            {"fiscalDateEnding": "2025-09-30", "reportedEPS": "7.40"},
            {"fiscalDateEnding": "2024-09-30", "reportedEPS": "6.10"},
        ],
    }
    monkeypatch.setattr(ced, "get_av_earnings", lambda symbol: payload)
    # THE leakage case: fiscal period ended 2026-03-31, before curr_date 2026-04-10,
    # but the report landed 2026-04-25 — it must be excluded.
    history = load_earnings_history("TEST", "2026-04-10", config=_av_config())
    assert [q.eps for q in history.quarters] == [2.80, 1.90, 1.60]
    assert history.quarters[0].fiscal_end == "2025-12-31"
    # annual FY2025 usable: a quarterly report with fiscal_end >= 2025-09-30 has landed
    assert [a.eps for a in history.annual] == [7.40, 6.10]


@pytest.mark.unit
def test_alpha_vantage_annual_needs_covering_quarterly_report(monkeypatch):
    payload = {
        "symbol": "TEST",
        "quarterlyEarnings": [
            {"fiscalDateEnding": "2025-06-30", "reportedDate": "2025-07-31", "reportedEPS": "1.60"},
        ],
        "annualEarnings": [
            {"fiscalDateEnding": "2025-09-30", "reportedEPS": "7.40"},
            {"fiscalDateEnding": "2024-09-30", "reportedEPS": "6.10"},
        ],
    }
    monkeypatch.setattr(ced, "get_av_earnings", lambda symbol: payload)
    history = load_earnings_history("TEST", "2025-08-15", config=_av_config())
    # FY2025 not yet covered by any quarterly report at/after its fiscal end
    assert [a.eps for a in history.annual] == [6.10]


@pytest.mark.unit
def test_unsupported_vendor_raises_value_error():
    with pytest.raises(ValueError, match="local_csv"):
        load_earnings_history(
            "TEST", "2026-05-15", config={"data_vendors": {"fundamental_data": "local_csv"}}
        )


@pytest.mark.integration
def test_yfinance_live_history_shape():
    history = load_earnings_history("AAPL", "2026-07-01", config=_yf_config())
    assert len(history.quarters) >= 5
    assert len(history.annual) >= 3
    assert all(q.reported_date <= "2026-07-01" for q in history.quarters)
