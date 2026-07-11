"""Continuation-chain classification for O'Neil flat bases."""

from __future__ import annotations

CONTINUATION_GAIN_THRESHOLD = 0.20


def classify_continuation(
    prior_pivot_price: float | None, prior_date: str | None, peak_price: float
) -> tuple[str, str]:
    """Classify a flat base's peak against its most recent prior confirmed breakout."""
    if prior_pivot_price is None:
        return (
            "no_prior_stage",
            "No confirmed prior base was found in the available history; "
            "treating as a first-stage base.",
        )

    gain = (peak_price - prior_pivot_price) / prior_pivot_price if prior_pivot_price else 0.0
    if gain >= CONTINUATION_GAIN_THRESHOLD:
        return (
            "confirmed_continuation",
            f"Advanced {gain:.1%} off the {prior_date} breakout at {prior_pivot_price:.2f} "
            "before basing again, qualifying as a genuine continuation base.",
        )
    return (
        "premature_continuation",
        f"Only advanced {gain:.1%} off the {prior_date} breakout at {prior_pivot_price:.2f} "
        "before basing again — below IBD's 20% continuation threshold.",
    )
