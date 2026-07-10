"""Detect, evaluate, and rank O'Neil base-pattern candidates."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.oneil_ascending_base import detect_ascending_base
from tradingagents.dataflows.oneil_base_types import BaseCandidate
from tradingagents.dataflows.oneil_breakout import (
    BreakoutEvent,
    Status,
    breakout_reversed,
    compute_confidence,
    determine_status,
    find_breakout,
)
from tradingagents.dataflows.oneil_cup import detect_cup
from tradingagents.dataflows.oneil_cup_forming import detect_forming_cup
from tradingagents.dataflows.oneil_double_bottom import detect_double_bottom
from tradingagents.dataflows.oneil_flat_base import detect_flat_base
from tradingagents.dataflows.oneil_handle import detect_handle
from tradingagents.dataflows.oneil_htf import detect_high_tight_flag

STATUS_RANK = {"confirmed": 3, "developing": 2, "forming": 1}


@dataclass
class PatternDetection:
    """A candidate after shared breakout status and confidence evaluation."""

    candidate: BaseCandidate
    status: Status
    breakout: BreakoutEvent | None
    confidence: float


def _cup_candidates(df: pd.DataFrame, atr_value: float) -> list[BaseCandidate]:
    """Return completed and still-forming cup candidates independently."""
    candidates: list[BaseCandidate] = []
    cup = detect_cup(df, atr_value)
    if cup is not None:
        handle = detect_handle(df, cup, atr_value)
        pattern_type = "cup_with_handle" if handle is not None else "cup_without_handle"
        complete_index = handle.end_index if handle is not None else cup.right_high_index
        pivot_price = handle.high_price if handle is not None else cup.left_high_price
        pivot_index = handle.high_index if handle is not None else cup.left_high_index
        pivot_date = pd.Timestamp(df.at[pivot_index, "Date"]).strftime("%Y-%m-%d")
        geometry = {
            "start_date": cup.left_high_date,
            "left_high": cup.left_high_price,
            "low_date": cup.low_date,
            "low_price": cup.low_price,
            "right_high_date": cup.right_high_date,
            "depth_pct": cup.depth_pct * 100,
            "duration_days": cup.duration_days,
        }
        evidence = [*cup.evidence, *(handle.evidence if handle is not None else [])]
        candidates.append(BaseCandidate(
            pattern_type=pattern_type, complete=True, pivot_price=pivot_price,
            pivot_date=pivot_date, complete_index=complete_index,
            geometry=geometry, evidence=evidence, handle=handle,
        ))
    forming = detect_forming_cup(df, atr_value)
    if forming is not None:
        candidates.append(forming)
    return candidates


def detect_all(df: pd.DataFrame, atr_value: float) -> list[BaseCandidate]:
    """Run each base detector and return every detected candidate."""
    detectors = (
        detect_flat_base,
        detect_double_bottom,
        detect_ascending_base,
        detect_high_tight_flag,
    )
    cups = _cup_candidates(df, atr_value)
    return cups + [candidate for detector in detectors if (candidate := detector(df, atr_value)) is not None]


def evaluate_candidates(
    df: pd.DataFrame,
    candidates: list[BaseCandidate],
    atr_value: float,
    rs_score: float | None,
) -> list[PatternDetection]:
    """Apply the common breakout engine once to each candidate."""
    detections: list[PatternDetection] = []
    for candidate in candidates:
        breakout = (
            find_breakout(df, candidate.pivot_price, candidate.complete_index + 1, atr_value)
            if candidate.complete
            else None
        )
        reversed_after = (
            breakout_reversed(df, breakout, candidate.pivot_price, atr_value)
            if breakout is not None
            else False
        )
        status = determine_status(
            complete=candidate.complete,
            handle=candidate.handle,
            handle_required=candidate.pattern_type == "cup_with_handle",
            breakout=breakout,
            reversed_after=reversed_after,
        )
        detections.append(
            PatternDetection(
                candidate, status, breakout,
                compute_confidence(candidate.pattern_type, status, candidate.handle, breakout,
                                   rs_score, undercut=candidate.undercut),
            )
        )
    return detections


def arbitrate(detections: list[PatternDetection]) -> tuple[PatternDetection | None, list[PatternDetection]]:
    """Choose the most advanced live pattern, retaining all other detections."""
    if not detections:
        return None, []
    live = [item for item in detections if item.status in STATUS_RANK]
    if live:
        primary = max(
            live,
            key=lambda item: (STATUS_RANK[item.status], item.confidence, item.candidate.pivot_date),
        )
    else:
        primary = max(
            detections,
            key=lambda item: item.breakout.date if item.breakout is not None else item.candidate.pivot_date,
        )
    return primary, [item for item in detections if item is not primary]
