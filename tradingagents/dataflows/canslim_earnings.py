"""Pure CANSLIM C+A verdicts over a point-in-time-filtered EarningsHistory."""

from __future__ import annotations

from typing import Any

from tradingagents.dataflows.canslim_earnings_data import AnnualEps, EarningsHistory
from tradingagents.dataflows.canslim_earnings_rules import (
    A_MIN_CAGR_PCT,
    A_MIN_YEARS,
    C_MIN_GROWTH_PCT,
    C_MIN_QUARTERS,
    EPS_ZERO_EPSILON,
    classify_acceleration,
    find_yoy_counterpart,
    growth_pct,
)


def _c_result(verdict: str, growth: float | None, acceleration: str | None, evidence: str) -> dict[str, Any]:
    return {"verdict": verdict, "growth_pct": growth, "acceleration": acceleration, "evidence": evidence}


def _score_c(history: EarningsHistory) -> dict[str, Any]:
    quarters = history.quarters
    if len(quarters) < C_MIN_QUARTERS:
        return _c_result(
            "unavailable", None, None,
            f"Only {len(quarters)} reported quarters are available, below the required {C_MIN_QUARTERS}.",
        )
    latest = quarters[0]
    counterpart = find_yoy_counterpart(quarters[1:], latest)
    if counterpart is None:
        return _c_result(
            "unavailable", None, None,
            f"No same-quarter counterpart was reported near one year before {latest.reported_date}.",
        )
    if abs(counterpart.eps) < EPS_ZERO_EPSILON:
        return _c_result(
            "unavailable", None, None,
            f"The year-ago quarterly EPS of {counterpart.eps:.2f} is too small a base for a meaningful growth rate.",
        )
    growth = round(growth_pct(latest.eps, counterpart.eps), 1)
    acceleration, acceleration_text = classify_acceleration(quarters)
    if latest.eps < 0:
        evidence = (
            f"Current quarterly EPS is negative ({latest.eps:.2f}, reported {latest.reported_date}); "
            "O'Neil requires positive current earnings."
        )
        return _c_result("fail", growth, acceleration, f"{evidence} {acceleration_text}")
    verdict = "pass" if growth >= C_MIN_GROWTH_PCT else "fail"
    relation = "meeting" if verdict == "pass" else "below"
    evidence = (
        f"Quarterly EPS of {latest.eps:.2f} (reported {latest.reported_date}) versus "
        f"{counterpart.eps:.2f} a year earlier ({counterpart.reported_date}) is {growth:+.1f}% "
        f"year-over-year, {relation} the {C_MIN_GROWTH_PCT:.0f}% CANSLIM threshold."
    )
    return _c_result(verdict, growth, acceleration, f"{evidence} {acceleration_text}")


def _a_result(verdict: str, growth: float | None, evidence: str) -> dict[str, Any]:
    return {"verdict": verdict, "growth_pct": growth, "evidence": evidence}


def _score_a(annual: list[AnnualEps]) -> dict[str, Any]:
    if len(annual) < A_MIN_YEARS:
        return _a_result(
            "unavailable", None,
            f"Only {len(annual)} annual EPS values are available, below the required {A_MIN_YEARS}.",
        )
    span = annual[:A_MIN_YEARS]
    newest, oldest = span[0], span[-1]
    values = ", ".join(f"{item.fiscal_year[:4]}: {item.eps:.2f}" for item in reversed(span))
    if oldest.eps < EPS_ZERO_EPSILON:
        newer_positive = all(item.eps > 0 for item in span[:-1])
        if newer_positive and newest.eps >= 2 * abs(oldest.eps):
            return _a_result(
                "pass", None,
                f"Annual EPS recovered from {oldest.eps:.2f} to {newest.eps:.2f} ({values}); the "
                "growth rate from a non-positive base is undefined but the turnaround qualifies.",
            )
        return _a_result(
            "unavailable", None,
            f"Annual EPS growth is not meaningfully computable from a base year of {oldest.eps:.2f} ({values}).",
        )
    down_years = sum(1 for i in range(len(span) - 1) if span[i].eps < span[i + 1].eps)
    cagr = round(((newest.eps / oldest.eps) ** (1 / (A_MIN_YEARS - 1)) - 1) * 100, 1)
    verdict = "pass" if cagr >= A_MIN_CAGR_PCT and down_years <= 1 else "fail"
    evidence = (
        f"Annual EPS ran {values} over the last {A_MIN_YEARS} fiscal years: {cagr:+.1f}% CAGR "
        f"with {down_years} down year(s)."
    )
    return _a_result(verdict, cagr, evidence)


def score_canslim_ca(history: EarningsHistory) -> dict[str, Any]:
    """Score O'Neil's C and A letters; verdicts are pass/fail/unavailable, never guessed."""
    return {"c": _score_c(history), "a": _score_a(history.annual)}
