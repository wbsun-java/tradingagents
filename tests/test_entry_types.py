"""Constants and dataclass for the entry-state trading layer (SP3)."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import entry_types as t


@pytest.mark.unit
def test_state_names_and_tuning_constants():
    assert t.PREDICTIVE_BOTTOM == "predictive_bottom"
    assert t.BREAKOUT_RETEST_ENTRY == "breakout_retest_entry"
    assert t.FALSE_BREAKOUT_SHORT == "false_breakout_short"
    assert (t.ENTRY_PROXIMITY_ATR, t.RETEST_WINDOW_BARS, t.PREDICTIVE_UNDERSHOOT_ATR) == (
        0.5, 15, 0.25,
    )


@pytest.mark.unit
def test_eligibility_sets():
    assert "double_bottom" in t.LONG_ELIGIBLE
    assert "resistance_breakout" in t.LONG_ELIGIBLE
    assert frozenset(
        {"double_top", "descending_triangle", "support_breakdown"}
    ) == t.BEARISH_TYPES


@pytest.mark.unit
def test_entry_assessment_holds_all_fields():
    a = t.EntryAssessment(
        state="observe", direction="none", entry_zone_low=None, entry_zone_high=None,
        trigger_price=None, invalidation_price=None, confirmation="x", volume_role="not_applicable",
    )
    assert a.state == "observe" and a.direction == "none"
