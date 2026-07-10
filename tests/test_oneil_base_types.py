"""Unit tests for shared O'Neil base-pattern candidate helpers."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_base_types import BaseCandidate, prior_uptrend, volume_dry_up


def _frame(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    values = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=len(values)),
            "Open": values,
            "High": values + 0.5,
            "Low": values - 0.5,
            "Close": values,
            "Volume": volumes or [1_000_000.0] * len(values),
        }
    )


@pytest.mark.unit
def test_prior_uptrend_accepts_a_meaningful_advance():
    df = _frame(np.linspace(100.0, 130.0, 121).tolist())

    qualifies, narration = prior_uptrend(df, 120, atr_value=1.0)

    assert qualifies
    assert df.at[0, "Date"].strftime("%Y-%m-%d") in narration


@pytest.mark.unit
def test_prior_uptrend_rejects_a_flat_approach():
    qualifies, _ = prior_uptrend(_frame([100.0] * 121), 120, atr_value=1.0)

    assert not qualifies


@pytest.mark.unit
def test_prior_uptrend_rejects_insufficient_history():
    qualifies, _ = prior_uptrend(_frame([100.0] * 20), 10, atr_value=1.0)

    assert not qualifies


@pytest.mark.unit
def test_volume_dry_up_reports_contraction():
    df = _frame([100.0] * 30, [1_000_000.0] * 20 + [500_000.0] * 10)

    ratio, narration = volume_dry_up(df, 20, 29)

    assert ratio == pytest.approx(0.5)
    assert "contracted" in narration


@pytest.mark.unit
def test_volume_dry_up_without_prior_bars_returns_none():
    ratio, _ = volume_dry_up(_frame([100.0] * 10), 5, 9)

    assert ratio is None


@pytest.mark.unit
def test_base_candidate_geometry_is_json_serializable():
    candidate = BaseCandidate(
        pattern_type="flat_base",
        complete=True,
        pivot_price=125.5,
        pivot_date="2024-06-03",
        complete_index=42,
        geometry={"start_date": "2024-05-01", "depth_pct": 0.08, "levels": [120.0, 125.5]},
        evidence=["A tight range formed."],
    )

    assert json.loads(json.dumps(candidate.geometry)) == candidate.geometry
