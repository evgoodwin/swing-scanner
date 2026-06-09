"""
config.py — All user-configurable parameters for the Swing Scanner.
"""

# ── Universe Filters ──────────────────────────────────────────────
MIN_PRICE             = 10.0
MIN_AVG_VOLUME_50D    = 500_000
MIN_MARKET_CAP        = 1_000_000_000

# ── Core MA Periods (always active) ──────────────────────────────
EMA_8_PERIOD   = 8
EMA_20_PERIOD  = 20
SMA_50_PERIOD  = 50
SMA_200_PERIOD = 200

# ── Optional MA Periods (calculated always, filter/stack toggleable)
EMA_3_PERIOD  = 3
HMA_90_PERIOD = 90

# ── Weekly MA Periods ─────────────────────────────────────────────
WEEKLY_SMA_SHORT = 10
WEEKLY_SMA_LONG  = 40

# ── MA Stack Labels (fastest → slowest, defines score pair order) ─
MA_PERIOD_ORDER = ["3E", "8E", "20E", "50S", "H90", "200S"]
PRICE_LABEL     = "【$】"   # visually distinct price marker in stack string

# ── RS / Benchmark ────────────────────────────────────────────────
RS_BENCHMARKS     = {"QQQ — NASDAQ 100 (default)": "QQQ",
                     "SPY — S&P 500":               "SPY"}
DEFAULT_BENCHMARK = "QQQ"
RS_Q1_WEIGHT = 0.40
RS_Q2_WEIGHT = 0.20
RS_Q3_WEIGHT = 0.20
RS_Q4_WEIGHT = 0.20

# ── Sector ETFs ───────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technology":             "XLK",
    "Healthcare":             "XLV",
    "Financials":             "XLF",
    "Consumer Discretionary": "XLY",
    "Industrials":            "XLI",
    "Communication Services": "XLC",
    "Consumer Staples":       "XLP",
    "Energy":                 "XLE",
    "Materials":              "XLB",
    "Real Estate":            "XLRE",
    "Utilities":              "XLU",
}

# ── Sector Name Normalisation ─────────────────────────────────────
# Maps every known NASDAQ screener variant → our ETF dict key
# All comparisons are lower-cased before lookup
SECTOR_NAME_MAP = {
    # Healthcare
    "health care":                "Healthcare",
    "healthcare":                 "Healthcare",
    # Consumer Discretionary
    "consumer cyclical":          "Consumer Discretionary",
    "consumer discretionary":     "Consumer Discretionary",
    # Financials
    "financial services":         "Financials",
    "financials":                 "Financials",
    "finance":                    "Financials",
    # Materials
    "basic materials":            "Materials",
    "materials":                  "Materials",
    # Consumer Staples
    "consumer defensive":         "Consumer Staples",
    "consumer staples":           "Consumer Staples",
    # Others (usually already correct)
    "communication services":     "Communication Services",
    "technology":                 "Technology",
    "industrials":                "Industrials",
    "industrial":                 "Industrials",
    "energy":                     "Energy",
    "real estate":                "Real Estate",
    "utilities":                  "Utilities",
    "utility":                    "Utilities",
    # Telecom variants → Communication Services
    "telecommunications":         "Communication Services",
    "telecommunication services": "Communication Services",
    "telecom":                    "Communication Services",
    "communication":              "Communication Services",
}

# ── Macro / Indices Assets ────────────────────────────────────────
MACRO_ASSETS = {
    "S&P 500":       "SPY",
    "NASDAQ 100":    "QQQ",
    "Russell 2000":  "IWM",
    "Dow Jones":     "DIA",
    "Gold":          "GLD",
    "Silver":        "SLV",
    "Crude Oil":     "USO",
    "Bitcoin":       "BTC-USD",
    "US Dollar":     "UUP",
    "20Y Treasury":  "TLT",
    "10Y Treasury":  "IEF",
    "VIX":           "^VIX",
}

VIX_GREEN  = 15   # Below = calm / bullish conditions
VIX_YELLOW = 25   # Above = elevated fear

# ── Finnhub API Settings ─────────────────────────────────────────
# Free API key from https://finnhub.io  (takes 2 minutes to register)
# Leave blank to skip earnings data — scanner works fine without it.
FINNHUB_API_KEY       = ""
EARNINGS_DAYS_AHEAD   = 30   # Scan this many calendar days ahead for earnings
EARNINGS_WARN_DAYS    = 7    # 🔴 Red if earnings within this many days
EARNINGS_CAUTION_DAYS = 14   # 🟡 Yellow if earnings within this many days

# ── Cache / Data Settings ─────────────────────────────────────────
CACHE_DIR            = "cache"
UNIVERSE_CACHE_HOURS = 24
PRICE_CACHE_HOURS    = 1
HISTORY_DAYS         = 380
BATCH_SIZE           = 100
MAX_WORKERS          = 8

# ── UI Defaults ───────────────────────────────────────────────────
DEFAULT_RS_PERCENTILE = 85
DEFAULT_TOP_N_SECTORS = 5
MAX_TABLE_ROWS        = 300
