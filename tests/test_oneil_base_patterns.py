"""Unit tests for O'Neil base-pattern orchestration and arbitration."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.oneil_base_patterns import (
    PatternDetection,
    arbitrate,
    detect_all,
    evaluate_candidates,
)
from tradingagents.dataflows.oneil_base_types import BaseCandidate
from tradingagents.dataflows.oneil_cup import atr, prepare_ohlcv


def _detection(pattern_type: str, status: str, confidence: float, date: str) -> PatternDetection:
    candidate = BaseCandidate(pattern_type, True, 100.0, date, 10, {}, [])  # type: ignore[arg-type]
    return PatternDetection(candidate, status, None, confidence)  # type: ignore[arg-type]


def _cup_without_handle() -> pd.DataFrame:
    from tests.test_oneil_cup import _cup

    return _cup(extra_flat=0)


@pytest.mark.unit
def test_confirmed_flat_base_beats_forming_htf():
    flat = _detection("flat_base", "confirmed", 0.5, "2024-05-01")
    htf = _detection("high_tight_flag", "forming", 0.8, "2024-06-01")
    primary, others = arbitrate([htf, flat])
    assert primary is flat
    assert others == [htf]


@pytest.mark.unit
def test_equal_status_tie_broken_by_confidence_then_recency():
    weaker = _detection("flat_base", "developing", 0.4, "2024-06-02")
    stronger = _detection("ascending_base", "developing", 0.5, "2024-06-01")
    assert arbitrate([weaker, stronger])[0] is stronger
    recent = _detection("flat_base", "developing", 0.5, "2024-06-03")
    assert arbitrate([stronger, recent])[0] is recent


@pytest.mark.unit
def test_failed_pattern_never_beats_live_one():
    failed = _detection("high_tight_flag", "failed", 0.0, "2024-07-01")
    live = _detection("flat_base", "forming", 0.2, "2024-06-01")
    assert arbitrate([failed, live])[0] is live


@pytest.mark.unit
def test_all_failed_reports_most_recent_failure():
    older = _detection("flat_base", "failed", 0.0, "2024-06-01")
    recent = _detection("double_bottom_base", "failed", 0.0, "2024-06-02")
    primary, _ = arbitrate([older, recent])
    assert primary is recent
    assert primary.status == "failed"


@pytest.mark.unit
def test_cup_without_handle_reported_as_developing():
    data = _cup_without_handle()
    df = prepare_ohlcv(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), 420)
    atr_value = float(atr(df).iloc[-1])
    cups = [item for item in detect_all(df, atr_value) if item.pattern_type.startswith("cup_")]
    assert cups and cups[0].pattern_type == "cup_without_handle"
    detection = evaluate_candidates(df, cups, atr_value, None)[0]
    assert detection.status == "developing"
