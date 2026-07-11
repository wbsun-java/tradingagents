"""Unit tests for O'Neil base-pattern orchestration and arbitration."""

from __future__ import annotations

import pandas as pd
import pytest

from tests.oneil_base_chain_fixtures import chained_flat_bases, single_flat_base
from tradingagents.dataflows.oneil_base_patterns import (
    PatternDetection,
    arbitrate,
    detect_all,
    evaluate_candidates,
)
from tradingagents.dataflows.oneil_base_types import BaseCandidate
from tradingagents.dataflows.oneil_cup import CupCandidate, atr, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import HandleCandidate


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


@pytest.mark.unit
def test_forming_cup_flows_through_as_forming():
    from tests.test_oneil_cup_forming import _forming_cup

    df = _forming_cup()
    atr_value = float(atr(df).iloc[-1])
    cups = [item for item in detect_all(df, atr_value) if item.pattern_type == "cup_without_handle"]

    assert cups and cups[0].complete is False
    detection = evaluate_candidates(df, cups, atr_value, None)[0]
    assert detection.status == "forming"
    assert detection.breakout is None


@pytest.mark.unit
def test_failed_completed_cup_does_not_mask_forming_cup(monkeypatch: pytest.MonkeyPatch):
    import tradingagents.dataflows.oneil_base_patterns as patterns

    df = _cup_without_handle()
    cup = CupCandidate(10, "2024-01-16", 100.0, "2024-02-01", 70.0, 30, "2024-02-13", 30.0, 20)
    invalid_handle = HandleCandidate(
        "2024-02-14", 35, "2024-02-20", 60.0, 31, 99.0, 1.2, 6, False
    )
    forming = BaseCandidate("cup_without_handle", False, 150.0, "2024-01-02", len(df) - 1, {}, [])
    monkeypatch.setattr(patterns, "detect_cup", lambda *_: cup)
    monkeypatch.setattr(patterns, "detect_handle", lambda *_: invalid_handle)
    monkeypatch.setattr(patterns, "detect_forming_cup", lambda *_: forming)
    monkeypatch.setattr(patterns, "detect_flat_base", lambda *_: None)
    monkeypatch.setattr(patterns, "detect_double_bottom", lambda *_: None)
    monkeypatch.setattr(patterns, "detect_ascending_base", lambda *_: None)
    monkeypatch.setattr(patterns, "detect_high_tight_flag", lambda *_: None)

    cups = detect_all(df, 1.0)
    primary, others = arbitrate(evaluate_candidates(df, cups, 1.0, None))

    assert len(cups) == 2
    assert primary is not None and primary.candidate is forming
    assert len(others) == 1 and others[0].status == "failed"


def _evaluation_frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=len(closes)),
            "Close": closes,
            "High": [value + 1 for value in closes],
            "Low": [value - 1 for value in closes],
            "Volume": [100] * len(closes),
        }
    )


@pytest.mark.unit
def test_completed_base_broken_below_its_low_fails():
    df = _evaluation_frame([100.0] * 12 + [89.0])
    candidate = BaseCandidate(
        "flat_base", True, 110.0, "2024-01-01", 10, {}, [],
        start_index=0, base_low_price=90.0,
    )
    assert evaluate_candidates(df, [candidate], 1.0, None)[0].status == "failed"


@pytest.mark.unit
def test_cup_with_handle_fails_below_the_handle_low():
    df = _evaluation_frame([100.0] * 12 + [94.0])
    handle = HandleCandidate(
        "2024-01-05", 4, "2024-01-11", 95.0, 5, 105.0, 0.8, 6, True
    )
    candidate = BaseCandidate(
        "cup_with_handle", True, 105.0, "2024-01-05", 10, {}, [], handle,
        start_index=0, base_low_price=95.0,
    )
    assert evaluate_candidates(df, [candidate], 1.0, None)[0].status == "failed"


@pytest.mark.unit
def test_base_older_than_65_weeks_is_dropped():
    df = _evaluation_frame([100.0] * 327)
    candidate = BaseCandidate(
        "flat_base", True, 110.0, "2024-01-01", 10, {}, [],
        start_index=0, base_low_price=90.0,
    )
    assert evaluate_candidates(df, [candidate], 1.0, None) == []


@pytest.mark.unit
def test_hand_built_candidate_without_new_fields_still_works():
    df = _evaluation_frame([100.0] * 327)
    candidate = BaseCandidate("flat_base", True, 110.0, "2024-01-01", 10, {}, [])
    result = evaluate_candidates(df, [candidate], 1.0, None)
    assert result[0].candidate is candidate
    assert result[0].status == "developing"


def _flat_base_detection(df: pd.DataFrame) -> PatternDetection:
    atr_value = float(atr(df).iloc[-1])
    candidates = [c for c in detect_all(df, atr_value) if c.pattern_type == "flat_base"]
    assert candidates, "expected a flat_base candidate"
    return evaluate_candidates(df, candidates, atr_value, None)[0]


@pytest.mark.unit
def test_confirmed_continuation_flat_base():
    df, _, _, peak2 = chained_flat_bases(1.25)
    detection = _flat_base_detection(df)
    assert detection.candidate.pivot_price == pytest.approx(peak2, abs=0.6)
    assert detection.candidate.continuation_state == "confirmed_continuation"
    assert any("continuation base" in line for line in detection.candidate.evidence)


@pytest.mark.unit
def test_premature_continuation_flat_base_is_flagged():
    df, _, _, _ = chained_flat_bases(1.08)
    detection = _flat_base_detection(df)
    assert detection.candidate.continuation_state == "premature_continuation"
    assert any("20% continuation threshold" in line for line in detection.candidate.evidence)


@pytest.mark.unit
def test_premature_continuation_scores_lower_than_confirmed():
    confirmed = _flat_base_detection(chained_flat_bases(1.25)[0])
    premature = _flat_base_detection(chained_flat_bases(1.08)[0])
    assert premature.confidence < confirmed.confidence


@pytest.mark.unit
def test_no_prior_stage_is_not_penalized():
    detection = _flat_base_detection(single_flat_base())
    assert detection.candidate.continuation_state == "no_prior_stage"
    assert any("first-stage base" in line for line in detection.candidate.evidence)
