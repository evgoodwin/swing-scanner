"""
swing_risk.stops
================
Auto-suggested stop levels (§4.6 stop_suggestions), computed from an OHLCV
DataFrame with columns: open, high, low, close, volume (datetime index,
ascending). Works on any timeframe (daily equities, H4 crypto -- P4).

Suggestions produced:
  SWING_LOW  - most recent confirmed swing low (5-step framework, step 1)
  SMA50      - 50-period simple MA (MTG structural level)
  ATR        - entry minus k*ATR(14) (volatility stop, default k=2)
  HMA90      - 90-period Hull MA  [overlay: Ev-Exp ruleset]

Each suggestion returns level, distance % from entry, and a note.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import StopSuggestion


# ----------------------------------------------------------------------------
# Indicator helpers
# ----------------------------------------------------------------------------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def hma(s: pd.Series, n: int) -> pd.Series:
    """Hull Moving Average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = max(int(n / 2), 1)
    root = max(int(np.sqrt(n)), 1)
    return wma(2 * wma(s, half) - wma(s, n), root)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def last_swing_low(df: pd.DataFrame, left: int = 3, right: int = 3) -> float | None:
    """
    Most recent confirmed swing low: a bar whose low is lower than `left`
    bars before and `right` bars after it. Confirmation requires `right`
    subsequent bars, so the most recent `right` bars can't qualify (by design:
    an unconfirmed low is not a stop basis).
    """
    lows = df["low"].to_numpy()
    n = len(lows)
    for i in range(n - right - 1, left - 1, -1):
        window_l = lows[i - left:i]
        window_r = lows[i + 1:i + 1 + right]
        if len(window_r) < right:
            continue
        if lows[i] < window_l.min() and lows[i] <= window_r.min():
            return float(lows[i])
    return None


# ----------------------------------------------------------------------------
# Suggestion engine
# ----------------------------------------------------------------------------

def suggest_stops(
    df: pd.DataFrame,
    entry_price: float,
    direction: str = "LONG",
    include_overlays: bool = True,
    atr_mult: float = 2.0,
) -> list[StopSuggestion]:
    """
    Return stop suggestions sorted nearest-first below entry (for LONG).
    SHORT direction mirrors above entry (Phase 7 ready).
    """
    if df is None or len(df) < 60:
        return []

    close = df["close"]
    out: list[StopSuggestion] = []
    long_side = direction.upper() == "LONG"

    def add(basis: str, level: float | None, note: str, overlay: bool = False):
        if level is None or not np.isfinite(level) or level <= 0:
            return
        # a valid stop must be on the protective side of entry
        if long_side and level >= entry_price:
            return
        if not long_side and level <= entry_price:
            return
        dist = abs(entry_price - level) / entry_price * 100.0
        out.append(StopSuggestion(basis=basis, level=round(float(level), 2),
                                  distance_pct=round(dist, 2), note=note,
                                  is_overlay=overlay))

    swing = last_swing_low(df) if long_side else None  # short swing-high TBD Phase 7
    add("SWING_LOW", swing, "Most recent confirmed swing low (5-step framework)")

    e20 = ema(close, 20).iloc[-1]
    add("EMA20", e20, "20-period EMA (MTG primary stop zone)")

    e8 = ema(close, 8).iloc[-1]
    add("EMA8", e8, "8-period EMA (fast momentum line)")

    s50 = sma(close, 50).iloc[-1]
    add("SMA50", s50, "50-period SMA structural level")

    a = atr(df, 14).iloc[-1]
    if np.isfinite(a):
        lvl = entry_price - atr_mult * a if long_side else entry_price + atr_mult * a
        add("ATR", lvl, f"{atr_mult:.1f}x ATR(14) volatility stop")

    if include_overlays and len(df) >= 100:
        h90 = hma(close, 90).iloc[-1]
        add("HMA90", h90, "90-period Hull MA [overlay: Ev-Exp]", overlay=True)

    # nearest (tightest) first
    out.sort(key=lambda s: s.distance_pct)
    return out
