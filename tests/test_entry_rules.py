"""Level extraction and position predicates for the entry layer (SP3)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows import entry_rules as r


def _pat(pattern, levels, invalidation=None):
    return SimpleNamespace(pattern=pattern, levels=levels, invalidation_price=invalidation)


def _df(closes, lows=None, vols=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    vols = vols if vols is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.5 for c in closes], "Low": lows,
            "Close": closes, "Volume": vols,
        }
    )


@pytest.mark.unit
def test_extract_levels_double_bottom_uses_twin_low_and_neckline():
    p = _pat("double_bottom", {"first_extreme": 94.4, "second_extreme": 95.4, "neckline": 108.6},
             invalidation=94.16)
    assert r.extract_levels(p, 1.2) == {
        "bottom_boundary": 94.4, "breakout_level": 108.6, "failure_level": 94.16,
    }


@pytest.mark.unit
def test_extract_levels_triangle_failure_is_lower_trendline_minus_buffer():
    p = _pat("ascending_triangle", {"lower_trendline": 95.0, "upper_trendline": 100.0})
    levels = r.extract_levels(p, 1.0)  # buffer = 0.2
    assert levels["bottom_boundary"] == 95.0
    assert levels["breakout_level"] == 100.0
    assert levels["failure_level"] == pytest.approx(94.8)


@pytest.mark.unit
def test_extract_levels_returns_none_for_unknown_pattern():
    assert r.extract_levels(_pat("head_shoulders", {}), 1.0) is None


@pytest.mark.unit
def test_near_within_tolerance():
    assert r.near(96.4, 96.0, 0.5) is True
    assert r.near(97.0, 96.0, 0.5) is False


@pytest.mark.unit
def test_retest_hold_true_on_low_volume_dip_to_boundary():
    closes = [100.0] * 18 + [102.0, 100.2, 101.0]
    lows = [99.5] * 18 + [101.5, 99.8, 100.5]
    vols = [1_000_000.0] * 18 + [1_000_000.0, 300_000.0, 1_000_000.0]
    assert r.retest_hold(_df(closes, lows, vols), 100.0, 0.5, 15) is True


@pytest.mark.unit
def test_retest_hold_false_when_price_below_boundary():
    closes = [100.0] * 18 + [102.0, 100.2, 99.0]
    assert r.retest_hold(_df(closes), 100.0, 0.5, 15) is False


@pytest.mark.unit
def test_retest_hold_false_when_no_low_volume_dip():
    closes = [100.0] * 18 + [102.0, 102.5, 103.0]
    lows = [101.5] * 21
    assert r.retest_hold(_df(closes, lows), 100.0, 0.5, 15) is False
