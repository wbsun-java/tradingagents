"""Emerging double-bottom detection (SP3b)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.double_bottom_emerging import find_emerging_double_bottom


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:], strict=False):
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _df(anchors):
    closes = _interp(anchors)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.8 for c in closes], "Low": [c - 0.8 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )


def _first_bottom():
    return [SimpleNamespace(kind="low", index=8, price=95.0, date="2026-01-13")]


_ANCHORS = [(0, 100), (8, 95.8), (18, 108.8), (35, 96.2), (39, 98)]


@pytest.mark.unit
def test_emerging_double_bottom_is_detected():
    pattern = find_emerging_double_bottom(_df(_ANCHORS), _first_bottom(), 1.5, 3)
    assert pattern is not None
    assert pattern.pattern == "double_bottom"
    assert pattern.status == "emerging"
    assert pattern.direction == "bullish"
    assert pattern.confidence == 0.4
    assert pattern.levels["first_extreme"] == pytest.approx(95.0)
    assert pattern.levels["second_extreme"] == pytest.approx(95.4)
    assert pattern.levels["breakout_price"] is None
    assert pattern.target_price > pattern.levels["neckline"]


@pytest.mark.unit
def test_no_turn_up_yields_none():
    pattern = find_emerging_double_bottom(
        _df([(0, 100), (8, 95.8), (18, 108.8), (35, 96.2), (39, 95.6)]), _first_bottom(), 1.5, 3
    )
    assert pattern is None


@pytest.mark.unit
def test_deep_undercut_yields_none():
    # candidate low crashes well below the first bottom -> a breakdown, not a double
    pattern = find_emerging_double_bottom(
        _df([(0, 100), (8, 95.8), (18, 108.8), (35, 89.0), (39, 92.0)]), _first_bottom(), 1.5, 3
    )
    assert pattern is None


@pytest.mark.unit
def test_no_matching_first_bottom_yields_none():
    pivots = [SimpleNamespace(kind="low", index=8, price=80.0, date="2026-01-13")]
    assert find_emerging_double_bottom(_df(_ANCHORS), pivots, 1.5, 3) is None
