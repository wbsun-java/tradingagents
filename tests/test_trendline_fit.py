"""Unit tests for the convex-hull envelope trendline fitter."""

from __future__ import annotations

import pytest

from tradingagents.dataflows.trendline_fit import resistance_line, support_line


@pytest.mark.unit
def test_resistance_line_ignores_a_stale_interior_spike():
    # A high pivot in the middle of the window that's above everything else
    # (like TSLA's 453 peak between two lower, more recent highs) must not
    # drag the line — the *current* resistance edge should run between the
    # two most recent relevant highs, not average in the old spike.
    highs = [(127, 409.28), (145, 453.40), (154, 445.60), (167, 416.00), (171, 414.75)]

    line = resistance_line(highs)

    assert line is not None
    assert (line.start_index, line.end_index) == (154, 171)
    assert line.slope < 0
    # Every high must sit on or below the fitted line (the envelope property).
    for index, price in highs:
        assert price <= line.slope * index + line.intercept + 1e-9


@pytest.mark.unit
def test_support_line_stays_beneath_every_low():
    lows = [(119, 337.24), (133, 364.02), (149, 393.63), (164, 380.15), (175, 368.60)]

    line = support_line(lows)

    assert line is not None
    assert line.slope > 0
    for index, price in lows:
        assert price >= line.slope * index + line.intercept - 1e-9


@pytest.mark.unit
def test_collinear_points_reduce_to_the_two_endpoints():
    points = [(0, 100.0), (10, 110.0), (20, 120.0), (30, 130.0)]

    line = resistance_line(points)

    assert (line.start_index, line.end_index) == (0, 30)
    assert line.slope == pytest.approx(1.0)


@pytest.mark.unit
def test_fewer_than_two_points_returns_none():
    assert resistance_line([(0, 100.0)]) is None
    assert support_line([]) is None


@pytest.mark.unit
def test_simple_rising_and_falling_sets_get_the_expected_sign():
    rising = [(0, 90.0), (5, 95.0), (10, 100.0)]
    falling = [(0, 100.0), (5, 95.0), (10, 90.0)]

    assert support_line(rising).slope > 0
    assert resistance_line(falling).slope < 0
