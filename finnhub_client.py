"""
finnhub_client.py — Lightweight Finnhub API client.

Current features (free tier):
  ✅ Earnings calendar  — upcoming earnings dates for all US stocks (1 API call)
  🔜 Basic financials   — PE, revenue/EPS growth (Phase 2)
  🔜 Analyst consensus  — buy/hold/sell ratings (Phase 2)
  🔜 Insider trading    — executive buy/sell activity (Phase 3)

Free tier limits: 60 API calls/minute
Sign up:  https://finnhub.io  (takes ~2 minutes, no credit card)
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE          = "https://finnhub.io/api/v1"
EARNINGS_CACHE_FILE   = os.path.join("cache", "finnhub_earnings.pkl")
EARNINGS_CACHE_HOURS  = 12   # Refresh earnings calendar twice a day


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get(endpoint: str, api_key: str, params: dict = None) -> dict:
    """Make a Finnhub API GET request. Raises on HTTP error."""
    p = dict(params or {})
    p["token"] = api_key
    r = requests.get(f"{FINNHUB_BASE}/{endpoint}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


def _cache_fresh(path: str, hours: float) -> bool:
    if not os.path.exists(path):
        return False
    age_sec = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))).total_seconds()
    return age_sec < hours * 3600


# ── Earnings Calendar ─────────────────────────────────────────────────────────

def get_earnings_calendar(
    api_key:       str,
    days_ahead:    int  = 30,
    force_refresh: bool = False,
) -> dict:
    """
    Fetch upcoming earnings dates for ALL US-listed stocks.

    Efficiency: this is ONE Finnhub API call regardless of how many stocks
    you're tracking — the API returns all companies reporting within the
    date range in a single response.

    Returns:
        dict  {ticker: {'date': 'YYYY-MM-DD', 'estimate': float | None}}

    Empty dict is returned gracefully if API key is missing or call fails.
    Cached for EARNINGS_CACHE_HOURS (default 12 hours).
    """
    if not api_key or not api_key.strip():
        return {}

    os.makedirs("cache", exist_ok=True)

    # ── Cache check ───────────────────────────────────────────────
    if not force_refresh and _cache_fresh(EARNINGS_CACHE_FILE, EARNINGS_CACHE_HOURS):
        try:
            with open(EARNINGS_CACHE_FILE, "rb") as f:
                cached = pickle.load(f)
            logger.info(f"Earnings calendar from cache: {len(cached)} events")
            return cached
        except Exception:
            pass   # Corrupted cache — re-fetch

    # ── Fetch from Finnhub ────────────────────────────────────────
    today = datetime.now().date()
    end   = today + timedelta(days=days_ahead)

    try:
        data = _get("calendar/earnings", api_key, {
            "from": today.strftime("%Y-%m-%d"),
            "to":   end.strftime("%Y-%m-%d"),
        })

        earnings = {}
        for item in data.get("earningsCalendar", []):
            ticker   = item.get("symbol", "").strip().upper()
            date_str = item.get("date", "")
            estimate = item.get("epsEstimate")
            hour     = item.get("hour", "")   # 'bmo' = before open, 'amc' = after close

            if ticker and date_str:
                earnings[ticker] = {
                    "date":     date_str,
                    "estimate": float(estimate) if estimate is not None else None,
                    "hour":     hour,   # bmo / amc / dmh (during market hours)
                }

        with open(EARNINGS_CACHE_FILE, "wb") as f:
            pickle.dump(earnings, f)

        logger.info(f"Finnhub earnings: {len(earnings)} events in next {days_ahead} days fetched")
        return earnings

    except requests.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("Finnhub API key invalid or expired — check config.py")
        elif e.response.status_code == 429:
            logger.warning("Finnhub rate limit hit — earnings data unavailable this run")
        else:
            logger.warning(f"Finnhub HTTP error: {e}")
        return {}

    except Exception as e:
        logger.warning(f"Finnhub earnings fetch failed: {e}")
        return {}


def days_until_earnings(ticker: str, earnings_dict: dict) -> Optional[int]:
    """
    Returns number of calendar days until next earnings for a ticker.
    Returns None if ticker not found in earnings calendar.
    Returns None if earnings date already passed.
    """
    info = earnings_dict.get(ticker.upper())
    if not info:
        return None
    try:
        earn_date = datetime.strptime(info["date"], "%Y-%m-%d").date()
        diff = (earn_date - datetime.now().date()).days
        return diff if diff >= 0 else None
    except Exception:
        return None


def earnings_label(days: Optional[int], hour: str = "") -> str:
    """
    Convert days-until-earnings to a display string.
    e.g.  3 → '3d ↑' (before open)  or  '3d ↓' (after close)
    """
    if days is None:
        return ""
    suffix = " ↑" if hour == "bmo" else " ↓" if hour == "amc" else "d"
    return f"{days}{suffix}"


# ── Validate API Key ──────────────────────────────────────────────────────────

def validate_api_key(api_key: str) -> bool:
    """Quick check that an API key is valid by fetching a minimal endpoint."""
    if not api_key or not api_key.strip():
        return False
    try:
        _get("stock/symbol", api_key, {"exchange": "US", "mic": "XNAS",
                                        "securityType": "Common Stock",
                                        "currency": "USD"})
        return True
    except Exception:
        return False
