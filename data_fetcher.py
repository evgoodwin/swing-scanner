"""
data_fetcher.py — Downloads and caches OHLCV price history.
"""

import os, pickle, logging, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    CACHE_DIR, PRICE_CACHE_HOURS, HISTORY_DAYS,
    MAX_WORKERS, SECTOR_ETFS, MACRO_ASSETS, DEFAULT_BENCHMARK,
)

logger          = logging.getLogger(__name__)
PRICE_CACHE_DIR = os.path.join(CACHE_DIR, "prices")


def _path(ticker: str) -> str:
    safe = ticker.replace("^","_").replace("-","_")
    return os.path.join(PRICE_CACHE_DIR, f"{safe.upper()}.pkl")

def _fresh(ticker: str) -> bool:
    p = _path(ticker)
    if not os.path.exists(p): return False
    return datetime.now() - datetime.fromtimestamp(os.path.getmtime(p)) \
           < timedelta(hours=PRICE_CACHE_HOURS)

def _load(ticker: str) -> Optional[pd.DataFrame]:
    p = _path(ticker)
    if not os.path.exists(p): return None
    try:
        with open(p,"rb") as f: return pickle.load(f)
    except: return None

def _save(ticker: str, df: pd.DataFrame) -> None:
    os.makedirs(PRICE_CACHE_DIR, exist_ok=True)
    with open(_path(ticker),"wb") as f: pickle.dump(df, f)


def _download_single(ticker: str, days: int = HISTORY_DAYS) -> Optional[pd.DataFrame]:
    try:
        df = yf.Ticker(ticker).history(period=f"{days}d",
                                        auto_adjust=True, actions=False)
        if df is None or len(df) < 50: return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "Date"
        df = df[["Open","High","Low","Close","Volume"]].dropna(subset=["Close"])
        return df
    except Exception as e:
        logger.debug(f"Download failed {ticker}: {e}")
        return None


def fetch_price_data(tickers: list, force_refresh: bool = False,
                     progress_cb=None) -> dict:
    os.makedirs(PRICE_CACHE_DIR, exist_ok=True)
    result, to_dl = {}, []

    for t in tickers:
        if not force_refresh and _fresh(t):
            result[t] = _load(t)
        else:
            to_dl.append(t)

    logger.info(f"Price data: {len(result)} cached, {len(to_dl)} to download")
    if not to_dl:
        if progress_cb: progress_cb(len(tickers), len(tickers))
        return result

    done = len(result)
    total = len(tickers)

    def _worker(t):
        df = _download_single(t)
        if df is not None: _save(t, df)
        return t, df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_worker, t): t for t in to_dl}
        for fut in as_completed(futures):
            t, df = fut.result()
            result[t] = df
            done += 1
            if progress_cb: progress_cb(done, total)
            if done % 50 == 0: time.sleep(0.1)

    return result


def filter_by_volume(price_data: dict, min_avg_vol: int,
                     lookback: int = 50) -> list:
    return [
        t for t, df in price_data.items()
        if df is not None and len(df) >= lookback
        and df["Volume"].iloc[-lookback:].mean() >= min_avg_vol
    ]


def fetch_sector_data(force_refresh: bool = False,
                      benchmark: str = DEFAULT_BENCHMARK) -> dict:
    """Fetch sector ETFs + benchmark."""
    tickers = list(set(list(SECTOR_ETFS.values()) + [benchmark]))
    result  = {}
    for t in tickers:
        if not force_refresh and _fresh(t):
            result[t] = _load(t)
        else:
            df = _download_single(t)
            if df is not None: _save(t, df)
            result[t] = df
    return result


def fetch_macro_data(force_refresh: bool = False) -> dict:
    """Fetch all macro/indices assets + both benchmarks."""
    tickers = list(set(list(MACRO_ASSETS.values()) + ["QQQ", "SPY"]))
    result  = {}
    for t in tickers:
        if not force_refresh and _fresh(t):
            result[t] = _load(t)
        else:
            df = _download_single(t)
            if df is not None: _save(t, df)
            result[t] = df
    logger.info(f"Macro data: {sum(1 for v in result.values() if v is not None)}"
                f"/{len(tickers)} assets fetched")
    return result
