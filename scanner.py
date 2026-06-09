"""
scanner.py — Full scan pipeline.
"""

import logging
from typing import Callable, Optional

import numpy as np
import pandas as pd

from config import (
    MIN_PRICE, MIN_AVG_VOLUME_50D, MIN_MARKET_CAP,
    SECTOR_ETFS, SECTOR_NAME_MAP,
    DEFAULT_BENCHMARK,
    RS_Q1_WEIGHT, RS_Q2_WEIGHT, RS_Q3_WEIGHT, RS_Q4_WEIGHT,
    DEFAULT_RS_PERCENTILE, DEFAULT_TOP_N_SECTORS,
    FINNHUB_API_KEY, EARNINGS_DAYS_AHEAD,
    EARNINGS_WARN_DAYS, EARNINGS_CAUTION_DAYS,
)
from finnhub_client import get_earnings_calendar, days_until_earnings
from indicators import (
    compute_stock_indicators, resample_to_weekly,
    ibd_rs_raw, percentile_rank,
)
from universe import get_universe
from data_fetcher import fetch_price_data, fetch_sector_data, filter_by_volume

logger = logging.getLogger(__name__)


def _norm_sector(name: str) -> str:
    """Normalise NASDAQ screener sector names to our ETF dict keys."""
    if not isinstance(name, str): return name
    return SECTOR_NAME_MAP.get(name.strip().lower(), name.strip())


def rank_sectors(sector_price_data: dict, benchmark: str) -> pd.DataFrame:
    bench_df = sector_price_data.get(benchmark)
    if bench_df is None:
        return pd.DataFrame()
    bench_close = bench_df["Close"]
    rows = []
    for sector_name, etf in SECTOR_ETFS.items():
        df = sector_price_data.get(etf)
        if df is None or len(df) < 200: continue
        raw = ibd_rs_raw(df["Close"], bench_close,
                         RS_Q1_WEIGHT, RS_Q2_WEIGHT, RS_Q3_WEIGHT, RS_Q4_WEIGHT)
        rows.append({"sector": sector_name, "etf": etf, "rs_raw": raw})
    if not rows: return pd.DataFrame()
    result = pd.DataFrame(rows)
    result["rs_pct"]      = percentile_rank(result["rs_raw"])
    result                = result.sort_values("rs_pct", ascending=False).reset_index(drop=True)
    result["sector_rank"] = result.index + 1
    return result


def run_scan(
    force_refresh:     bool  = False,
    rs_min_pct:        float = DEFAULT_RS_PERCENTILE,
    top_n_sectors:     int   = DEFAULT_TOP_N_SECTORS,
    require_hma90:     bool  = True,
    use_3ema_stack:    bool  = False,
    require_ema_align: bool  = False,
    benchmark:         str   = DEFAULT_BENCHMARK,
    min_price:         float = MIN_PRICE,
    min_vol:           int   = MIN_AVG_VOLUME_50D,
    min_market_cap:    float = MIN_MARKET_CAP,
    finnhub_key:       str   = FINNHUB_API_KEY,
    status_cb: Optional[Callable[[str, float], None]] = None,
) -> tuple:
    """
    Returns (results_df, sector_ranks_df, filter_counts_dict)

    require_hma90   : HMA90 as hard entry filter
    use_3ema_stack  : include 3 EMA in stack score/string (no hard filter impact)
    require_ema_align: 3 EMA > 8 EMA as hard filter
    benchmark       : 'QQQ' or 'SPY'
    min_price       : minimum stock price ($) — sidebar control
    min_vol         : minimum 50-day avg volume — sidebar control
    min_market_cap  : minimum market cap ($) — sidebar control
    finnhub_key     : Finnhub API key for earnings data (optional)
    """

    def _s(msg, pct):
        logger.info(msg)
        if status_cb: status_cb(msg, pct)

    # ── Phase 1: Universe ─────────────────────────────────────────
    _s("📋 Phase 1/6 — Loading universe…", 0.02)
    universe_df = get_universe(force_refresh=force_refresh)

    # Normalise sector names
    if "sector" in universe_df.columns:
        universe_df["sector"] = universe_df["sector"].apply(_norm_sector)

    if "price" in universe_df.columns:
        universe_df = universe_df[
            universe_df["price"].isna() | (universe_df["price"] >= min_price)
        ]
    if "market_cap" in universe_df.columns:
        universe_df = universe_df[
            universe_df["market_cap"].isna() | (universe_df["market_cap"] >= min_market_cap)
        ]
    tickers = universe_df["ticker"].tolist()
    _s(f"   Universe: {len(tickers)} tickers", 0.05)

    # ── Fetch benchmark + sector ETFs FIRST ──────────────────────
    _s(f"📊 Fetching {benchmark} & sector ETFs first…", 0.06)
    sector_data = fetch_sector_data(force_refresh=force_refresh,
                                    benchmark=benchmark)
    bench_df    = sector_data.get(benchmark)
    if bench_df is not None:
        _s(f"   {benchmark}: {len(bench_df)} bars ✅", 0.07)
    else:
        _s(f"   ⚠️ {benchmark} download failed — RS unavailable", 0.07)

    # ── Phase 2: Download + Volume ────────────────────────────────
    _s(f"⬇️  Phase 2/6 — Downloading {len(tickers)} stocks…", 0.08)

    def _prog(cur, tot):
        pct = 0.08 + (cur / max(tot,1)) * 0.35
        if cur % 200 == 0 or cur == tot:
            _s(f"   Downloaded {cur}/{tot}…", pct)

    price_data = fetch_price_data(tickers, force_refresh=force_refresh,
                                  progress_cb=_prog)

    _s("🔍 Applying volume filter…", 0.44)
    vol_passing = filter_by_volume(price_data, min_avg_vol=min_vol)
    _s(f"   After volume filter: {len(vol_passing)} tickers", 0.45)

    # ── Phase 3: Indicators ───────────────────────────────────────
    _s("📐 Phase 3/6 — Calculating indicators…", 0.46)
    rows = []
    for i, ticker in enumerate(vol_passing):
        daily = price_data.get(ticker)
        if daily is None or len(daily) < 210: continue
        if float(daily["Close"].iloc[-1]) < min_price: continue

        weekly = resample_to_weekly(daily)
        ind    = compute_stock_indicators(daily, weekly,
                                          use_3ema=use_3ema_stack,
                                          use_hma90=require_hma90)
        ind["ticker"]     = ticker
        ind["avg_vol_50"] = float(daily["Volume"].rolling(50).mean().iloc[-1])
        rows.append(ind)

        if (i+1) % 200 == 0:
            _s(f"   Indicators: {i+1}/{len(vol_passing)}…",
               0.46 + (i+1)/max(len(vol_passing),1)*0.14)

    ind_df = pd.DataFrame(rows)
    if ind_df.empty:
        _s("⚠️ No stocks survived indicator calculation.", 1.0)
        return pd.DataFrame(), pd.DataFrame(), {}

    # ── Phase 4: MA Filters ───────────────────────────────────────
    _s("🔽 Phase 4/6 — Applying MA filters…", 0.62)
    fc = {
        "total_with_indicators": len(ind_df),
        "above_sma50":    int(ind_df["above_sma50"].sum()),
        "above_sma200":   int(ind_df["above_sma200"].sum()),
        "above_hma90":    int(ind_df["above_hma90"].sum()),
        "weekly_trend":   int(ind_df["weekly_trend_ok"].sum()),
        "ema3_gt_ema8":   int(ind_df["ema3_gt_ema8"].sum()),
    }
    _s(f"   >SMA50:{fc['above_sma50']}  >SMA200:{fc['above_sma200']}  "
       f">HMA90:{fc['above_hma90']}  Weekly✓:{fc['weekly_trend']}  "
       f"3>8EMA:{fc['ema3_gt_ema8']}", 0.63)

    mask = (ind_df["above_sma50"] & ind_df["above_sma200"]
            & ind_df["weekly_trend_ok"])
    if require_hma90:     mask &= ind_df["above_hma90"]
    if require_ema_align: mask &= ind_df["ema3_gt_ema8"]

    ind_df = ind_df[mask].reset_index(drop=True)
    _s(f"   Passed MA gate: {len(ind_df)} stocks", 0.64)
    fc["passed_ma_filter"] = len(ind_df)

    if ind_df.empty:
        _s("⚠️ No stocks passed MA filters.", 1.0)
        return pd.DataFrame(), rank_sectors(sector_data, benchmark), fc

    # ── Phase 5: RS ───────────────────────────────────────────────
    _s(f"📈 Phase 5/6 — RS vs {benchmark}…", 0.65)

    if bench_df is None:
        _s(f"   ⚠️ {benchmark} unavailable — skipping RS filter", 0.70)
        ind_df["rs_raw"] = np.nan; ind_df["rs_pct"] = np.nan
        fc["rs_available"] = False
        fc["passed_rs_filter"] = len(ind_df)
    else:
        bench_close = bench_df["Close"]
        scores = []
        for ticker in ind_df["ticker"]:
            df  = price_data.get(ticker)
            raw = np.nan
            if df is not None and len(df) >= 200:
                raw = ibd_rs_raw(df["Close"], bench_close,
                                 RS_Q1_WEIGHT, RS_Q2_WEIGHT,
                                 RS_Q3_WEIGHT, RS_Q4_WEIGHT)
            scores.append(raw)
        ind_df["rs_raw"] = scores
        ind_df["rs_pct"] = percentile_rank(pd.Series(scores)).values
        fc["rs_available"] = True

        before = len(ind_df)
        ind_df = ind_df[
            ind_df["rs_pct"].isna() | (ind_df["rs_pct"] >= rs_min_pct)
        ].reset_index(drop=True)
        _s(f"   After RS ≥ {rs_min_pct}: {len(ind_df)} (was {before})", 0.80)
        fc["passed_rs_filter"] = len(ind_df)

    # ── Phase 6: Sector Ranking ───────────────────────────────────
    _s("🏭 Phase 6/6 — Ranking sectors…", 0.82)
    sector_ranks = rank_sectors(sector_data, benchmark)

    # Merge metadata
    meta = ["ticker"] + [c for c in ["name","sector","industry"]
                         if c in universe_df.columns]
    ind_df = ind_df.merge(
        universe_df[meta].drop_duplicates("ticker"),
        on="ticker", how="left",
    )
    # Normalise sector in merged results too
    if "sector" in ind_df.columns:
        ind_df["sector"] = ind_df["sector"].apply(_norm_sector)

    if not sector_ranks.empty and "sector" in ind_df.columns:
        ind_df = ind_df.merge(
            sector_ranks[["sector","sector_rank","rs_pct"]].rename(
                columns={"rs_pct":"sector_rs_pct"}),
            on="sector", how="left",
        )
        if top_n_sectors and "sector_rank" in ind_df.columns:
            ind_df = ind_df[
                ind_df["sector_rank"].isna() | (ind_df["sector_rank"] <= top_n_sectors)
            ]
    else:
        ind_df["sector_rank"]   = np.nan
        ind_df["sector_rs_pct"] = np.nan

    # ── Earnings Calendar (Finnhub) ──────────────────────────────
    _s("📅 Fetching earnings calendar…", 0.92)
    earnings_dict = get_earnings_calendar(
        finnhub_key, days_ahead=EARNINGS_DAYS_AHEAD,
        force_refresh=force_refresh,
    )
    if earnings_dict:
        ind_df["earn_days"] = ind_df["ticker"].apply(
            lambda t: days_until_earnings(t, earnings_dict)
        )
        _s(f"   Earnings data: {ind_df['earn_days'].notna().sum()} stocks with upcoming earnings", 0.94)
    else:
        ind_df["earn_days"] = np.nan
        if finnhub_key:
            _s("   ⚠️ Finnhub unavailable — earnings column empty", 0.94)
        else:
            _s("   ℹ️ No Finnhub key — earnings column skipped", 0.94)

    fc["final_results"] = len(ind_df)

    # Sort: sector_rank ASC → rs_pct DESC
    scols, sasc = [], []
    if "sector_rank" in ind_df.columns: scols.append("sector_rank"); sasc.append(True)
    if "rs_pct" in ind_df.columns and fc.get("rs_available"):
        scols.append("rs_pct"); sasc.append(False)
    if scols:
        ind_df = ind_df.sort_values(scols, ascending=sasc).reset_index(drop=True)

    _s(f"✅ Scan complete — {len(ind_df)} stocks", 1.0)
    return ind_df, sector_ranks, fc
