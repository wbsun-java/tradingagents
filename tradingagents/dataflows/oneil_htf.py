"""Detection of O'Neil high-tight flags."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.oneil_base_types import BaseCandidate

HTF_POLE_MIN_ADVANCE = 1.9
HTF_POLE_MAX_DAYS = 45
HTF_FLAG_MIN_DAYS = 5
HTF_FLAG_MAX_DAYS = 25
HTF_FLAG_MAX_CORRECTION = 0.25
BREAKOUT_BUFFER_ATR = 0.1


def _latest_pole(df: pd.DataFrame) -> tuple[int, int] | None:
    """Return the latest qualifying close-to-close flagpole."""
    for pole_end in range(len(df) - 1, 0, -1):
        for pole_start in range(pole_end - 1, max(-1, pole_end - HTF_POLE_MAX_DAYS - 1), -1):
            start_close = float(df.at[pole_start, "Close"])
            if start_close and float(df.at[pole_end, "Close"]) / start_close >= HTF_POLE_MIN_ADVANCE:
                return pole_start, pole_end
    return None


def _flag_end(df: pd.DataFrame, pole_end: int, atr_value: float) -> int | None:
    """End immediately before the first buffered close above the flag high."""
    start = pole_end + 1
    if start >= len(df):
        return None
    flag_high = float(df.at[start, "High"])
    for index in range(start + 1, len(df)):
        if float(df.at[index, "Close"]) > flag_high + BREAKOUT_BUFFER_ATR * atr_value:
            return index - 1
        flag_high = max(flag_high, float(df.at[index, "High"]))
    return len(df) - 1


def _date(df: pd.DataFrame, index: int) -> str:
    return pd.Timestamp(df.at[index, "Date"]).strftime("%Y-%m-%d")


def detect_high_tight_flag(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the latest pole-and-tight-flag candidate, if present."""
    pole = _latest_pole(df)
    if pole is None:
        return None
    pole_start, pole_end = pole
    flag_end = _flag_end(df, pole_end, atr_value)
    if flag_end is None:
        return None
    flag_days = flag_end - pole_end
    if flag_days > HTF_FLAG_MAX_DAYS:
        return None
    if flag_days < HTF_FLAG_MIN_DAYS and flag_end != len(df) - 1:
        return None
    flag = df.iloc[pole_end + 1 : flag_end + 1]
    flag_high = float(flag["High"].max())
    flag_low = float(flag["Low"].min())
    correction = (flag_high - flag_low) / flag_high if flag_high else 0.0
    if correction > HTF_FLAG_MAX_CORRECTION:
        return None
    high_index = int(flag["High"].idxmax())
    low_index = int(flag["Low"].idxmin())
    start_price = float(df.at[pole_start, "Close"])
    end_price = float(df.at[pole_end, "Close"])
    advance = end_price / start_price - 1
    pole_start_date, pole_end_date = _date(df, pole_start), _date(df, pole_end)
    flag_start_date, flag_end_date = _date(df, pole_end + 1), _date(df, flag_end)
    pole_volume = pd.to_numeric(df["Volume"].iloc[pole_start : pole_end + 1], errors="coerce").mean()
    flag_volume = pd.to_numeric(flag["Volume"], errors="coerce").mean()
    volume_ratio = float(flag_volume / pole_volume) if pole_volume and not pd.isna(flag_volume) else None
    volume_note = "unavailable" if volume_ratio is None else f"{volume_ratio:.2f}x pole volume"
    return BaseCandidate(
        pattern_type="high_tight_flag",
        complete=flag_days >= HTF_FLAG_MIN_DAYS,
        pivot_price=flag_high,
        pivot_date=_date(df, high_index),
        complete_index=flag_end,
        geometry={
            "pole_start": {"date": pole_start_date, "price": start_price},
            "pole_end": {"date": pole_end_date, "price": end_price},
            "advance_pct": advance * 100,
            "pole_days": pole_end - pole_start,
            "flag_high": flag_high,
            "flag_low": flag_low,
            "correction_pct": correction * 100,
            "flag_days": flag_days,
        },
        evidence=[
            f"Flagpole advanced {advance:.1%} from {pole_start_date} at {start_price:.2f} to "
            f"{pole_end_date} at {end_price:.2f} over {pole_end - pole_start} trading days.",
            f"Flag from {flag_start_date} at {float(df.at[pole_end + 1, 'Close']):.2f} to "
            f"{flag_end_date} at {float(df.at[flag_end, 'Close']):.2f} held a {correction:.1%} correction "
            f"from the {_date(df, high_index)} high of {flag_high:.2f} to the {_date(df, low_index)} "
            f"low of {flag_low:.2f}; mean flag volume was {volume_note}.",
        ],
        start_index=pole_end,
        base_low_price=flag_low,
    )
