"""
universe.py — Fetches and caches the full US stock universe.

Primary source: NASDAQ Screener API (returns ~2,500 stocks with price,
market cap, sector, industry — all the metadata we need in one call).

FTP sources are skipped as they are commonly blocked by firewalls/antivirus.
"""

import os
import pickle
import logging
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

from config import (
    CACHE_DIR,
    UNIVERSE_CACHE_HOURS,
    MIN_PRICE,
    MIN_MARKET_CAP,
)

logger = logging.getLogger(__name__)

SCREENER_URL  = "https://api.nasdaq.com/api/screener/stocks"
UNIVERSE_CACHE = os.path.join(CACHE_DIR, "universe.pkl")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/",
}


# ── NASDAQ Screener API ───────────────────────────────────────────────────────

def _fetch_screener() -> pd.DataFrame:
    """
    Fetch all US-listed stocks from NASDAQ Screener API.
    Returns a DataFrame with ticker, name, price, market_cap, sector, industry.
    The download=true parameter returns all records in one call.
    """
    params = {
        "tableonly": "true",
        "limit":     25,
        "offset":    0,
        "download":  "true",
    }
    r = requests.get(SCREENER_URL, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    if "data" not in data or "rows" not in data["data"]:
        raise RuntimeError("Unexpected NASDAQ screener response format")

    df = pd.DataFrame(data["data"]["rows"])

    col_map = {
        "symbol":    "ticker",
        "lastsale":  "price",
        "marketCap": "market_cap",
        "name":      "name",
        "sector":    "sector",
        "industry":  "industry",
        "country":   "country",
        "volume":    "volume",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return df


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_price(val) -> float:
    if val is None: return np.nan
    s = str(val).strip().replace("$", "").replace(",", "")
    try:    return float(s)
    except: return np.nan


def _parse_mcap(val) -> float:
    """Parse '$1.23B', '456M', '12.3T' → float."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    s = str(val).strip().replace("$", "").replace(",", "").upper()
    if not s or s in ("N/A", "-", ""):
        return np.nan
    for suffix, mult in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if s.endswith(suffix):
            try:    return float(s[:-1]) * mult
            except: return np.nan
    try:    return float(s)
    except: return np.nan


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and filter the raw DataFrame from the screener."""
    df = df.copy()

    # Normalize ticker
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    # Keep only clean common-stock tickers (1–5 uppercase letters, no dots/dashes)
    df = df[df["ticker"].str.match(r"^[A-Z]{1,5}$", na=False)]

    # Filter to US stocks only (if country column present)
    if "country" in df.columns:
        df = df[df["country"].str.strip().str.upper() == "UNITED STATES"]

    # Parse and filter price
    if "price" in df.columns:
        df["price"] = df["price"].apply(_parse_price)
        df = df[df["price"].isna() | (df["price"] >= MIN_PRICE)]

    # Parse and filter market cap
    if "market_cap" in df.columns:
        df["market_cap"] = df["market_cap"].apply(_parse_mcap)
        df = df[df["market_cap"].isna() | (df["market_cap"] >= MIN_MARKET_CAP)]

    # Clean sector — replace empty strings with NaN
    if "sector" in df.columns:
        df["sector"] = df["sector"].replace("", np.nan).replace("NA", np.nan)

    df = df.drop_duplicates(subset="ticker").reset_index(drop=True)
    return df


# ── Public API ────────────────────────────────────────────────────────────────

def get_universe(force_refresh: bool = False) -> pd.DataFrame:
    """
    Return the filtered US stock universe as a DataFrame.

    Guaranteed columns: ticker
    Available columns:  name, price, market_cap, sector, industry

    Cached for UNIVERSE_CACHE_HOURS (default 24 hours).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    # ── Cache check ───────────────────────────────────────────────
    if not force_refresh and os.path.exists(UNIVERSE_CACHE):
        age = datetime.now() - datetime.fromtimestamp(
            os.path.getmtime(UNIVERSE_CACHE)
        )
        if age < timedelta(hours=UNIVERSE_CACHE_HOURS):
            with open(UNIVERSE_CACHE, "rb") as f:
                universe = pickle.load(f)
            logger.info(f"Universe from cache: {len(universe)} tickers")
            return universe

    # ── Fetch fresh from NASDAQ Screener ─────────────────────────
    logger.info("Fetching universe from NASDAQ Screener API…")
    try:
        df = _fetch_screener()
        df = _clean(df)
        logger.info(f"Universe fetched: {len(df)} tickers")
    except Exception as e:
        logger.error(f"Screener fetch failed: {e}")
        # If cache exists (even stale), use it rather than crashing
        if os.path.exists(UNIVERSE_CACHE):
            logger.warning("Using stale cache as fallback")
            with open(UNIVERSE_CACHE, "rb") as f:
                return pickle.load(f)
        raise

    with open(UNIVERSE_CACHE, "wb") as f:
        pickle.dump(df, f)

    return df


def get_ticker_list(force_refresh: bool = False) -> list:
    return get_universe(force_refresh=force_refresh)["ticker"].tolist()
