"""Unit tests for the pocket pivot walk-forward hit-rate report logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_backtest import (
    aggregate,
    collect_events,
    format_report,
    new_stats,
)


def _fixture(total: int = 140, pivot_at: int = 100) -> pd.DataFrame:
    closes: list[float] = []
    vols: list[float] = []
    for i in range(total):
        if i < pivot_at - 6:
            base = 100.0 + 0.05 * i
            if i % 5 == 2:
                closes.append(base - 0.4)
                vols.append(1_200_000.0)
            else:
                closes.append(base)
                vols.append(1_000_000.0)
        elif i < pivot_at:
            closes.append(closes[-1] - 0.35)
            vols.append(700_000.0)
        elif i == pivot_at:
            closes.append(closes[-1] + 2.5)
            vols.append(1_500_000.0)
        else:
            closes.append(closes[-1] + 0.15)
            vols.append(1_000_000.0)
    prices = np.asarray(closes)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=total),
        "Open": prices - 0.1,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": vols,
    })


@pytest.mark.unit
def test_dedupe_keeps_one_record_per_event_and_ma_period():
    records = collect_events(_fixture(), step=5, holding_days=20)
    assert [(r["date"], r["ma_period"]) for r in records] == [
        ("2024-05-21", 10), ("2024-05-21", 50),
    ]


@pytest.mark.unit
def test_forward_return_anchored_to_event_date():
    records = collect_events(_fixture(), step=5, holding_days=20)
    assert records[0]["forward_return"] == pytest.approx(0.0286, abs=0.001)
    assert records[0]["hit"] is True


@pytest.mark.unit
def test_event_without_full_forward_window_is_dropped():
    assert collect_events(_fixture(), step=5, holding_days=50) == []


@pytest.mark.unit
def test_flag_lift_none_never_counts_as_false():
    records = [
        {"date": "2024-01-10", "ma_period": 10, "gap_up": True,
         "context": {"v_shape_risk": True, "extended_from_ma": None,
                     "multi_month_downtrend": False, "above_sma200": None},
         "forward_return": 0.05, "hit": True},
        {"date": "2024-02-10", "ma_period": 50, "gap_up": False,
         "context": {"v_shape_risk": False, "extended_from_ma": None,
                     "multi_month_downtrend": None, "above_sma200": True},
         "forward_return": -0.02, "hit": False},
    ]
    stats = new_stats()
    aggregate(records, stats)
    assert stats["flags"][("v_shape_risk", True)]["count"] == 1
    assert stats["flags"][("v_shape_risk", False)]["count"] == 1
    assert stats["flags"][("extended_from_ma", None)]["count"] == 2
    assert ("extended_from_ma", False) not in stats["flags"]
    assert stats["flags"][("gap_up", True)]["count"] == 1
    assert stats["baseline"][10]["hits"] == 1
    assert stats["baseline"][50]["hits"] == 0


@pytest.mark.unit
def test_end_to_end_report_contains_expected_buckets():
    records = collect_events(_fixture(), step=5, holding_days=20)
    stats = new_stats()
    aggregate(records, stats)
    report = format_report(stats)
    assert "ma_period" in report and "flag" in report
    assert "v_shape_risk" in report and "gap_up" in report
    # one 10dma event, hit: baseline row shows 100.0%
    assert "100.0%" in report
