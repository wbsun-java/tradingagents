from __future__ import annotations

import pytest

from tradingagents.dataflows.oneil_base_chain import classify_continuation


@pytest.mark.unit
@pytest.mark.parametrize(
    ("prior_pivot_price", "prior_date", "peak_price", "expected_state", "evidence_parts"),
    [
        (
            None,
            None,
            120.0,
            "no_prior_stage",
            ("first-stage base",),
        ),
        (
            100.0,
            "2026-01-15",
            120.0,
            "confirmed_continuation",
            ("20.0%", "2026-01-15", "100.00"),
        ),
        (
            100.0,
            "2026-01-15",
            127.5,
            "confirmed_continuation",
            ("27.5%", "2026-01-15", "100.00"),
        ),
        (
            100.0,
            "2026-01-15",
            108.0,
            "premature_continuation",
            ("8.0%", "20% continuation threshold"),
        ),
    ],
)
def test_classify_continuation(
    prior_pivot_price: float | None,
    prior_date: str | None,
    peak_price: float,
    expected_state: str,
    evidence_parts: tuple[str, ...],
) -> None:
    state, evidence = classify_continuation(prior_pivot_price, prior_date, peak_price)

    assert state == expected_state
    for evidence_part in evidence_parts:
        assert evidence_part in evidence
