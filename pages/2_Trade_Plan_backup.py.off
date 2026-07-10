"""
pages/2_Trade_Plan.py  —  v2 (Phase 2.5 seam stitch)
====================================================
Changes from v1:
  - Accepts scan → plan handoff from app.py (symbol, price, benchmark,
    scanner MA levels, RS %ile, sector, earnings days) via
    st.session_state["plan_handoff"]; lands pre-filled with zero retyping.
  - Scanner MA levels (SMA50/HMA90/SMA200/EMA8/EMA20) become instant stop
    bases even before bars are fetched; bar-computed suggestions
    (swing low, ATR) merge in on top.
  - Earnings-proximity warning surfaces on the plan when earn_days is known.
  - use_container_width deprecation cleaned up (width="stretch").
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from swing_risk import (
    SIZING_CONFIGS, EXIT_CONFIGS, DEFAULT_SIZING, DEFAULT_EXIT,
    RegimeSnapshot, RegimeMode, StopSuggestion, suggest_stops,
    build_trade_plan, portfolio_current_heat_pct, store,
)

st.set_page_config(page_title="Trade Plan", page_icon="🎯", layout="wide")
st.title("🎯 Trade Plan Generator")
st.caption("Phase 2 — Risk Management · built against Data Architecture v1.4")

USER_ID = "ev"
ACCOUNT_ID = "default"
BENCHMARKS = ["QQQ", "SPY", "IWM", "DIA", "BTC"]

# ----------------------------------------------------------------------------
# Scan → Plan handoff (Phase 2.5)
# ----------------------------------------------------------------------------
_handoff = st.session_state.pop("plan_handoff", None)
if _handoff:
    st.session_state["tp_symbol"] = _handoff.get("symbol", "")
    if _handoff.get("price"):
        st.session_state["tp_entry"] = round(float(_handoff["price"]), 2)
    if _handoff.get("benchmark") in BENCHMARKS:
        st.session_state["tp_benchmark"] = _handoff["benchmark"]
    st.session_state["tp_levels"] = _handoff          # keep for stop bases
if "tp_levels" not in st.session_state:
    st.session_state["tp_levels"] = {}


# ----------------------------------------------------------------------------
# TODO(EV): point this at the scanner's data pipeline / cache when convenient.
# Used only for swing-low + ATR stop bases; scanner handoff supplies the MAs.
# ----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_price_data(symbol: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        df = yf.download(symbol, period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        df.columns = [str(c[0]).lower() if isinstance(c, tuple) else str(c).lower()
                      for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        return None


def get_regime(benchmark: str) -> RegimeSnapshot:
    with st.sidebar:
        st.subheader("Market Regime (manual until automated)")
        mode = st.selectbox(f"{benchmark} regime", ["GREEN", "YELLOW", "RED"],
                            index=0, key="tp_regime_mode")
        composite = st.selectbox("Composite RYG verdict",
                                 ["GREEN", "YELLOW", "RED"], index=0,
                                 key="tp_regime_comp")
    return RegimeSnapshot(
        as_of=date.today(), benchmark_id=benchmark,
        mode=RegimeMode(mode), composite_mode=RegimeMode(composite),
        detail="manually set (RegimeState engine will compute this)",
    )


# ----------------------------------------------------------------------------
# Sidebar: account & configs
# ----------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Account")
    equity = st.number_input("Account equity ($)", min_value=1000.0,
                             value=100_000.0, step=1000.0, key="tp_equity")
    st.subheader("Rulesets (P2: rules are config)")
    sizing_id = st.selectbox("Sizing config", list(SIZING_CONFIGS),
                             index=list(SIZING_CONFIGS).index(DEFAULT_SIZING),
                             key="tp_sizing")
    exit_id = st.selectbox("Exit config", list(EXIT_CONFIGS),
                           index=list(EXIT_CONFIGS).index(DEFAULT_EXIT),
                           key="tp_exit")
    sizing_cfg = SIZING_CONFIGS[sizing_id]
    exit_cfg = EXIT_CONFIGS[exit_id]
    with st.expander("Config details"):
        st.write(f"**{sizing_cfg.config_id}** — {sizing_cfg.notes}")
        st.json(sizing_cfg.risk_pct_by_mode)
        st.write(f"**{exit_cfg.config_id}** — {exit_cfg.notes}")
        for r in exit_cfg.rungs:
            st.write(f"• {r.label}")

# ----------------------------------------------------------------------------
# Open positions (feeds current heat)
# ----------------------------------------------------------------------------
st.subheader("Open Positions (current heat)")
open_pos = store.get_open_positions(USER_ID, ACCOUNT_ID)
c1, c2 = st.columns([3, 2])
with c1:
    if open_pos:
        pdf = pd.DataFrame(open_pos)
        if "initial_risk_ps" in pdf.columns:
            _r = pd.to_numeric(pdf["initial_risk_ps"], errors="coerce").fillna(0.0)
            _e = pd.to_numeric(pdf["avg_entry"], errors="coerce")
            _m = _r > 0
            for _n in (1, 2, 3):
                pdf.loc[_m, f"{_n}R"] = (_e + _n * _r)[_m].round(2)
        pdf = pdf.drop(columns=[c for c in ("plan_id",) if c in pdf.columns])
        st.dataframe(pdf, width="stretch", hide_index=True)
        st.caption("1R/2R/3R price levels appear for positions recorded via "
                   "**Mark FILLED** (initial risk captured at fill).")
    else:
        st.info("No open positions on record. Add them below so heat is accurate.")
with c2:
    with st.form("add_pos", clear_on_submit=True):
        st.write("**Add / update position**")
        p_sym = st.text_input("Symbol").upper()
        p_shares = st.number_input("Shares", min_value=0.0, step=1.0)
        p_entry = st.number_input("Avg entry", min_value=0.0, step=0.01)
        p_stop = st.number_input("Current stop", min_value=0.0, step=0.01)
        cA, cB = st.columns(2)
        if cA.form_submit_button("Save") and p_sym and p_shares > 0:
            store.upsert_position(USER_ID, ACCOUNT_ID, p_sym, p_shares, p_entry, p_stop)
            st.rerun()
        if cB.form_submit_button("Remove") and p_sym:
            store.delete_position(USER_ID, ACCOUNT_ID, p_sym)
            st.rerun()

heat_now = portfolio_current_heat_pct(open_pos, equity)
free_trades = sum(1 for p in open_pos
                  if p["current_stop"] >= p["avg_entry"] and p["direction"] == "LONG")
m1, m2, m3 = st.columns(3)
m1.metric("Current portfolio heat", f"{heat_now:.2f}%",
          help="Sum of current risk (entry vs current stop) across open positions ÷ equity. v1.4: breakeven stops contribute zero.")
m2.metric("Heat ceiling", f"{sizing_cfg.max_portfolio_heat_pct:.1f}%")
m3.metric("Free trades (stop ≥ BE)", free_trades)

st.divider()

# ----------------------------------------------------------------------------
# Plan a trade
# ----------------------------------------------------------------------------
st.subheader("Plan a Trade")

lv = st.session_state.get("tp_levels", {}) or {}
if lv.get("symbol"):
    bits = [f"**{lv['symbol']}** pre-filled from scan"]
    if lv.get("rs_pct") is not None:
        bits.append(f"RS %ile **{lv['rs_pct']:.1f}**")
    if lv.get("sector"):
        bits.append(lv["sector"])
    if lv.get("earn_days") is not None:
        bits.append(f"earnings in **{int(lv['earn_days'])}** days")
    st.info(" · ".join(bits))

col1, col2, col3, col4 = st.columns(4)
symbol = col1.text_input("Symbol", key="tp_symbol").upper()
setup_type = col2.selectbox("Setup", ["Pullback", "Breakout", "Bull Flag", "Base",
                                      "Shakeout", "Gap", "ORB", "Cup & Handle"],
                            key="tp_setup")
grade = col3.selectbox("Setup grade", ["A", "B", "C"], index=1, key="tp_grade")
if "tp_benchmark" not in st.session_state:
    st.session_state["tp_benchmark"] = "QQQ"
benchmark = col4.selectbox("Benchmark", BENCHMARKS, key="tp_benchmark")

regime = get_regime(benchmark)
tier = sizing_cfg.risk_pct_by_mode.get(regime.mode.value, 0.0)
st.caption(f"Regime: **{regime.mode.value}** on {benchmark} → risk tier "
           f"**{tier}%** of equity = **${equity * tier / 100:,.0f}** risk budget "
           f"({sizing_cfg.config_id})")

# bars: used for swing-low & ATR; the scanner handoff already covers the MAs
df = get_price_data(symbol) if symbol else None
last_close = float(df["close"].iloc[-1]) if df is not None and len(df) else 0.0

col5, col6, col7 = st.columns(3)
if "tp_entry" not in st.session_state:
    st.session_state["tp_entry"] = round(last_close, 2) if last_close else 0.0
entry = col5.number_input("Entry price", min_value=0.0, step=0.01, key="tp_entry")
if last_close and abs(entry - last_close) > 0.005:
    if col5.button(f"↩ use last close {last_close:,.2f}"):
        st.session_state["tp_entry"] = round(last_close, 2)
        st.rerun()

# ---- stop suggestions: bars-computed + scanner-handoff levels merged --------
sugg: list[StopSuggestion] = []
if df is not None and entry > 0:
    sugg = suggest_stops(df, entry)

if entry > 0 and lv.get("symbol") == symbol:
    have = {s.basis for s in sugg}
    _scan_levels = [
        ("EMA8",   lv.get("ema8"),   "8 EMA (scanner)",   False),
        ("EMA20",  lv.get("ema20"),  "20 EMA (scanner)",  False),
        ("SMA50",  lv.get("sma50"),  "50 SMA (scanner)",  False),
        ("HMA90",  lv.get("hma90"),  "90 HMA (scanner) [overlay: Ev-Exp]", True),
        ("SMA200", lv.get("sma200"), "200 SMA (scanner)", False),
    ]
    for basis, level, note, overlay in _scan_levels:
        if basis in have or level is None:
            continue
        if level < entry:  # protective side only (long)
            sugg.append(StopSuggestion(
                basis=basis, level=round(float(level), 2),
                distance_pct=round((entry - level) / entry * 100, 2),
                note=note, is_overlay=overlay))
    sugg.sort(key=lambda s: s.distance_pct)

if sugg:
    st.write("**Auto-suggested stops** (nearest first — 5-step framework):")
    srows = [{"Basis": s.basis + (" ⚗️" if s.is_overlay else ""),
              "Level": f"${s.level:,.2f}", "Distance": f"{s.distance_pct:.2f}%",
              "Note": s.note} for s in sugg]
    st.dataframe(pd.DataFrame(srows), width="stretch", hide_index=True)
    default_stop = _lm0.get("EMA20", sugg[0].level) if (_lm0 := {s.basis: s.level for s in sugg}) else sugg[0].level
else:
    default_stop = 0.0
    if symbol and df is None and not lv.get("symbol"):
        st.warning("No price data — enter the stop manually (suggestions unavailable).")

# ---- stop basis drives the stop price; MANUAL frees it ----------------------
_level_map = {s.basis: s.level for s in sugg}
_basis_options = list(_level_map) + ["MANUAL"]
_pref_basis = "EMA20" if "EMA20" in _level_map else _basis_options[0]
if st.session_state.get("tp_stop_basis") not in _basis_options:
    st.session_state["tp_stop_basis"] = _pref_basis
with col6:
    basis = st.selectbox("Stop basis", _basis_options,
                         key="tp_stop_basis",
                         help="Pick a technical level to snap the stop to it. "
                              "Pick MANUAL to type any stop.")
    if "tp_stop" not in st.session_state:
        st.session_state["tp_stop"] = float(default_stop)
    if basis != "MANUAL" and basis in _level_map:
        if st.session_state.get("_tp_last_basis") != basis:
            st.session_state["tp_stop"] = float(_level_map[basis])
    st.session_state["_tp_last_basis"] = basis
    stop = st.number_input("Stop price", min_value=0.0, step=0.01, key="tp_stop")

# record honestly if the number was hand-adjusted away from the named basis
basis_recorded = basis
if basis != "MANUAL" and basis in _level_map         and abs(stop - _level_map[basis]) > 0.005:
    basis_recorded = f"MANUAL (adj from {basis})"
    st.caption(f"✏️ Stop hand-adjusted away from {basis} "
               f"({_level_map[basis]:,.2f}) — will be recorded as {basis_recorded}.")

st.session_state.setdefault("tp_target", 0.0)
target = col7.number_input("Target (0 = trail-only)", min_value=0.0,
                           step=0.01, key="tp_target",
                           help="0 = trail-based plan (R/R shows 'trail'; the exit "
                                "config manages the reward side). Enter a price to "
                                "get a fixed R/R validated against the config minimum.")

thesis = st.text_input("Thesis (why this trade)", key="tp_thesis")

if st.button("Build Trade Plan", type="primary",
             disabled=not (symbol and entry > 0 and stop > 0)):
    plan = build_trade_plan(
        symbol=symbol, entry_price=entry, stop_price=stop, stop_basis=basis_recorded,
        equity=equity, regime=regime, sizing=sizing_cfg, exit_cfg=exit_cfg,
        open_positions=open_pos, setup_type=setup_type, setup_grade=grade,
        target_price=target or None, stop_suggestions=sugg,
        benchmark_id=benchmark, thesis=thesis, user_id=USER_ID,
        account_id=ACCOUNT_ID,
    )
    # earnings-proximity warning from scanner handoff
    if lv.get("symbol") == symbol and lv.get("earn_days") is not None:
        ed = int(lv["earn_days"])
        if ed <= 10:
            plan.warnings.append(
                f"Earnings in {ed} days — MTG guidance: avoid holding new swing "
                f"entries into earnings; plan the exit or pass.")
    st.session_state["last_plan"] = plan

# ----------------------------------------------------------------------------
# Plan result
# ----------------------------------------------------------------------------
plan = st.session_state.get("last_plan")
if plan and plan.symbol == symbol:
    st.divider()
    if (abs(plan.entry_price - entry) > 0.005 or abs(plan.stop_price - stop) > 0.005
            or plan.setup_grade != grade
            or abs((plan.target_price or 0.0) - (target or 0.0)) > 0.005):
        st.warning("⚠️ Inputs have changed since this plan was built — the numbers "
                   "below are a snapshot. Click **Build Trade Plan** to refresh "
                   "before saving.")
    if plan.is_valid:
        st.success(f"✅ VALID PLAN — {plan.symbol}")
    else:
        st.error(f"⛔ PLAN BLOCKED — {plan.symbol}")
        for b in plan.blockers:
            st.error(b)
    for w in plan.warnings:
        st.warning(w)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Shares", f"{plan.shares_planned:,}")
    k2.metric("Risk $", f"${plan.risk_dollars:,.0f}", f"{plan.risk_pct}% tier")
    k3.metric("Position $", f"${plan.position_dollars:,.0f}")
    k4.metric("R/R", f"{plan.rr_ratio}:1" if plan.rr_ratio else "trail")
    k5.metric("Heat after", f"{plan.heat_after_pct:.2f}%",
              f"{plan.heat_after_pct - plan.heat_before_pct:+.2f}%")

    _rps = abs(plan.entry_price - plan.stop_price)
    if _rps > 0:
        _sgn = 1 if plan.direction == "LONG" else -1
        st.caption(
            f"**R ladder** (per-share risk ${_rps:,.2f}) — "
            f"1R **${plan.entry_price + _sgn*_rps:,.2f}** · "
            f"2R **${plan.entry_price + _sgn*2*_rps:,.2f}** · "
            f"3R **${plan.entry_price + _sgn*3*_rps:,.2f}** — "
            f"exit config takes over from these milestones.")

    with st.expander("Pre-trade verification checklist", expanded=not plan.is_valid):
        for name, item in plan.checklist.items():
            icon = "✅" if item["ok"] else "❌"
            st.write(f"{icon} **{name.replace('_', ' ').title()}** — {item['msg']}")

    with st.expander(f"Exit script — {plan.exit_config_id}"):
        for r in EXIT_CONFIGS[plan.exit_config_id].rungs:
            st.write(f"• {r.label}")

    cS, cA = st.columns(2)
    if cS.button("💾 Save as DRAFT"):
        store.save_plan(plan)
        st.toast(f"Plan {plan.plan_id} saved.")
    if cA.button("🎯 Save & ARM", disabled=not plan.is_valid):
        plan.status = "ARMED"
        store.save_plan(plan)
        st.toast(f"Plan {plan.plan_id} ARMED.")

# ----------------------------------------------------------------------------
# Saved plans
# ----------------------------------------------------------------------------
st.divider()
st.subheader("Saved Plans")
plans = store.load_plans(USER_ID)
if plans:
    rows = [{"Created": p.created, "Symbol": p.symbol, "Setup": p.setup_type,
             "Grade": p.setup_grade, "Shares": p.shares_planned,
             "Risk $": p.risk_dollars, "R/R": p.rr_ratio, "Status": p.status,
             "Valid": "✅" if p.is_valid else "⛔", "ID": p.plan_id}
            for p in plans]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    _labels = {f"{p.symbol} · {p.status} · {p.created} · {p.plan_id[:6]}": p
               for p in plans}
    _sel = st.selectbox("Manage a plan", ["—"] + list(_labels),
                        key="tp_manage_sel")
    if _sel != "—":
        p = _labels[_sel]
        a1, a2, a3 = st.columns(3)

        if a1.button("📥 Load into form", help="Pull this plan back into the "
                     "inputs above to adjust → Build → Save (creates a new "
                     "version; delete the old one if superseded)."):
            st.session_state["tp_symbol"] = p.symbol
            st.session_state["tp_entry"] = float(p.entry_price)
            st.session_state["tp_stop_basis"] = "MANUAL"
            st.session_state["tp_stop"] = float(p.stop_price)
            st.session_state["tp_target"] = float(p.target_price or 0.0)
            st.session_state["tp_grade"] = p.setup_grade
            _setups = ["Pullback", "Breakout", "Bull Flag", "Base",
                       "Shakeout", "Gap", "ORB", "Cup & Handle"]
            if p.setup_type in _setups:
                st.session_state["tp_setup"] = p.setup_type
            if p.benchmark_id in BENCHMARKS:
                st.session_state["tp_benchmark"] = p.benchmark_id
            st.session_state["tp_thesis"] = p.thesis or ""
            st.session_state["tp_levels"] = {}
            st.session_state.pop("last_plan", None)
            st.rerun()

        if p.status == "DRAFT" and a2.button("🎯 ARM this plan"):
            store.update_plan_status(p.plan_id, "ARMED")
            st.rerun()

        if a3.button("🗑 Delete plan"):
            store.delete_plan(p.plan_id)
            st.rerun()

        if p.status in ("DRAFT", "ARMED"):
            with st.expander(f"✅ Mark {p.symbol} FILLED — record actual execution",
                             expanded=False):
                f1, f2, f3 = st.columns(3)
                fill_price = f1.number_input("Actual fill price",
                    value=float(p.entry_price), step=0.01,
                    key=f"fp_{p.plan_id}")
                fill_shares = f2.number_input("Filled shares",
                    value=float(p.shares_planned), step=1.0,
                    key=f"fs_{p.plan_id}")
                fill_stop = f3.number_input("Working stop",
                    value=float(p.stop_price), step=0.01,
                    key=f"fstop_{p.plan_id}")
                if st.button("Record fill → creates/updates open position",
                             type="primary", key=f"fbtn_{p.plan_id}"):
                    store.upsert_position(
                        USER_ID, ACCOUNT_ID, p.symbol, fill_shares,
                        fill_price, fill_stop,
                        initial_risk_ps=max(fill_price - fill_stop, 0.0),
                        plan_id=p.plan_id)
                    store.update_plan_status(p.plan_id, "FILLED")
                    _slip = fill_price - p.entry_price
                    st.toast(f"{p.symbol} FILLED — slippage {_slip:+.2f}/share "
                             f"vs plan. Position added with initial risk "
                             f"captured.")
                    st.rerun()
else:
    st.caption("No saved plans yet.")
