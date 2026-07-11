"""Matching, growth, and acceleration rules for the CANSLIM C+A scorer."""

from __future__ import annotations

from datetime import date, timedelta

from tradingagents.dataflows.canslim_earnings_data import QuarterEps

C_MIN_GROWTH_PCT = 25.0
A_MIN_CAGR_PCT = 25.0
C_MIN_QUARTERS = 5
A_MIN_YEARS = 4
YOY_MATCH_TOLERANCE_DAYS = 45
EPS_ZERO_EPSILON = 0.01


def match_key(quarter: QuarterEps) -> date:
    """Date used for YoY pairing: fiscal end when the vendor provides it, else report date."""
    return date.fromisoformat(quarter.fiscal_end or quarter.reported_date)


def find_yoy_counterpart(
    older: list[QuarterEps], target: QuarterEps
) -> QuarterEps | None:
    """Return the quarter closest to one year before ``target`` within tolerance."""
    wanted = match_key(target) - timedelta(days=365)
    best: tuple[int, QuarterEps] | None = None
    for quarter in older:
        delta = abs((match_key(quarter) - wanted).days)
        if delta <= YOY_MATCH_TOLERANCE_DAYS and (best is None or delta < best[0]):
            best = (delta, quarter)
    return best[1] if best else None


def growth_pct(now: float, year_ago: float) -> float:
    """YoY growth with an absolute-value base so a negative year-ago EPS scores sanely."""
    return (now - year_ago) / abs(year_ago) * 100.0


def classify_acceleration(quarters: list[QuarterEps]) -> tuple[str | None, str]:
    """YoY growth trend across the latest three quarters; informational, never a gate."""
    growths: list[float] = []
    for index in range(min(3, len(quarters))):
        target = quarters[index]
        counterpart = find_yoy_counterpart(quarters[index + 1 :], target)
        if counterpart is None or abs(counterpart.eps) < EPS_ZERO_EPSILON:
            break
        growths.append(growth_pct(target.eps, counterpart.eps))
    if len(growths) < 3:
        return None, "Year-over-year growth is computable for fewer than three recent quarters."
    chronological = list(reversed(growths))
    if chronological[0] < chronological[1] < chronological[2]:
        label = "accelerating"
    elif chronological[0] > chronological[1] > chronological[2]:
        label = "decelerating"
    else:
        label = "mixed"
    sequence = " -> ".join(f"{value:+.1f}%" for value in chronological)
    return label, f"Quarterly EPS growth ran {sequence} across the last three reports ({label})."
