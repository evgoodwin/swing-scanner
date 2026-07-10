"""
app.py — Swing Scanner Dashboard (Phase 1 — Polish)
"""

import io, logging, os
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Swing Scanner", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

from config import (
    MIN_PRICE, MIN_AVG_VOLUME_50D, MIN_MARKET_CAP,
    DEFAULT_RS_PERCENTILE, DEFAULT_TOP_N_SECTORS,
    RS_BENCHMARKS, DEFAULT_BENCHMARK,
    MACRO_ASSETS, VIX_GREEN, VIX_YELLOW, MAX_TABLE_ROWS,
    FINNHUB_API_KEY,
    EARNINGS_WARN_DAYS, EARNINGS_CAUTION_DAYS,
)
from scanner import run_scan
from data_fetcher import fetch_macro_data
from indicators import sma, ibd_rs_raw, pct_change_over, pct_change_ytd

st.markdown("""
<style>
  .stDataFrame{font-size:13px}
  [data-testid="stSidebar"]{min-width:285px;max-width:315px}
  .hdr{background:linear-gradient(135deg,#0f2027,#1a3a4a,#0d3b2e);
       padding:18px 24px;border-radius:10px;margin-bottom:16px}
  .hdr h1{color:#00e676;margin:0;font-size:1.6rem}
  .hdr p{color:#80cbc4;margin:4px 0 0 0;font-size:.85rem}
  [data-testid="stMetric"]{background:#1e1e2e;border-radius:8px;
       padding:12px 16px;border-left:3px solid #00e676}
</style>""", unsafe_allow_html=True)

for k,d in [("results",None),("sector_ranks",None),("filter_counts",None),
            ("last_run",None),("macro_df",None),("display_df",None)]:
    if k not in st.session_state: st.session_state[k]=d

st.markdown("""<div class="hdr">
  <h1>📈 Swing Scanner</h1>
  <p>IBD-Style RS · 90 HMA · 50/200 SMA · Weekly Trend · Dynamic MA Stack</p>
</div>""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Parameters")

    st.markdown("**Universe**")
    min_price  = st.number_input("Min Price ($)",      value=MIN_PRICE,
                                 step=1.0, format="%.2f")
    min_vol    = st.number_input("Min AvgVol (50d)",
                                 value=float(MIN_AVG_VOLUME_50D),
                                 step=50_000.0, format="%.0f")
    min_mcap_b = st.number_input("Min Mkt Cap ($B)",
                                 value=MIN_MARKET_CAP / 1e9,
                                 step=0.5, format="%.1f",
                                 help="$1B default. Lower to $0.5B adds ~1,000 more stocks; $0.2B adds ~3,000 more.")
    min_market_cap = min_mcap_b * 1e9

    st.markdown("---")
    st.markdown("**RS Benchmark**")
    bench_label = st.selectbox("Select benchmark", list(RS_BENCHMARKS.keys()))
    benchmark   = RS_BENCHMARKS[bench_label]
    st.caption("QQQ = best for momentum/growth stocks (beats the best).\n"
               "SPY = broader market comparison — more differentiation across sectors.")

    st.markdown("---")
    st.markdown("**Momentum / RS**")
    rs_min    = st.slider("Min RS Percentile", 50, 99, int(DEFAULT_RS_PERCENTILE))
    ema_align = st.checkbox("Require 3 EMA > 8 EMA (hard filter)", value=False)

    st.markdown("---")
    st.markdown("**MA Filters & Stack**")
    st.caption("Core always active: 8 EMA · 20 EMA · 50 SMA · 200 SMA")
    require_hma = st.checkbox("90 HMA — hard entry filter", value=True,
        help="Price must be above 90 HMA to enter. HMA90 always shown as (H90) in Stack Detail but never counted in stack score.")
    use_3ema    = st.checkbox("3 EMA — stack only (informational)", value=False,
        help="Adds 3 EMA to stack score/string. Does NOT block stocks from results.")
    if not require_hma:
        st.caption("⚠️ HMA90 filter OFF — use >HMA90 column for manual review")

    st.markdown("---")
    st.markdown("**Sectors**")
    top_sectors = st.slider("Top N Sectors", 1, 11, DEFAULT_TOP_N_SECTORS,
        help="Raise to 7-8 to capture emerging sectors while keeping RS bar high")

    st.markdown("---")
    st.markdown("**Earnings Data (Finnhub)**")
    _fh_default = FINNHUB_API_KEY
    if not _fh_default:
        try:
            _fh_default = st.secrets.get("FINNHUB_API_KEY", "")
        except Exception:
            _fh_default = ""
    fh_key = st.text_input("Finnhub API Key",
                           value=_fh_default,
                           type="password",
                           placeholder="Paste key from finnhub.io (free)",
                           help="Free key from finnhub.io — enables upcoming earnings column. Leave blank to skip.")
    if fh_key:
        st.caption("✅ Earnings calendar active")
    else:
        st.caption("ℹ️ No key — [get free key at finnhub.io](https://finnhub.io)")
    st.markdown("---")
    force_refresh = st.checkbox("Force re-download all data", value=False)
    st.markdown("---")
    run_btn = st.button("🚀 Run Scan", type="primary", use_container_width=True)
    if st.session_state.last_run:
        st.caption(f"Last run: {st.session_state.last_run}")

# ── Macro DF Builder ──────────────────────────────────────────────
def _build_macro_df(md: dict, benchmark: str) -> pd.DataFrame:
    if not md:
        logger.warning("Macro data dict is empty — check data fetch")
    qqq_df = md.get("QQQ"); spy_df = md.get("SPY")
    rows   = []
    for name, ticker in MACRO_ASSETS.items():
        df = md.get(ticker)
        row = {"Asset": name, "Ticker": ticker,
               "Price": np.nan, "1D %": np.nan, "1W %": np.nan, "1M %": np.nan,
               "YTD %": np.nan, "1Yr %": np.nan,
               "% > 10d SMA": np.nan, "RS vs QQQ %": np.nan, "RS vs SPY %": np.nan}
        if df is None or len(df) < 20:
            rows.append(row); continue

        close = df["Close"]
        row["Price"]      = round(float(close.iloc[-1]), 2)
        row["1D %"]       = round(float(pct_change_over(close, 1)),  2)
        row["1W %"]       = round(float(pct_change_over(close, 5)),  2)
        row["1M %"]       = round(float(pct_change_over(close, 21)), 2)
        row["YTD %"]      = round(float(pct_change_ytd(close)),      2)
        row["1Yr %"]      = round(float(pct_change_over(close, 252)),2)

        # % > 10d SMA: VIX-only metric (IBD-style breadth gauge)
        if ticker == "^VIX":
            s10 = float(sma(close, 10).iloc[-1]) if len(close) >= 10 else np.nan
            row["% > 10d SMA"] = round((row["Price"]/s10 - 1)*100, 2) \
                if not np.isnan(s10) else np.nan
        else:
            row["% > 10d SMA"] = np.nan

        if ticker != "^VIX" and len(df) >= 200:
            for col, bdf in [("RS vs QQQ %", qqq_df), ("RS vs SPY %", spy_df)]:
                if bdf is not None:
                    try:
                        raw = ibd_rs_raw(close, bdf["Close"])
                        row[col] = round(float(raw) * 100, 2) if not np.isnan(raw) else np.nan
                    except Exception:
                        row[col] = np.nan

        rows.append(row)
    return pd.DataFrame(rows)


# ── Run Scan ──────────────────────────────────────────────────────
if run_btn:
    s_ph  = st.empty(); p_bar = st.progress(0.0); l_ph = st.empty()
    msgs  = []
    def _cb(msg, pct):
        msgs.append(msg); s_ph.markdown(f"**{msg}**")
        p_bar.progress(min(pct,1.0))
        l_ph.code("\n".join(msgs[-8:]), language=None)
    try:
        # Fetch macro data FIRST — before stock downloads consume rate limit
        _cb("🌍 Pre-fetching macro & indices data…", 0.01)
        md = fetch_macro_data(force_refresh=force_refresh)
        st.session_state.macro_df = _build_macro_df(md, benchmark)

        r, sr, fc = run_scan(
            force_refresh=force_refresh, rs_min_pct=float(rs_min),
            top_n_sectors=top_sectors, require_hma90=require_hma,
            use_3ema_stack=use_3ema, require_ema_align=ema_align,
            benchmark=benchmark,
            min_price=float(min_price), min_vol=int(min_vol),
            min_market_cap=float(min_market_cap),
            finnhub_key=fh_key.strip(),
            status_cb=_cb,
        )
        st.session_state.results       = r
        st.session_state.sector_ranks  = sr
        st.session_state.filter_counts = fc
        st.session_state.last_run      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        st.error(f"Scan failed: {e}"); logger.exception("Scan error")
    s_ph.empty(); p_bar.empty(); l_ph.empty()
    st.rerun()


# ── Colour helpers ────────────────────────────────────────────────
def _c_earn(v):
    """Red = earnings very soon (risky), Yellow = approaching, blank = safe."""
    try:
        d = int(float(v))
        if d <= EARNINGS_WARN_DAYS:    return "color:#ef5350;font-weight:700"
        if d <= EARNINGS_CAUTION_DAYS: return "color:#ffd600;font-weight:700"
        return "color:#69f0ae"
    except: return ""

def _c_hma_dist(v):
    """Green = price above HMA90, Red = price below HMA90."""
    try:
        f = float(v)
        if f >= 0: return "color:#00e676;font-weight:700"   # above HMA
        return "color:#ef5350;font-weight:700"               # below HMA
    except: return ""

def _c_rs(v):
    try:
        f=float(v)
        if f>=90: return "color:#00e676;font-weight:700"
        if f>=80: return "color:#69f0ae"
        if f>=70: return "color:#ffd600"
        return ""
    except: return ""

def _c_pctb(v):
    try:
        f=float(v)
        if f>=1.0: return "color:#00e676;font-weight:700"
        if f>=0.5: return "color:#ffd600"
        return "color:#ef5350"
    except: return ""

def _c_stack(v):
    try:
        n,d_=str(v).split("/"); r=int(n)/int(d_)
        if r==1.0:  return "color:#00e676;font-weight:700"
        if r>=0.75: return "color:#ffd600"
        return "color:#ef5350"
    except: return ""

def _c_52wh(v):
    try:
        f=float(v)
        if f>=-3:  return "color:#00e676;font-weight:700"
        if f>=-25: return "color:#ffd600"
        return ""
    except: return ""

def _c_relvol(v):
    try:
        f=float(v)
        if f>=2.0: return "color:#00e676;font-weight:700"
        if f>=1.0: return "color:#69f0ae"
        return ""
    except: return ""

def _c_rank(v):
    try:
        n=int(float(v))
        if n<=3: return "color:#00e676;font-weight:700"
        if n<=6: return "color:#ffd600"
        return "color:#ef5350"
    except: return ""

def _c_chg(v):
    try:
        f=float(v)
        if f>2:  return "color:#00e676"
        if f<-2: return "color:#ef5350"
        return ""
    except: return ""

def _c_vix(v):
    try:
        f=float(v)
        if f<VIX_GREEN:  return "color:#00e676;font-weight:700"
        if f<VIX_YELLOW: return "color:#ffd600"
        return "color:#ef5350;font-weight:700"
    except: return ""


# ── Excel Export Builder ──────────────────────────────────────────
def _build_excel(stocks_df, sectors_df, macro_df) -> bytes:
    buf = io.BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            if stocks_df is not None and not stocks_df.empty:
                stocks_df.to_excel(writer, sheet_name="Stocks",  index=False)
            if sectors_df is not None and not sectors_df.empty:
                sectors_df.to_excel(writer, sheet_name="Sectors", index=False)
            if macro_df is not None and not macro_df.empty:
                macro_df.to_excel(writer,   sheet_name="Macro",   index=False)
        return buf.getvalue()
    except ImportError:
        return None


# ── Column config for stocks table ────────────────────────────────
def _stocks_col_config():
    CC = st.column_config
    return {
        # Ticker is the pinned index column — always visible when scrolling right
        "Ticker ▸":     CC.TextColumn("Ticker ▸",    width="small"),
        "W10SMA":       CC.NumberColumn("W10SMA",     format="%.2f", width="small"),
        "W40SMA":       CC.NumberColumn("W40SMA",     format="%.2f", width="small"),
        # Optional EMA/SMA price columns
        "EMA3":         CC.NumberColumn("EMA3",   format="%.2f", width="small"),
        "EMA8":         CC.NumberColumn("EMA8",   format="%.2f", width="small"),
        "EMA20":        CC.NumberColumn("EMA20",  format="%.2f", width="small"),
        "SMA50":        CC.NumberColumn("SMA50",  format="%.2f", width="small"),
        "HMA90":        CC.NumberColumn("HMA90",  format="%.2f", width="small"),
        "SMA200":       CC.NumberColumn("SMA200", format="%.2f", width="small"),
        "Industry":     CC.TextColumn("Industry"),
        "Name":         CC.TextColumn("Name"),                          # auto-width
        "Sector":       CC.TextColumn("Sector",       width="small"),   # compact
        "Price":        CC.NumberColumn("Price",       format="%.2f",  width="small"),
        "RS %ile ↓":    CC.NumberColumn("RS %ile ↓",   format="%.1f",  width="small"),
        "Sec Rank ↑":   CC.NumberColumn("Sec Rank ↑",  format="%.0f",  width="small"),
        "Sec RS":       CC.NumberColumn("Sec RS",      format="%.1f",  width="small"),
        "AvgVol(M)":    CC.NumberColumn("AvgVol(M)",   format="%.2f",  width="small"),
        "Rel Vol":      CC.NumberColumn("Rel Vol",     format="%.2f",  width="small"),
        "%B(50,1)":     CC.NumberColumn("%B(50,1)",    format="%.2f",  width="small"),
        "52wH%":        CC.NumberColumn("52wH%",       format="%.2f",  width="small"),
        "HMA90%":       CC.NumberColumn("HMA90%",      format="%.2f",  width="small"),
        "Stack":        CC.TextColumn("Stack",         width="small"),
        "Stack Detail": CC.TextColumn("Stack Detail"),                  # auto-width
        ">SMA50":       CC.TextColumn(">SMA50",        width="small"),
        ">SMA200":      CC.TextColumn(">SMA200",       width="small"),
        "Wkly✓":        CC.TextColumn("Wkly✓",        width="small"),
        "3>8":          CC.TextColumn("3>8",           width="small"),
        "Earn":         CC.NumberColumn("Earn",         format="%.0f", width="small"),
    }


# ── Main Results UI ───────────────────────────────────────────────
if st.session_state.results is not None:
    results     = st.session_state.results
    sr          = st.session_state.sector_ranks
    fc          = st.session_state.filter_counts or {}
    macro_df_ss = st.session_state.macro_df

    # Filter funnel
    if fc:
        with st.expander("🔬 Filter Funnel", expanded=True):
            cols = st.columns(6)
            for col,(lbl,key) in zip(cols,[
                ("Stocks","total_with_indicators"),
                (">SMA50","above_sma50"),(">SMA200","above_sma200"),
                (">HMA90","above_hma90"),("Weekly✓","weekly_trend"),
                ("MA Gate","passed_ma_filter"),
            ]): col.metric(lbl, fc.get(key,"—"))
            ra = fc.get("rs_available", True)
            st.caption(
                f"**MA Gate** = stocks passing SMA50 + SMA200 + HMA90 + Weekly (all together)  ·  "
                f"**Weekly** = Close > 10 SMA > 40 SMA (weekly bars)  ·  "
                f"RS≥{rs_min}: {fc.get('passed_ma_filter','?')} → {fc.get('passed_rs_filter','?')}"
                + ("" if ra else "  ⚠️ Benchmark unavailable")
                + f"  ·  Final watchlist: {fc.get('final_results','?')}"
            )

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("✅ Watchlist",  len(results))
    c2.metric("🏭 Sectors",
              results["sector"].nunique() if "sector" in results.columns else "—")
    if "rs_pct" in results.columns and not results["rs_pct"].isna().all():
        c3.metric("📊 Median RS", f"{results['rs_pct'].median():.0f}")
        c4.metric("🔝 Top RS",    f"{results['rs_pct'].max():.0f}")

    st.markdown("---")
    tab_stocks, tab_sectors, tab_macro, tab_export = st.tabs([
        "📋 Stocks", "🏭 Sectors", "🌍 Macro & Indices", "📤 Export"
    ])

    # ── STOCKS TAB ────────────────────────────────────────────────
    with tab_stocks:
        if results.empty:
            st.warning("No stocks passed all filters.\n\n"
                       "Try: turn OFF '90 HMA hard filter', lower RS %, "
                       "or increase Top N Sectors.")
        else:
            unmapped = int(results["sector_rank"].isna().sum()) if "sector_rank" in results.columns else 0
            st.caption(
                f"{len(results)} stocks · RS≥{rs_min} · "
                f">SMA50 >SMA200 {'> HMA90 ' if require_hma else '(HMA flag) '}"
                f"· Weekly Close>10SMA>40SMA · Benchmark: {benchmark}  ·  "
                f"**Sort: Sec Rank ↑ → RS %ile ↓**"
                + (f"  ·  {unmapped} stocks have unmapped sectors (e.g. Miscellaneous) — no sector rank available" if unmapped else "")
            )

            with st.expander("🔧 Column Options", expanded=False):
                c1,c2,c3 = st.columns(3)
                show_emas   = c1.checkbox("EMA/SMA prices",  value=False,
                    key="show_emas",
                    help="Adds EMA3, EMA8, EMA20, SMA50, HMA90, SMA200 price columns")
                show_weekly = c2.checkbox("Weekly MA values", value=False,
                    key="show_weekly",
                    help="Adds W10SMA and W40SMA price columns")
                show_ind    = c3.checkbox("Industry column",  value=False,
                    key="show_ind",
                    help="Adds the Industry sub-sector column")
                if show_emas or show_weekly or show_ind:
                    st.caption("✅ Extra columns added — scroll the table right →")

            d = results.head(MAX_TABLE_ROWS).copy()

            # ── Round ALL numeric columns to 2dp ─────────────────
            num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
            d[num_cols] = d[num_cols].round(2)

            # Avg vol in millions
            if "avg_vol_50" in d.columns:
                d["avg_vol_50"] = (d["avg_vol_50"] / 1e6).round(2)

            # Bool → emoji
            for col in ["above_sma50","above_sma200","above_hma90",
                        "ema3_gt_ema8","weekly_trend_ok"]:
                if col in d.columns:
                    d[col] = d[col].map({True:"✅", False:"❌"})

            # ── Priority column order ─────────────────────────────
            cols_map = [
                ("ticker","Ticker"),("name","Name"),("sector","Sector"),
                ("price","Price"),("rs_pct","RS %ile ↓"),
                ("sector_rank","Sec Rank ↑"),("sector_rs_pct","Sec RS"),
                ("avg_vol_50","AvgVol(M)"),("rel_vol","Rel Vol"),
                ("pct_b","%B(50,1)"),("pct_from_52wh","52wH%"),
                ("stack_score","Stack"),("stack_str","Stack Detail"),
                ("hma_dist_pct","HMA90%"),
                ("above_sma50",">SMA50"),("above_sma200",">SMA200"),
                ("ema3_gt_ema8","3>8"),
                ("earn_days","Earn"),
            ]
            # Weekly MAs immediately followed by Wkly flag
            if show_weekly:
                cols_map += [("w_sma_10","W10SMA"),("w_sma_40","W40SMA")]
            cols_map += [("weekly_trend_ok","Wkly✓")]
            if show_emas:
                cols_map += [("ema_3","EMA3"),("ema_8","EMA8"),
                             ("ema_20","EMA20"),("sma_50","SMA50"),
                             ("hma_90","HMA90"),("sma_200","SMA200")]
            if show_ind:
                cols_map += [("industry","Industry")]
            keep = [(c,n) for c,n in cols_map if c in d.columns]
            d    = d[[c for c,_ in keep]].rename(columns=dict(keep))
            # Pin Ticker as index so it stays visible when scrolling right
            if "Ticker" in d.columns:
                d = d.set_index("Ticker")
                d.index.name = "Ticker ▸"  # subtle arrow hints to scroll right

            # ── Apply colour styling ──────────────────────────────
            style = d.style
            for col, fn in [("RS %ile ↓",_c_rs),("%B(50,1)",_c_pctb),
                            ("Stack",_c_stack),("52wH%",_c_52wh),
                            ("Rel Vol",_c_relvol),("Sec Rank ↑",_c_rank),
                            ("HMA90%",_c_hma_dist),
                            ("Earn",_c_earn)]:
                if col in d.columns:
                    style = style.map(fn, subset=[col])

            n_rows    = min(len(d), MAX_TABLE_ROWS)
            tbl_height = min(max(n_rows * 36 + 60, 400), 900)
            st.caption(
                f"💡 Scroll **within the table** to keep headers visible. "
                f"({n_rows} rows)"
            )
            # Save display-ready table for export (matches screen exactly)
            st.session_state.display_df = d.reset_index()  # Ticker back as column

            tbl_event = st.dataframe(style,
                         column_config=_stocks_col_config(),
                         width="stretch",
                         hide_index=False,   # Ticker index always visible on left
                         height=tbl_height,
                         on_select="rerun",
                         selection_mode="multi-row",
                         key="stocks_tbl")

            # ── Phase 2.5: scan → plan handoff ────────────────────
            _sel = []
            try:
                _sel = list(tbl_event.selection.rows)
            except Exception:
                _sel = []
            if _sel:
                def _g(row, col):
                    try:
                        v = float(row[col])
                        return v if np.isfinite(v) else None
                    except Exception:
                        return None

                def _handoff_for(tkr):
                    _raw = results[results["ticker"] == tkr]
                    _raw = _raw.iloc[0] if not _raw.empty else None
                    return {
                        "symbol":    tkr,
                        "price":     _g(_raw, "price")     if _raw is not None else None,
                        "sma50":     _g(_raw, "sma_50")    if _raw is not None else None,
                        "hma90":     _g(_raw, "hma_90")    if _raw is not None else None,
                        "sma200":    _g(_raw, "sma_200")   if _raw is not None else None,
                        "ema8":      _g(_raw, "ema_8")     if _raw is not None else None,
                        "ema20":     _g(_raw, "ema_20")    if _raw is not None else None,
                        "rs_pct":    _g(_raw, "rs_pct")    if _raw is not None else None,
                        "earn_days": _g(_raw, "earn_days") if _raw is not None else None,
                        "sector":    (str(_raw["sector"]) if _raw is not None
                                      and "sector" in _raw.index else ""),
                        "benchmark": benchmark,
                    }

                _tickers = [str(d.index[i]) for i in _sel][:6]
                st.markdown("**Selected for planning** — click to open in "
                            "Trade Plan (pre-filled):")
                _bcols = st.columns(max(len(_tickers), 1))
                for _i, _tkr in enumerate(_tickers):
                    if _bcols[_i].button(f"🎯 {_tkr}", type="primary",
                                         key=f"planbtn_{_tkr}"):
                        st.session_state["plan_handoff"] = _handoff_for(_tkr)
                        st.switch_page("pages/2_Trade_Plan.py")
                if len(_sel) > 6:
                    st.caption(f"{len(_sel)} rows selected — showing first 6. "
                               "Plan these, then select the next batch.")

    # ── SECTORS TAB ───────────────────────────────────────────────
    with tab_sectors:
        st.markdown(f"### Sector RS Rankings vs {benchmark}")
        if sr is not None and not sr.empty:
            d = sr.copy()
            # Convert RS raw score to % (multiply by 100) for readability
            if "rs_raw" in d.columns:
                d["rs_raw"] = (d["rs_raw"] * 100).round(2)
            if "rs_pct" in d.columns:
                d["rs_pct"] = d["rs_pct"].round(0).astype("Int64", errors="ignore")
            if "sector_rank" in d.columns:
                d["sector_rank"] = d["sector_rank"].round(0)
            d = d.rename(columns={"sector":"Sector","etf":"ETF",
                                   "rs_raw":"RS %","rs_pct":"RS %ile",
                                   "sector_rank":"Rank"})
            # Column order: Sector - ETF - Rank - RS %ile - RS %
            col_order = [c for c in ["Sector","ETF","Rank","RS %ile","RS %"] if c in d.columns]
            d = d[col_order]
            # Auto-height to show all 11 rows
            sec_height = len(d) * 36 + 58
            st.caption(f"Showing {len(d)} sectors  ·  **Sort: Rank ↑**  ·  "
                       f"RS %ile = 1–99 percentile vs {benchmark}  ·  "
                       f"RS % = raw outperformance × 100")
            st.dataframe(
                d.style.map(_c_rank, subset=["Rank"]),
                column_config={
                    "Sector":  st.column_config.TextColumn("Sector",  width="large"),
                    "ETF":     st.column_config.TextColumn("ETF",     width="small"),
                    "Rank":    st.column_config.NumberColumn("Rank",  format="%.0f", width="small"),
                    "RS %ile": st.column_config.NumberColumn("RS %ile",format="%.0f",width="small"),
                    "RS %":    st.column_config.NumberColumn("RS %",  format="%.2f", width="small"),
                },
                use_container_width=True, hide_index=True, height=sec_height,
            )
        else:
            st.info("No sector data available.")

    # ── MACRO TAB ─────────────────────────────────────────────────
    with tab_macro:
        st.markdown("### 🌍 Macro & Indices")
        if macro_df_ss is None:
            st.info("Run a scan first — macro data loads automatically.")
        else:
            mdf = macro_df_ss.copy()
            # Ensure all numeric columns are clean floats
            num_cols = mdf.select_dtypes(include=[np.number]).columns
            mdf[num_cols] = mdf[num_cols].round(2)
            # Replace any None with NaN for clean display
            mdf = mdf.where(mdf.notna(), other=np.nan)

            style = mdf.style
            for col in ["1D %","1W %","1M %","YTD %","1Yr %","% > 10d SMA"]:
                if col in mdf.columns:
                    style = style.map(_c_chg, subset=[col])

            # VIX price colour
            if "Price" in mdf.columns and "Ticker" in mdf.columns:
                vix_idx = mdf[mdf["Ticker"]=="^VIX"].index
                if len(vix_idx):
                    style = style.map(_c_vix,
                        subset=pd.IndexSlice[vix_idx, ["Price"]])

            macro_height = len(mdf) * 36 + 58
            st.caption(
                f"Showing {len(mdf)} assets  ·  "
                "**Colours:** 🟢 >+2% gain  ·  🔴 >2% loss  ·  no colour = within ±2%  ·  "
                f"VIX: 🟢 <{VIX_GREEN} calm  ·  🟡 {VIX_GREEN}–{VIX_YELLOW} caution  ·  "
                f"🔴 >{VIX_YELLOW} fear  ·  "
                "RS % = IBD-style outperformance vs benchmark × 100 (positive = beating benchmark)  ·  "
                "% > 10d SMA shown for VIX only (IBD-style VIX breadth gauge)"
            )
            col_cfg_macro = {
                "Asset":       st.column_config.TextColumn("Asset",        width="medium"),
                "Ticker":      st.column_config.TextColumn("Ticker",       width="small"),
                "Price":       st.column_config.NumberColumn("Price",       format="%.2f", width="small"),
                "1D %":        st.column_config.NumberColumn("1D %",        format="%.2f", width="small"),
                "1W %":        st.column_config.NumberColumn("1W %",        format="%.2f", width="small"),
                "1M %":        st.column_config.NumberColumn("1M %",        format="%.2f", width="small"),
                "YTD %":       st.column_config.NumberColumn("YTD %",       format="%.2f", width="small"),
                "1Yr %":       st.column_config.NumberColumn("1Yr %",       format="%.2f", width="small"),
                "% > 10d SMA": st.column_config.NumberColumn("% > 10d SMA", format="%.2f", width="small"),
                "RS vs QQQ %": st.column_config.NumberColumn("RS vs QQQ %", format="%.2f", width="small"),
                "RS vs SPY %": st.column_config.NumberColumn("RS vs SPY %", format="%.2f", width="small"),
            }
            st.dataframe(style, column_config=col_cfg_macro,
                         use_container_width=True, hide_index=True,
                         height=macro_height)

    # ── EXPORT TAB ────────────────────────────────────────────────
    with tab_export:
        st.markdown("### 📤 Export")


        # ── Export All (Excel, 3 sheets) ──────────────────────────
        st.markdown("#### 📊 Export All — Single Excel File (3 sheets)")
        # Use display_df — matches screen exactly incl. Column Options
        stocks_export = st.session_state.get("display_df", pd.DataFrame())
        if stocks_export.empty:
            st.info("💡 View the **Stock Results** tab first, then come back here to export.")

        excel_bytes = _build_excel(stocks_export, sr, macro_df_ss)
        if excel_bytes:
            st.download_button(
                "⬇️ Export All (Excel — Stocks + Sectors + Macro)",
                excel_bytes,
                f"SwingScan_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.warning("Excel export requires openpyxl. Run: `pip install openpyxl` "
                       "in your venv, then restart.")

        st.markdown("---")
        st.markdown("#### Individual CSV Downloads")
        ca, cb, cc = st.columns(3)

        with ca:
            if not stocks_export.empty:
                st.download_button("⬇️ Stocks CSV", stocks_export.to_csv(index=False).encode(),
                    f"watchlist_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    "text/csv", use_container_width=True)

        with cb:
            if sr is not None and not sr.empty:
                st.download_button("⬇️ Sectors CSV", sr.to_csv(index=False).encode(),
                    f"sectors_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    "text/csv", use_container_width=True)

        with cc:
            if macro_df_ss is not None and not macro_df_ss.empty:
                st.download_button("⬇️ Macro CSV", macro_df_ss.to_csv(index=False).encode(),
                    f"macro_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    "text/csv", use_container_width=True)

        st.markdown("---")
        st.markdown("---")
        st.markdown("#### TradingView Watchlist Import")
        if not results.empty:
            tv_col1, tv_col2 = st.columns(2)
            with tv_col1:
                tv_lines = "\n".join(
                    results["ticker"].head(MAX_TABLE_ROWS).tolist())
                st.download_button(
                    "⬇️ Download TradingView Watchlist (.txt)",
                    tv_lines.encode(),
                    f"TV_SwingScanner_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    "text/plain",
                    use_container_width=True,
                    help="One ticker per line — upload via TV Watchlist dropdown → Upload List"
                )
            with tv_col2:
                st.caption(
                    "**To import:** In TradingView, open your Swing Scanner watchlist "
                    "→ click the watchlist name dropdown → **Upload List** → select this file."
                )
            tl = ",".join(results["ticker"].head(MAX_TABLE_ROWS).tolist())
            st.text_area("Comma-separated (for manual use)",
                         value=tl, height=80, label_visibility="visible")


else:
    # Welcome
    st.info("Configure filters in the sidebar → **🚀 Run Scan**")
    with st.expander("📖 Column Guide", expanded=True):
        st.markdown("""
| Column | What to look for |
|--------|-----------------|
| **%B(50,1)** | 🟢 ≥1.0 = above upper BB (your Buy line) · 🟡 0.5–1.0 · 🔴 <0.5 |
| **52wH%** | % below 52-week high. 🟢 within 10% (near new high) · 🟡 within 25% |
| **Rel Vol** | Today's vol ÷ 50-day avg. 🟢 ≥2x surging · 🟩 ≥1x above avg |
| **Stack** | How many consecutive pairs are in bullish order **starting from Price**. Score includes Price vs each MA. 4/4 = Price above all 4 core MAs AND all MAs in descending order. **3/4 with MAs perfectly ordered = Price is below the fastest active MA (a pullback).** 🟢 = fully stacked · 🟡 ≥75% · 🔴 <75% |
| **Stack Detail** | Dynamic string ordered by actual current value (high → low). **【$】= your price position**. () = calculated but not counted in score (always 3E and H90). Example: `8E-【$】-20E-50S-(H90)-200S` means price pulled back below 8 EMA but above 20 EMA — all MAs still properly stacked below. |

**New exports:** Single Excel file with Stocks + Sectors + Macro all in separate sheets.
        """)
    with st.expander("📐 Exit Signal Reference"):
        st.markdown("""
| Signal | Action |
|--------|--------|
| 3 EMA × below 8 EMA | Sell ⅓ (early momentum exit) |
| Price touches 50 SMA | Sell ⅓ |
| Price closes below 90 HMA | Sell ⅓ |
| Price closes below 200 SMA | Exit all |
        """)

st.markdown("---")
st.caption(f"yfinance ~15-min delayed · IBD-Style RS · BB(50,1) · "
           f"Cache: {os.path.abspath('cache')}")
