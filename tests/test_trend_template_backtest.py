"""Unit tests for the trend-template walk-forward hit-rate report logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.trend_template_backtest import (
    WARMUP_BARS,
    aggregate,
    collect_readings,
    format_report,
    new_stats,
    pass_band,
    rs_band,
)


def _frame(closes) -> pd.DataFrame:
    prices = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": 1_000_000.0,
    })


def _strong() -> pd.DataFrame:
    return _frame(np.linspace(100.0, 220.0, 320))


def _flat_benchmark() -> pd.DataFrame:
    return _frame(np.full(320, 100.0))


@pytest.mark.unit
def test_pass_band_edges():
    assert pass_band(0) == "0-4"
    assert pass_band(4) == "0-4"
    assert pass_band(5) == "5-6"
    assert pass_band(6) == "5-6"
    assert pass_band(7) == "7"
    assert pass_band(8) == "8"


@pytest.mark.unit
def test_rs_band_edges():
    assert rs_band(-0.001) == "rs<0"
    assert rs_band(0.0) == "0<=rs<=0.10"
    assert rs_band(0.10) == "0<=rs<=0.10"
    assert rs_band(0.101) == "rs>0.10"
    assert rs_band(None) == "n/a"


@pytest.mark.unit
def test_collect_samples_strong_uptrend_as_stage_2():
    records = collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=20)
    assert records, "expected records past the warm-up"
    first = records[0]
    assert first["passed_count"] == 8
    assert first["stage_2_uptrend"] is True
    assert first["rs_score"] > 0.10
    assert first["forward_return"] == pytest.approx(0.038, abs=0.005)
    assert first["hit"] is True
    # warm-up respected: first sampled date is at/after bar WARMUP_BARS
    assert first["date"] >= _strong()["Date"].iloc[WARMUP_BARS].strftime("%Y-%m-%d")


@pytest.mark.unit
def test_no_records_without_full_forward_window():
    # holding window longer than the bars remaining after warm-up
    assert collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=80) == []


@pytest.mark.unit
def test_aggregate_routes_bands_and_none_rs():
    records = [
        {"date": "2025-01-02", "passed_count": 8, "total_criteria": 8,
         "stage_2_uptrend": True, "rs_score": 0.15, "forward_return": 0.04, "hit": True},
        {"date": "2025-02-03", "passed_count": 5, "total_criteria": 8,
         "stage_2_uptrend": False, "rs_score": None, "forward_return": -0.01, "hit": False},
    ]
    stats = new_stats()
    aggregate(records, stats)
    assert stats["baseline"]["8"]["hits"] == 1
    assert stats["baseline"]["5-6"]["count"] == 1
    assert stats["lift"][("8", "rs>0.10")]["count"] == 1
    assert stats["lift"][("5-6", "n/a")]["count"] == 1
    assert ("5-6", "rs<0") not in stats["lift"]


@pytest.mark.unit
def test_end_to_end_report_contains_expected_rows():
    records = collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=20)
    stats = new_stats()
    aggregate(records, stats)
    report = format_report(stats)
    assert "pass_band" in report and "rs_band" in report
    assert "rs>0.10" in report
    assert "100.0%" in report  # every strong-uptrend sample is a hit
