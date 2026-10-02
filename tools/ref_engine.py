"""
Reference calculator for mtg_core@1.2 golden vectors (Ev Goodwin, 1 Oct 2026).
Independent of the platform's JS test: it computes expected results from the
signed Rulebook v1.1 rulings and contract v2.1, then the JS test re-derives the
arithmetic a second way. Not the production engine.
"""
from decimal import Decimal as D, ROUND_HALF_UP, ROUND_FLOOR
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
# NYSE full-day closures, 2026 (engine should use an exchange-calendar library)
NYSE_HOLIDAYS_2026 = {date(2026,1,1), date(2026,1,19), date(2026,2,16), date(2026,4,3),
    date(2026,5,25), date(2026,6,19), date(2026,7,3), date(2026,9,7), date(2026,11,26), date(2026,12,25)}

def is_trading_day(d): return d.weekday() < 5 and d not in NYSE_HOLIDAYS_2026
def prev_trading_day(d):
    d -= timedelta(days=1)
    while not is_trading_day(d): d -= timedelta(days=1)
    return d

def r2(x): return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)
def fl(x): return int(D(x).to_integral_value(rounding=ROUND_FLOOR))
def num(x): return D(str(x))
def out(x):  # Decimal -> JSON number (int when whole)
    return int(x) if x == x.to_integral_value() else float(x)

def cap_pct(d):  # D-4
    return 30 if d < 5 else (15 if d < 8 else 8)

# Verdict precedence (proposed engine convention, most severe first)
PRECEDENCE = ["STOP_PENDING", "NO_TIMING_CALL", "WAIT_MODE", "STAGE_INVALID", "EARNINGS_IN_HOLD",
              "POSITION_LIMIT", "SECTOR_LIMIT", "HEAT_LIMIT", "EXIT_PLAN_INCOMPLETE", "OVERSIZED"]
RULE_VERDICT = {"A-14": "STOP_PENDING", "D-2": "NO_TIMING_CALL", "A-2d": "WAIT_MODE", "A-12": "STAGE_INVALID",
                "A-27": "EARNINGS_IN_HOLD", "A-23b": "POSITION_LIMIT", "A-23": "SECTOR_LIMIT", "A-21": "HEAT_LIMIT"}

def blk(rule, src, tier, sev, msg): return {"rule_id": rule, "source_ref": src, "tier": tier, "severity": sev, "message": msg}

def call_is_current(regime, now_utc):
    if not regime or regime.get("state") is None or not regime.get("as_of"): return False
    today_et = now_utc.astimezone(ET).date()
    call = date.fromisoformat(regime["as_of"])
    return call >= prev_trading_day(today_et)

def severity(state, facts):
    if state != "wait": return None
    ix = facts["index"]
    if num(ix["close"]) < num(ix["sma50"]) and ix["dist_days_5wk"] >= 5: return "severe"
    return "light"   # includes Rick's Wait with the index above its 20 EMA (proposed, I-173)

def check(req, now_utc, facts=None):
    c, p, rg = req["candidate"], req["profile"], req["regime"]
    acct = num(p["account_size"])
    blocks = []
    # heat now
    ops = p.get("open_positions") or []
    if ops:
        current = sum(num(o["shares"]) * abs(num(o["entry"]) - num(o["stop"])) for o in ops) / acct * 100
        count = len(ops)
    else:
        current = num(p.get("declared_heat_pct") or 0); count = p.get("declared_open_count") or 0
    current_call = call_is_current(rg, now_utc)
    state = rg.get("state") if current_call else None
    limit = num(p.get("heat_limit_pct", 5)) if state == "buy" else min(num(p.get("heat_limit_pct", 5)), D(5))
    sev = severity(state, facts) if state else None
    if c.get("stop_pending"):
        return {"shares": 0, "dollar_risk": 0, "pct_account": 0, "verdict": "STOP_PENDING",
                "blocks": [blk("A-14", "M4-L3-S3", "core", "block", "Rick hasn't set the stop yet. Size it once his stop alert arrives.")],
                "size_breakdown": None, "heat": {"current_pct": out(r2(current)), "after_pct": out(r2(current)), "limit_pct": out(limit)},
                "regime": {"state": state, "severity": sev}, "ruleset_id": "mtg_core@1.2"}
    entry, stop = num(c["entry"]), num(c["stop"])
    rps = abs(entry - stop)
    a_grade = (c.get("self_declared_a_grade") or c.get("grade") == "A") and state == "buy" and p.get("risk_pct_a_grade") is not None
    base = num(p["risk_pct_a_grade"]) if a_grade else num(p["risk_pct"])
    risk = base * num(c.get("size_factor", 1) or 1)          # unrounded for sizing; reported rounded
    dpct = rps / entry * 100
    cp = cap_pct(dpct)
    formula = fl(acct * risk / 100 / rps)
    stopcap = fl(acct * cp / 100 / entry)
    shield = fl(acct * D("0.30") / entry)
    computed = min(formula, stopcap, shield)
    binding = [k for k, v in (("A-16", formula), ("A-17", stopcap), ("A-18", shield)) if v == computed]
    after = current + computed * rps / acct * 100             # compared unrounded
    # ---- rules
    if not current_call:
        blocks.append(blk("D-2", "M4-L4-S2-V", "core", "block", "There's no current timing call, so nothing is sized until Rick's next call arrives."))
    if state == "wait" and c["direction"] == "long":
        msg = "The Market Timing Model is in Wait Mode, so no new long entries." + (" Severe conditions: exit open positions." if sev == "severe" else "")
        blocks.append(blk("A-2d", "M4-L4-S2-V", "core", "block", msg))
    if facts and c["symbol"] in facts.get("symbols", {}) and c["direction"] == "long":
        st = facts["symbols"][c["symbol"]].get("stage")
        if st in (3, 4):
            blocks.append(blk("A-12", "M2-L5", "core", "block", f"The stock is in Stage {st}; long setups are valid only in late Stage 1 or Stage 2."))
    if count + 1 > p.get("max_positions", 4):
        blocks.append(blk("A-23b", "M4-L3-S2-V", "core", "block", f"This would be position {count + 1}; your limit is {p.get('max_positions', 4)}."))
    elif count + 1 > 8:
        blocks.append(blk("A-23b", "M4-L3-S2-V", "core", "warn", f"This would be position {count + 1}. Above 8 positions, check you can keep 8-day EMA discipline on every one."))
    # sector cap A-23
    if c.get("sector") is None:
        blocks.append(blk("A-23", "M5-L2-S4-P", "core", "warn", "Sector cap not checked: this trade has no sector."))
    elif not ops and count > 0:
        blocks.append(blk("A-23", "M5-L2-S4-P", "core", "warn", "Sector cap not checked: no position list, only your declared open risk."))
    elif any(o.get("sector") is None for o in ops):
        blocks.append(blk("A-23", "M5-L2-S4-P", "core", "warn", "Sector cap not checked: an open position has no sector."))
    else:
        sec_val = sum(num(o["shares"]) * num(o["entry"]) for o in ops if o.get("sector") == c["sector"]) + computed * entry
        sec_pct = r2(sec_val / acct * 100)
        if sec_pct > 50:
            blocks.append(blk("A-23", "M5-L2-S4-P", "core", "block", f"This would put {out(sec_pct)}% of your account in {c['sector']}, above the 50% sector limit."))
    if after > limit:
        blocks.append(blk("A-21", "M5-L2-S3-V", "core", "block", f"This trade would take your open risk to {out(r2(after))}%, above your {out(limit)}% limit."))
    if c["direction"] == "short":
        blocks.append(blk("P-SHORT", "PRACTICE", "practice", "warn", "Shorts aren't covered by the TradeQuest setup rules. This checks your size and risk limits only."))
    # order: blocks by precedence, then warns
    def key(b):
        v = RULE_VERDICT.get(b["rule_id"])
        return (0 if b["severity"] == "block" else 1, PRECEDENCE.index(v) if v else 99)
    blocks.sort(key=key)
    hard = [b for b in blocks if b["severity"] == "block"]
    verdict = RULE_VERDICT[hard[0]["rule_id"]] if hard else "FITS"
    shares = 0 if hard else computed
    heat = {"current_pct": out(r2(current)), "after_pct": out(r2(after)), "limit_pct": out(limit)}
    if any(b["rule_id"] == "A-21" and b["severity"] == "block" for b in blocks):
        heat["shares_within_limit"] = min(computed, fl(max(D(0), limit - current) / 100 * acct / rps))
    return {"shares": shares, "dollar_risk": out(r2(shares * rps)), "pct_account": out(r2(shares * rps / acct * 100)),
            "verdict": verdict, "blocks": blocks,
            "size_breakdown": {"formula_shares": formula, "stop_cap_shares": stopcap, "shield_shares": shield,
                               "computed_shares": computed, "binding_rules": binding, "stop_distance_pct": out(r2(dpct)),
                               "stop_cap_pct": cp, "risk_pct_used": out(r2(risk))},
            "heat": heat, "regime": {"state": state, "severity": sev}, "ruleset_id": "mtg_core@1.2"}
