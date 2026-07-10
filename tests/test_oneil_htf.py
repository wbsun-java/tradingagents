"""Unit tests for O'Neil high-tight-flag detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, prepare_ohlcv
from tradingagents.dataflows.oneil_htf import detect_high_tight_flag


def _htf(pole_days: int = 35, flag_days: int = 10, advance: float = 1.0, correction: float = 0.12) -> pd.DataFrame:
    pole = np.linspace(50.0, 50.0 * (1 + advance), pole_days + 1)
    flag_high = pole[-1] * (1 - correction)
    flag = np.linspace(flag_high, flag_high * (1 - correction), flag_days)
    closes = np.concatenate((pole, flag))
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(closes)),
        "Open": closes,
        "High": closes + 0.25,
        "Low": closes - 0.25,
        "Close": closes,
        "Volume": [1_000_000] * len(pole) + [500_000] * len(flag),
    })


def _detected(df: pd.DataFrame):
    return detect_high_tight_flag(df, float(atr(df).iloc[-1]))


@pytest.mark.unit
def test_textbook_htf_detected():
    candidate = _detected(_htf())

    assert candidate is not None
    assert candidate.complete is True
    assert candidate.pattern_type == "high_tight_flag"
    assert candidate.pivot_price == candidate.geometry["flag_high"]


@pytest.mark.unit
def test_flag_too_young_is_forming():
    candidate = _detected(_htf(flag_days=3))

    assert candidate is not None
    assert candidate.complete is False


@pytest.mark.unit
def test_resolved_young_flag_is_not_forming():
    df = _htf(flag_days=3)
    flag_high = float(df["High"].iloc[-3:].max())
    later = pd.DataFrame({
        "Date": pd.bdate_range(df["Date"].iloc[-1] + pd.Timedelta(days=1), periods=4),
        "Open": [flag_high + 2.0] * 4,
        "High": [flag_high + 2.25] * 4,
        "Low": [flag_high + 1.75] * 4,
        "Close": [flag_high + 2.0] * 4,
        "Volume": [1_500_000] * 4,
    })

    assert _detected(pd.concat((df, later), ignore_index=True)) is None


@pytest.mark.unit
def test_correction_too_deep_rejected():
    assert _detected(_htf(correction=0.35)) is None


@pytest.mark.unit
def test_advance_too_small_rejected():
    assert _detected(_htf(advance=0.40)) is None


@pytest.mark.unit
def test_advance_too_slow_rejected():
    assert _detected(_htf(pole_days=90)) is None


@pytest.mark.unit
def test_flag_overlong_rejected():
    assert _detected(_htf(flag_days=40)) is None


@pytest.mark.unit
def test_evidence_narrates_advance_and_flag_volume():
    candidate = _detected(_htf())

    assert candidate is not None
    evidence = " ".join(candidate.evidence)
    assert f"{candidate.geometry['advance_pct']:.1f}%" in evidence
    assert "flag volume was" in evidence and "pole volume" in evidence


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_before_htf_detection():
    df = _htf(pole_days=90)
    cutoff = df["Date"].iloc[79].strftime("%Y-%m-%d")
    future = _htf().assign(Date=lambda frame: frame["Date"] + pd.Timedelta(days=500))

    prepared = prepare_ohlcv(pd.concat((df, future), ignore_index=True), cutoff, 420)

    assert prepared["Date"].max() <= pd.Timestamp(cutoff)
    assert _detected(prepared) is None
