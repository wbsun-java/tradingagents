"""Unit tests for the peak-anchored O'Neil flat-base detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr
from tradingagents.dataflows.oneil_flat_base import detect_flat_base


def _frame(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    prices = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": volumes,
    })


def _flat_base(
    tight_days: int = 30, ramp_gain: float = 40.0, depth: float = 0.08, dry: bool = True
) -> tuple[pd.DataFrame, int]:
    ramp = np.linspace(100.0, 100.0 + ramp_gain, 60).tolist()
    peak = 100.0 + ramp_gain + 3.0
    angles = np.linspace(0, 6 * np.pi, tight_days - 1)
    range_closes = (peak * (1 - depth * (0.55 + 0.45 * np.sin(angles)))).tolist()
    closes = ramp + [peak] + range_closes
    base_volume = 700_000.0 if dry else 1_000_000.0
    return _frame(closes, [1_000_000.0] * 61 + [base_volume] * (tight_days - 1)), 60


def _detected(df: pd.DataFrame):
    return detect_flat_base(df, float(atr(df).iloc[-1]))


@pytest.mark.unit
def test_textbook_flat_base_starts_at_the_peak():
    df, peak_index = _flat_base()
    candidate = _detected(df)

    assert candidate is not None and candidate.complete is True
    assert candidate.pivot_price == pytest.approx(df.at[peak_index, "High"])
    assert candidate.geometry["start_date"] == df.at[peak_index, "Date"].strftime("%Y-%m-%d")


@pytest.mark.unit
def test_uptrend_anchored_at_the_peak_not_the_range():
    df, _ = _flat_base(ramp_gain=20.0)

    assert _detected(df) is None


@pytest.mark.unit
def test_depth_measured_from_the_peak_rejected_when_too_deep():
    df, _ = _flat_base(depth=0.20)

    assert _detected(df) is None


@pytest.mark.unit
def test_no_volume_dry_up_rejected():
    df, _ = _flat_base(dry=False)

    assert _detected(df) is None


@pytest.mark.unit
def test_live_short_range_is_forming():
    candidate = _detected(_flat_base(tight_days=18)[0])

    assert candidate is not None and candidate.complete is False


@pytest.mark.unit
def test_old_short_range_is_not_forming():
    df, _ = _flat_base(tight_days=18)
    extension = _frame(np.linspace(150.0, 170.0, 10).tolist(), [1_500_000.0] * 10)
    extension["Date"] += df["Date"].iloc[-1] + pd.Timedelta(days=1) - extension["Date"].iloc[0]

    assert _detected(pd.concat((df, extension), ignore_index=True)) is None


@pytest.mark.unit
def test_resumed_advance_restarts_the_base_at_the_new_peak():
    first, _ = _flat_base(tight_days=18)
    advance = np.linspace(150.0, 180.0, 12).tolist()
    second_range = (180.0 * (1 - 0.07 * (0.55 + 0.45 * np.sin(np.linspace(0, 6 * np.pi, 29))))).tolist()
    second = _frame(advance + [183.0] + second_range, [1_000_000.0] * 13 + [700_000.0] * 29)
    second["Date"] += first["Date"].iloc[-1] + pd.Timedelta(days=1) - second["Date"].iloc[0]
    df = pd.concat((first, second), ignore_index=True)

    candidate = _detected(df)

    assert candidate is not None
    assert candidate.pivot_price == pytest.approx(183.5)
    assert candidate.geometry["start_date"] == df.at[90, "Date"].strftime("%Y-%m-%d")


@pytest.mark.unit
def test_broken_out_base_ends_before_the_breakout_bar():
    df, _ = _flat_base()
    breakout = _frame([150.0, 151.0, 152.0], [1_500_000.0] * 3)
    breakout["Date"] += df["Date"].iloc[-1] + pd.Timedelta(days=1) - breakout["Date"].iloc[0]
    candidate = _detected(pd.concat((df, breakout), ignore_index=True))

    assert candidate is not None and candidate.complete_index == len(df) - 1


@pytest.mark.unit
def test_future_rows_do_not_contaminate_truncated_detection():
    df, _ = _flat_base()

    assert _detected(df) == _detected(pd.concat((df, df.iloc[:5]), ignore_index=True).iloc[: len(df)])
