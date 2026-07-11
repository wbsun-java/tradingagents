"""Continuation-stage classification for O'Neil base chains."""

from __future__ import annotations

CONTINUATION_GAIN_THRESHOLD = 0.20


def classify_continuation(
    prior_pivot_price: float | None, prior_date: str | None, peak_price: float
) -> tuple[str, str]:
    """Classify whether a base follows a sufficiently advanced prior stage."""
    if prior_pivot_price is None:
        return (
            "no_prior_stage",
            "No prior pivot is available, so this is a first-stage base.",
        )

    gain = (
        (peak_price - prior_pivot_price) / prior_pivot_price
        if prior_pivot_price
        else 0.0
    )
    if gain >= CONTINUATION_GAIN_THRESHOLD:
        return (
            "confirmed_continuation",
            f"The peak gained {gain:.1%} from the prior pivot "
            f"({prior_date} at {prior_pivot_price:.2f}), confirming continuation.",
        )
    return (
        "premature_continuation",
        f"The peak gained {gain:.1%} from the prior pivot "
        f"({prior_date} at {prior_pivot_price:.2f}), below IBD's 20% continuation threshold.",
    )
