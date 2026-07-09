"""Pocket Pivot core detection: Kacher & Morales's two-rule definition -- an
ATR-adaptive cross back above the 10-day or 50-day moving average on an up
day, confirmed by volume exceeding the highest down-volume day of the prior
10 sessions. See docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

CROSS_BUFFER_ATR = 0.1
DOWN_VOLUME_LOOKBACK = 10
EVENT_SCAN_WINDOW = 60
MA_PERIODS: tuple[int, ...] = (10, 50)
# sma(50) needs 50 valid closes to produce one non-NaN value, and _qualifies
# requires both ma_series.iloc[i] and ma_series.iloc[i-1] to be non-NaN, so
# the earliest possible non-NaN pair needs i >= 50 (0-indexed) i.e. 51 rows
# total. That's the smallest row count for which the 50dma pocket pivot rule
# can ever fire, and it comfortably covers atr()'s own 15-row minimum too.
MIN_ROWS = 51


def prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {sorted(missing)}")
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date"])
        .sort_values("Date")
        .drop_duplicates(subset="Date", keep="last")
    )
    cutoff = pd.to_datetime(curr_date)
    df = df[df["Date"] <= cutoff]
    df = df.tail(max(MIN_ROWS, int(look_back_days)))
    df = df.reset_index(drop=True)
    if len(df) < MIN_ROWS:
        raise ValueError(f"At least {MIN_ROWS} OHLCV rows are required for Pocket Pivot analysis.")
    return df


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def _highest_down_volume(df: pd.DataFrame, i: int, window: int = DOWN_VOLUME_LOOKBACK) -> float:
    lo = max(1, i - window)
    down_volumes = [
        float(df.at[j, "Volume"])
        for j in range(lo, i)
        if float(df.at[j, "Close"]) < float(df.at[j - 1, "Close"])
    ]
    return max(down_volumes) if down_volumes else 0.0


@dataclass
class PocketPivotEvent:
    index: int
    date: str
    ma_period: Literal[10, 50]
    close: float
    ma_value: float
    volume: float
    highest_down_volume_10d: float
    gap_up: bool
    evidence: list[str] = field(default_factory=list)


def _qualifies(
    df: pd.DataFrame, i: int, period: int, ma_series: pd.Series, atr_value: float
) -> PocketPivotEvent | None:
    if i < 1 or pd.isna(ma_series.iloc[i]) or pd.isna(ma_series.iloc[i - 1]):
        return None
    close, prior_close = float(df.at[i, "Close"]), float(df.at[i - 1, "Close"])
    if close <= prior_close:
        return None
    buffer = CROSS_BUFFER_ATR * atr_value
    ma_value, prior_ma = float(ma_series.iloc[i]), float(ma_series.iloc[i - 1])
    if not (prior_close <= prior_ma + buffer and close > ma_value + buffer):
        return None
    volume = float(df.at[i, "Volume"])
    highest_down = _highest_down_volume(df, i)
    if volume <= highest_down:
        return None
    gap_up = float(df.at[i, "Open"]) > prior_close
    evidence = [
        f"Closed at {close:.2f}, above the {period}dma ({ma_value:.2f}) after being at/below "
        f"it the prior day, on {volume:,.0f} volume vs. {highest_down:,.0f} highest down-volume "
        f"day in the prior {DOWN_VOLUME_LOOKBACK} sessions."
    ]
    return PocketPivotEvent(
        i, df.at[i, "Date"].strftime("%Y-%m-%d"), period, close, ma_value,
        volume, highest_down, gap_up, evidence,
    )


def find_pocket_pivots(
    df: pd.DataFrame, atr_value: float, ma_periods: tuple[int, ...] = MA_PERIODS
) -> list[PocketPivotEvent]:
    """Scan the last EVENT_SCAN_WINDOW bars for qualifying pocket pivots."""
    start = max(0, len(df) - EVENT_SCAN_WINDOW)
    ma_series_by_period = {period: sma(df["Close"], period) for period in ma_periods}
    events: list[PocketPivotEvent] = []
    for i in range(start, len(df)):
        for period in ma_periods:
            hit = _qualifies(df, i, period, ma_series_by_period[period], atr_value)
            if hit is not None:
                events.append(hit)
    return sorted(events, key=lambda e: (e.index, e.ma_period))
