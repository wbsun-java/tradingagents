"""Shared quality gates for completed and forming O'Neil cups."""

from __future__ import annotations

import pandas as pd

CUP_BOTTOM_MAX_VOLUME_RATIO = 1.0


def bottom_volume_dry_up(
    df: pd.DataFrame,
    cup_start: int,
    low_index: int,
    cup_end: int,
    rounding_window: int,
) -> tuple[bool, str]:
    """Require volume around the cup low to contract versus its decline."""
    bottom_start = max(cup_start, low_index - rounding_window)
    bottom_end = min(cup_end, low_index + rounding_window)
    decline_volume = pd.to_numeric(
        df["Volume"].iloc[cup_start:bottom_start], errors="coerce"
    ).mean()
    bottom_volume = pd.to_numeric(
        df["Volume"].iloc[bottom_start : bottom_end + 1], errors="coerce"
    ).mean()
    ratio = float(bottom_volume / decline_volume) if decline_volume else float("nan")
    low_date = pd.Timestamp(df.at[low_index, "Date"]).strftime("%Y-%m-%d")
    low_price = float(df.at[low_index, "Low"])
    qualifies = pd.notna(ratio) and ratio < CUP_BOTTOM_MAX_VOLUME_RATIO
    behavior = "dried up" if qualifies else "did not dry up"
    return bool(qualifies), (
        f"Volume at the {low_date} cup low of {low_price:.2f} {behavior}: "
        f"the bottom window averaged {ratio:.2f}x the preceding cup decline."
    )
