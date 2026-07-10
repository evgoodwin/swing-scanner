"""
swing_risk.sizing
=================
The Phase 2 core: builds a validated TradePlan (§4.6).

    size = (equity x effective_risk_pct) / (entry - stop)

with:
  - regime-tiered risk % (instrument's OWN benchmark regime -- v1.2)
  - portfolio heat check on CURRENT heat (v1.4: managed stops reduce heat)
  - R/R validation against config minimum
  - grade gate (C = pass unless config allows)
  - pre-trade verification checklist (auto-evaluated, §4.6)

All rule parameters come from SizingConfig (P2). No magic numbers here.
"""

from __future__ import annotations

import math
from dataclasses import asdict

from .models import (
    TradePlan, SizingConfig, ExitConfig, RegimeSnapshot,
    StopSuggestion, RegimeMode, SetupGrade, PlanStatus, Direction,
)


# ----------------------------------------------------------------------------
# Open-position summary the sizer needs (fed by app / later by TradeRecords)
# ----------------------------------------------------------------------------

def portfolio_current_heat_pct(open_positions: list[dict], equity: float) -> float:
    """
    open_positions: [{symbol, shares, avg_entry, current_stop, direction}]
    Current risk per position = max(0, protective distance) * shares.
    Breakeven/locked stops contribute zero ("free trades", v1.4).
    """
    if equity <= 0:
        return 0.0
    total = 0.0
    for p in open_positions:
        shares = float(p.get("shares", 0))
        entry = float(p.get("avg_entry", 0))
        stop = float(p.get("current_stop", 0))
        direction = str(p.get("direction", "LONG")).upper()
        if shares <= 0 or entry <= 0 or stop <= 0:
            continue
        risk_per_share = (entry - stop) if direction == "LONG" else (stop - entry)
        total += max(0.0, risk_per_share) * shares
    return round(total / equity * 100.0, 2)


# ----------------------------------------------------------------------------
# Plan builder
# ----------------------------------------------------------------------------

def build_trade_plan(
    *,
    symbol: str,
    entry_price: float,
    stop_price: float,
    stop_basis: str,
    equity: float,
    regime: RegimeSnapshot,
    sizing: SizingConfig,
    exit_cfg: ExitConfig,
    open_positions: list[dict],
    setup_type: str = "",
    setup_grade: str = "B",
    direction: str = "LONG",
    target_price: float | None = None,
    stop_suggestions: list[StopSuggestion] | None = None,
    asset_class: str = "EQUITY",
    benchmark_id: str = "QQQ",
    thesis: str = "",
    user_id: str = "ev",
    account_id: str = "default",
    scale_split: tuple[float, ...] = (1.0,),
) -> TradePlan:
    """
    Returns a TradePlan with is_valid, blockers, warnings, and the full
    auto-evaluated checklist populated. Never raises on a bad plan --
    a bad plan is a valid *object* with blockers, so the UI can show why.
    """
    plan = TradePlan(
        symbol=symbol.upper(),
        asset_class=asset_class,
        benchmark_id=benchmark_id,
        user_id=user_id,
        account_id=account_id,
        sizing_config_id=sizing.config_id,
        exit_config_id=exit_cfg.config_id,
        regime_ruleset_id=regime.ruleset_id,
        regime_mode=regime.mode.value if isinstance(regime.mode, RegimeMode) else str(regime.mode),
        regime_composite=(regime.composite_mode.value
                          if isinstance(regime.composite_mode, RegimeMode)
                          else str(regime.composite_mode)),
        regime_detail=regime.detail,
        setup_type=setup_type,
        setup_grade=setup_grade,
        direction=direction,
        entry_price=float(entry_price),
        stop_price=float(stop_price),
        stop_basis=stop_basis,
        target_price=float(target_price) if target_price else None,
        equity=float(equity),
        thesis=thesis,
        stop_suggestions=[asdict(s) for s in (stop_suggestions or [])],
    )

    checklist: dict[str, tuple[bool, str]] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    long_side = direction.upper() == "LONG"

    # ---- 1. Structural sanity -------------------------------------------------
    risk_per_share = (entry_price - stop_price) if long_side else (stop_price - entry_price)
    ok = risk_per_share > 0
    checklist["stop_protective_side"] = (ok, "Stop is on the protective side of entry"
                                         if ok else "Stop is NOT below entry (long) / above entry (short)")
    if not ok:
        blockers.append("Stop must be on the protective side of the entry.")

    # ---- 2. Market timing gate (v1.2: instrument's own benchmark) -------------
    mode = plan.regime_mode
    gate_ok = True
    if long_side and mode == RegimeMode.RED.value and sizing.red_mode_blocks_new_longs:
        gate_ok = False
        blockers.append(f"Regime gate: {benchmark_id} is RED -- new longs blocked by "
                        f"{sizing.config_id}.")
    checklist["market_timing_gate"] = (
        gate_ok,
        f"{benchmark_id} regime {mode} (composite {plan.regime_composite})"
        + ("" if gate_ok else " -- BLOCKED"),
    )
    if long_side and mode == RegimeMode.YELLOW.value:
        warnings.append(f"{benchmark_id} regime is YELLOW: risk tier reduced to "
                        f"{sizing.risk_pct_by_mode.get('YELLOW')}%.")

    # ---- 3. Setup grade gate ---------------------------------------------------
    grade_ok = not (setup_grade == SetupGrade.C.value and not sizing.allow_grade_c)
    checklist["setup_grade"] = (grade_ok, f"Grade {setup_grade}"
                                + ("" if grade_ok else " -- C = pass per config"))
    if not grade_ok:
        blockers.append("Setup graded C: per MTG discipline, C-grade setups are a pass.")

    # ---- 4. Sizing ---------------------------------------------------------------
    base_risk_pct = float(sizing.risk_pct_by_mode.get(mode, 0.0))
    plan.risk_pct = base_risk_pct
    plan.risk_dollars = round(equity * base_risk_pct / 100.0, 2)

    shares = 0
    if risk_per_share > 0 and plan.risk_dollars > 0:
        shares = math.floor(plan.risk_dollars / risk_per_share)
    plan.shares_planned = int(shares)
    plan.position_dollars = round(shares * entry_price, 2)

    ok = shares > 0
    checklist["position_size"] = (
        ok,
        f"{shares} shares = ${plan.risk_dollars:,.0f} risk / "
        f"${risk_per_share:,.2f} per share" if ok else
        "Computed size is zero (risk budget too small for stop distance)",
    )
    if not ok and gate_ok and grade_ok:
        blockers.append("Position size computes to zero shares.")

    # allocation cap
    if equity > 0 and plan.position_dollars / equity * 100.0 > sizing.max_single_position_pct:
        capped = math.floor((equity * sizing.max_single_position_pct / 100.0) / entry_price)
        warnings.append(
            f"Allocation cap: {plan.position_dollars/equity*100:.1f}% of equity exceeds "
            f"{sizing.max_single_position_pct:.0f}% max -- shares capped "
            f"{plan.shares_planned} -> {capped}."
        )
        plan.shares_planned = capped
        plan.position_dollars = round(capped * entry_price, 2)
        plan.risk_dollars = round(capped * risk_per_share, 2)

    # scale plan (per-entry split, e.g. (0.5, 0.5))
    plan.scale_plan = []
    remaining = plan.shares_planned
    for i, frac in enumerate(scale_split):
        leg_shares = round(plan.shares_planned * frac) if i < len(scale_split) - 1 else remaining
        remaining -= leg_shares
        plan.scale_plan.append({"leg": i + 1, "fraction": frac,
                                "shares": leg_shares,
                                "trigger": "initial trigger" if i == 0 else "add point"})

    # ---- 5. R/R ------------------------------------------------------------------
    if target_price and risk_per_share > 0:
        reward = (target_price - entry_price) if long_side else (entry_price - target_price)
        rr = reward / risk_per_share if risk_per_share else 0.0
        plan.rr_ratio = round(rr, 2)
        ok = rr >= sizing.min_rr_ratio
        checklist["risk_reward"] = (ok, f"R/R {rr:.2f}:1 vs minimum {sizing.min_rr_ratio:.1f}:1")
        if not ok:
            blockers.append(f"R/R {rr:.2f}:1 below config minimum {sizing.min_rr_ratio:.1f}:1.")
        elif rr < sizing.preferred_rr_ratio:
            warnings.append(f"R/R {rr:.2f}:1 meets minimum but is below preferred "
                            f"{sizing.preferred_rr_ratio:.1f}:1.")
    else:
        checklist["risk_reward"] = (True, "No fixed target (trail-based exit config)")

    # ---- 6. Portfolio heat (v1.4 current heat) ------------------------------------
    heat_before = portfolio_current_heat_pct(open_positions, equity)
    add_heat = (plan.risk_dollars / equity * 100.0) if equity > 0 else 0.0
    heat_after = round(heat_before + add_heat, 2)
    plan.heat_before_pct = heat_before
    plan.heat_after_pct = heat_after
    ok = heat_after <= sizing.max_portfolio_heat_pct
    checklist["portfolio_heat"] = (
        ok, f"Current heat {heat_before:.2f}% + {add_heat:.2f}% = {heat_after:.2f}% "
            f"vs {sizing.max_portfolio_heat_pct:.1f}% max")
    if not ok:
        blockers.append(
            f"Portfolio heat would reach {heat_after:.2f}%, exceeding "
            f"{sizing.max_portfolio_heat_pct:.1f}% max. Reduce size, tighten stops "
            f"elsewhere, or pass.")

    # position count
    if len(open_positions) + 1 > sizing.max_positions:
        warnings.append(f"Open positions would be {len(open_positions)+1}, above "
                        f"config max {sizing.max_positions}.")

    # ---- finalize -------------------------------------------------------------------
    plan.checklist = {k: {"ok": v[0], "msg": v[1]} for k, v in checklist.items()}
    plan.blockers = blockers
    plan.warnings = warnings
    plan.is_valid = len(blockers) == 0 and plan.shares_planned > 0
    plan.status = PlanStatus.DRAFT.value
    return plan
