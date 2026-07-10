"""Synthetic price fixtures for double-bottom tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradingagents.dataflows.oneil_double_bottom import detect_double_bottom


def _line(values: list[float], end: float, bars: int) -> None:
    values.extend(np.linspace(values[-1], end, bars + 1)[1:].tolist())


def w_frame(
    *,
    first: float = 70,
    second: float = 69,
    middle: float = 88,
    prior_gain: float = 50,
    leg: int = 40,
    cross: int = 20,
    down: int = 20,
    tail: int = 15,
    recovery: float | None = None,
    rising_leg_volume: bool = False,
    base_volume: float = 350_000,
    minor_dip: bool = False,
) -> pd.DataFrame:
    close = np.linspace(50, 50 + prior_gain, 45).tolist()
    if minor_dip:
        _line(close, 78, 10)
        _line(close, 82, 7)
        leg -= 17
    _line(close, first, leg)
    first_index = len(close) - 1
    _line(close, middle, cross)
    _line(close, second, down)
    target = min(middle - 4, second + 12) if recovery is None else recovery
    _line(close, target, tail)
    volume = np.full(len(close), 1_000_000.0)
    volume[44 : first_index + 1] = np.linspace(
        500_000 if rising_leg_volume else 900_000,
        1_100_000 if rising_leg_volume else 450_000,
        first_index - 43,
    )
    volume[first_index + 1 :] = base_volume
    prices = np.asarray(close)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2023-01-02", periods=len(prices)),
            "Open": prices,
            "High": prices + 0.5,
            "Low": prices - 0.5,
            "Close": prices,
            "Volume": volume,
        }
    )


def detect(frame: pd.DataFrame | None = None, **kwargs: object):
    return detect_double_bottom(frame if frame is not None else w_frame(**kwargs), 1.0)


def delay_reclaim(frame: pd.DataFrame, bars: int = 11) -> pd.DataFrame:
    second = int(frame["Low"].iloc[45:].idxmin())
    indexes = range(second + 1, min(second + 1 + bars, len(frame)))
    for index in indexes:
        close = frame.loc[index, "Close"]
        held = min(close, frame.loc[second, "Close"] + 0.4)
        frame.loc[index, ["Open", "Close", "High", "Low"]] = [held, held, held + 0.5, held - 0.4]
    return frame
