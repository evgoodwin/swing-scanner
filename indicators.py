"""
indicators.py — All technical indicator calculations.
"""

import numpy as np
import pandas as pd
from config import MA_PERIOD_ORDER


# ── Core MAs ──────────────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()

def wma(series: pd.Series, period: int) -> pd.Series:
    weights    = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()
    def _w(x): return float(np.dot(x, weights) / weight_sum)
    return series.rolling(window=period, min_periods=period).apply(_w, raw=True)

def hma(series: pd.Series, period: int = 90) -> pd.Series:
    """Hull Moving Average: HMA(n) = WMA(2·WMA(n/2) − WMA(n), √n)"""
    half  = max(int(period / 2), 2)
    sqrtn = max(round(np.sqrt(period)), 2)
    return wma(2.0 * wma(series, half) - wma(series, period), sqrtn)


# ── Bollinger %B ──────────────────────────────────────────────────

def bollinger_pct_b(series: pd.Series, period: int = 50,
                    num_std: float = 1.0) -> pd.Series:
    """
    %B = (Price - Lower) / (Upper - Lower)  using BB(period, num_std)
    Key levels:  1.0 = upper band (Buy line in the sand)
                 0.5 = middle (SMA)
                 0.0 = lower band
    """
    mid   = sma(series, period)
    std   = series.rolling(period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    bw    = upper - lower
    return ((series - lower) / bw).where(bw > 0, np.nan)


# ── Weekly Resample ───────────────────────────────────────────────

def resample_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    return daily_df.resample("W-FRI").agg({
        "Open": "first", "High": "max",
        "Low":  "min",   "Close": "last", "Volume": "sum",
    }).dropna(subset=["Close"])


# ── IBD-Style RS ──────────────────────────────────────────────────

def ibd_rs_raw(stock_close: pd.Series, bench_close: pd.Series,
               q1=0.40, q2=0.20, q3=0.20, q4=0.20) -> float:
    c = pd.concat([stock_close.rename("s"), bench_close.rename("b")],
                  axis=1, join="inner").dropna()
    if len(c) < 200:
        return np.nan
    c = c.iloc[-252:]
    n = len(c)
    q = n // 4

    def _r(col, s, e):
        if e <= s: return 0.0
        return float((1 + c[col].iloc[s:e].pct_change().dropna()).prod() - 1)

    segs = [(n-q,n),(n-2*q,n-q),(n-3*q,n-2*q),(0,n-3*q)]
    ws   = [q1, q2, q3, q4]
    return sum(w*(_r("s",s,e)-_r("b",s,e)) for (s,e),w in zip(segs,ws))


def percentile_rank(series: pd.Series) -> pd.Series:
    return series.rank(pct=True).mul(98).add(1).clip(1,99).round(1)


# ── Dynamic MA Stack ──────────────────────────────────────────────

def compute_ma_stack(
    price:         float,
    ma_values:     dict,   # {label: float}  ALL calculated MAs
    active_labels: list,   # labels currently toggled ON
    period_order:  list,   # fastest→slowest label order (for score)
) -> tuple:
    """
    Returns (score_str, stack_str)

    score_str  : "4/4"  — fraction of consecutive pairs in correct bullish order
                          considers only price + active MAs
    stack_str  : dynamic string ordered by actual current value (high→low)
                 active MA labels shown as-is, inactive in parentheses
                 $ = price position
                 e.g.  (3E)-8E-$-20E-50S-(H90)-200S

    Bullish interpretation:
      score_str  numerator == denominator  →  fully stacked ✅
      $ near left of string  →  price leading all MAs  ✅
    """
    from config import PRICE_LABEL as _PL
    # Build value dict (all MAs + price)
    all_vals = {_PL: price}
    for label, val in ma_values.items():
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            all_vals[label] = float(val)

    # Sort by value descending = top-of-chart to bottom
    sorted_items = sorted(all_vals.items(), key=lambda x: x[1], reverse=True)

    # Build stack string
    parts = []
    for label, _ in sorted_items:
        if label == _PL:
            parts.append(_PL)
        elif label in active_labels:
            parts.append(label)
        else:
            parts.append(f"({label})")
    stack_str = "-".join(parts)

    # Score: consecutive pairs in period_order among active items
    seq = [_PL] + [l for l in period_order if l in active_labels]
    n_pairs = len(seq) - 1
    if n_pairs == 0:
        return "N/A", stack_str

    correct = sum(
        1 for i in range(n_pairs)
        if all_vals.get(seq[i], -999) > all_vals.get(seq[i+1], -999)
    )
    return f"{correct}/{n_pairs}", stack_str


# ── Pct Changes (for macro table) ────────────────────────────────

def pct_change_over(series: pd.Series, bars: int) -> float:
    """% change over last `bars` trading days."""
    if len(series) < bars + 1:
        return np.nan
    return round((series.iloc[-1] / series.iloc[-bars-1] - 1) * 100, 2)


def pct_change_ytd(series: pd.Series) -> float:
    """% change from first trading day of current calendar year to today."""
    import datetime
    year_start = pd.Timestamp(datetime.date.today().year, 1, 1)
    ytd = series[series.index >= year_start]
    if len(ytd) < 2:
        return np.nan
    return round((float(series.iloc[-1]) / float(ytd.iloc[0]) - 1) * 100, 2)


# ── Full Indicator Snapshot ───────────────────────────────────────

def compute_stock_indicators(daily_df: pd.DataFrame,
                              weekly_df: pd.DataFrame,
                              use_3ema:  bool = False,
                              use_hma90: bool = True) -> dict:
    """
    Compute all indicators for a single stock.

    use_3ema  : whether 3 EMA is toggled on (affects filter flags + stack score)
    use_hma90 : whether 90 HMA is toggled on (affects filter flags + stack score)
    """
    out = {}

    if daily_df is None or len(daily_df) < 210:
        return {k: np.nan for k in _KEYS}

    close  = daily_df["Close"]
    volume = daily_df.get("Volume")

    # ── Daily MAs ─────────────────────────────────────────────────
    out["ema_3"]   = float(ema(close,  3).iloc[-1])
    out["ema_8"]   = float(ema(close,  8).iloc[-1])
    out["ema_20"]  = float(ema(close, 20).iloc[-1])
    out["sma_50"]  = float(sma(close, 50).iloc[-1])
    out["hma_90"]  = float(hma(close, 90).iloc[-1])
    out["sma_200"] = float(sma(close,200).iloc[-1])
    out["price"]   = float(close.iloc[-1])

    # ── Bollinger %B (50,1) ───────────────────────────────────────
    out["pct_b"] = round(float(bollinger_pct_b(close, 50, 1.0).iloc[-1]), 2)

    # ── 52-Week High & Distance ───────────────────────────────────
    lb = min(252, len(daily_df))
    h52 = float(daily_df["High"].iloc[-lb:].max())
    out["high_52w"]      = h52
    out["pct_from_52wh"] = round((out["price"]/h52 - 1)*100, 2) if h52 > 0 else np.nan

    # ── Volume & Relative Volume ──────────────────────────────────
    if volume is not None:
        avg50          = float(volume.rolling(50).mean().iloc[-1])
        out["avg_vol_50"] = avg50
        out["rel_vol"]    = round(float(volume.iloc[-1]) / avg50, 2) if avg50 > 0 else np.nan
    else:
        out["avg_vol_50"] = out["rel_vol"] = np.nan

    # ── Weekly MAs ────────────────────────────────────────────────
    if weekly_df is not None and len(weekly_df) >= 40:
        wc = weekly_df["Close"]
        out["w_sma_10"] = float(sma(wc, 10).iloc[-1])
        out["w_sma_40"] = float(sma(wc, 40).iloc[-1])
        out["w_close"]  = float(wc.iloc[-1])
    else:
        out["w_sma_10"] = out["w_sma_40"] = out["w_close"] = np.nan

    # ── MA Stack ──────────────────────────────────────────────────
    # H90 is always informational (shown in parens in string, never in score).
    # It appears as (H90) regardless of use_hma90 toggle.
    # use_hma90 only controls the hard ENTRY FILTER, not the stack.
    ma_vals = {
        "3E":   out["ema_3"],
        "8E":   out["ema_8"],
        "20E":  out["ema_20"],
        "50S":  out["sma_50"],
        "H90":  out["hma_90"],   # always in ma_vals so it appears in string as (H90)
        "200S": out["sma_200"],
    }
    # Active = core MAs + optional 3E (if toggled). H90 never active in stack.
    active = ["8E", "20E", "50S", "200S"]
    if use_3ema: active.insert(0, "3E")
    active = [l for l in MA_PERIOD_ORDER if l in active]

    out["stack_score"], out["stack_str"] = compute_ma_stack(
        out["price"], ma_vals, active, MA_PERIOD_ORDER
    )

    # ── HMA90 % Distance ──────────────────────────────────────────
    # Positive = price above HMA (green), Negative = price below HMA (red)
    h90 = out["hma_90"]
    _h90_valid = (h90 is not None
                  and not (isinstance(h90, float) and np.isnan(h90))
                  and h90 != 0)
    out["hma_dist_pct"] = round((out["price"] / h90 - 1) * 100, 2)         if _h90_valid else np.nan

    # ── Filter Flags ──────────────────────────────────────────────
    p = out["price"]
    def _ok(v): return v is not None and not (isinstance(v, float) and np.isnan(v))

    out["above_sma50"]  = bool(p > out["sma_50"])  if _ok(out["sma_50"])  else False
    out["above_sma200"] = bool(p > out["sma_200"]) if _ok(out["sma_200"]) else False
    out["above_hma90"]  = bool(p > out["hma_90"])  if _ok(out["hma_90"])  else False
    out["ema3_gt_ema8"] = bool(out["ema_3"] > out["ema_8"]) \
        if _ok(out["ema_3"]) and _ok(out["ema_8"]) else False

    wk10 = out["w_sma_10"]; wk40 = out["w_sma_40"]; wc = out["w_close"]
    out["weekly_trend_ok"] = (
        _ok(wk10) and _ok(wk40) and _ok(wc) and wc > wk10 and wk10 > wk40
    )
    return out


_KEYS = [
    "ema_3","ema_8","ema_20","sma_50","hma_90","sma_200","price",
    "pct_b","high_52w","pct_from_52wh","avg_vol_50","rel_vol",
    "hma_dist_pct",
    "w_sma_10","w_sma_40","w_close",
    "stack_score","stack_str",
    "above_sma50","above_sma200","above_hma90","ema3_gt_ema8","weekly_trend_ok",
]
