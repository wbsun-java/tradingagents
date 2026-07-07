"""Envelope trendlines for chart-pattern boundaries.

See CHART_PATTERN_ANALYSIS_PLAN.md, "三角形整理". A resistance/support line
should have every pivot on one side of it, not scattered around an averaged
best-fit line — a single stray high in the middle of the window should not
drag a least-squares regression off the boundary price is actually
respecting. This fits the upper/lower convex hull of the candidate pivots and
returns the most recent hull edge as the current trendline, so an old,
already-superseded extreme doesn't distort "the" line.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[int, float]


@dataclass
class TrendLine:
    slope: float
    intercept: float
    start_index: int
    end_index: int


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull_half(points: list[Point], *, upper: bool) -> list[Point]:
    """One half of Andrew's monotone chain; ``upper=True`` gives the top boundary."""
    ordered = sorted(points, reverse=upper)
    hull: list[Point] = []
    for point in ordered:
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], point) <= 0:
            hull.pop()
        hull.append(point)
    return list(reversed(hull)) if upper else hull


def _edge_line(hull: list[Point]) -> TrendLine | None:
    if len(hull) < 2:
        return None
    (x1, y1), (x2, y2) = hull[-2], hull[-1]
    slope = (y2 - y1) / (x2 - x1)
    return TrendLine(slope=slope, intercept=y1 - slope * x1, start_index=x1, end_index=x2)


def resistance_line(points: list[Point]) -> TrendLine | None:
    """Most recent edge of the upper hull: every given high lies on or below it."""
    return _edge_line(_hull_half(sorted(set(points)), upper=True))


def support_line(points: list[Point]) -> TrendLine | None:
    """Most recent edge of the lower hull: every given low lies on or above it."""
    return _edge_line(_hull_half(sorted(set(points)), upper=False))
