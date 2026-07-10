"""Unit tests for the O'Neil flat-base detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr
from tradingagents.dataflows.oneil_flat_base import detect_flat_base


def _flat_base(tight_days: int = 30, ramp_gain: float = 30.0, depth: float = 0.02) -> pd.DataFrame:
    ramp = np.linspace(100.0, 100.0 + ramp_gain, 60)
    center = ramp[-1]
    angles = np.linspace(0, 6 * np.pi, tight_days)
    tight = center * (1 + depth * np.sin(angles))
    closes = np.concatenate((ramp, tight))
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=len(closes)),
            "Open": closes,
            "High": closes + 0.5,
            "Low": closes - 0.5,
            "Close": closes,
            "Volume": 1_000_000.0,
        }
    )


def _detected(df: pd.DataFrame):
    return detect_flat_base(df, float(atr(df).iloc[-1]))


@pytest.mark.unit
def test_textbook_flat_base_detected():
    df = _flat_base()
    candidate = _detected(df)

    assert candidate is not None
    assert candidate.complete is True
    assert candidate.pattern_type == "flat_base"
    assert candidate.pivot_price == pytest.approx(df["High"].iloc[60:].max())


@pytest.mark.unit
def test_short_tight_range_is_forming():
    candidate = _detected(_flat_base(tight_days=18))

    assert candidate is not None
    assert candidate.complete is False


@pytest.mark.unit
def test_old_short_range_is_not_forming():
    df = _flat_base(tight_days=18)
    breakout = pd.DataFrame({
        "Date": pd.bdate_range(df["Date"].iloc[-1] + pd.Timedelta(days=1), periods=10),
        "Open": np.linspace(140.0, 200.0, 10),
        "High": np.linspace(140.5, 200.5, 10),
        "Low": np.linspace(139.5, 199.5, 10),
        "Close": np.linspace(140.0, 200.0, 10),
        "Volume": 1_500_000.0,
    })

    assert _detected(pd.concat((df, breakout), ignore_index=True)) is None


@pytest.mark.unit
def test_deep_range_rejected():
    assert _detected(_flat_base(depth=0.25)) is None


@pytest.mark.unit
def test_no_prior_uptrend_rejected():
    assert _detected(_flat_base(ramp_gain=0.0)) is None


@pytest.mark.unit
def test_broken_out_base_ends_before_the_breakout_bar():
    df = _flat_base()
    base_high = float(df["High"].iloc[60:].max())
    breakout = pd.DataFrame(
        {
            "Date": pd.bdate_range(df["Date"].iloc[-1] + pd.Timedelta(days=1), periods=3),
            "Open": base_high + 2,
            "High": base_high + 2.5,
            "Low": base_high + 1.5,
            "Close": base_high + 2,
            "Volume": 1_500_000.0,
        }
    )
    candidate = _detected(pd.concat((df, breakout), ignore_index=True))

    assert candidate is not None
    assert candidate.complete_index == len(df) - 1


@pytest.mark.unit
def test_evidence_narrates_depth_and_prior_advance():
    candidate = _detected(_flat_base())

    assert candidate is not None
    evidence = " ".join(candidate.evidence).lower()
    assert "range" in evidence and "%" in evidence
    assert "prior advance" in evidence


@pytest.mark.unit
def test_future_rows_do_not_contaminate_truncated_detection():
    df = _flat_base()
    truncated = _detected(df)
    future = pd.concat((df, _flat_base(tight_days=30).assign(Date=lambda frame: frame["Date"] + pd.Timedelta(days=500))), ignore_index=True)

    assert truncated == _detected(future.iloc[: len(df)].copy())
