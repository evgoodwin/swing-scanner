"""mtg_core@1.2 Trade Check (contract v2.1, with the proposed v2.2 as_of_now).

Rules implemented: A-14 stop pending, D-2 timing call current, A-2d Wait Mode (longs), A-12 stage
(needs facts), A-23b position count, A-23 sector cap, A-21/C-1 open-risk limit, D-3 A-grade opt-in,
size_factor, A-16/A-17/A-18/A-19 sizing, P-SHORT, W-STOP-SIDE (needs facts).
Not yet: A-27 earnings in hold and A-24 exit plan (both await inputs/rulings; review item 10),
OVERSIZED (no input), crypto (pending).

Conventions (ruleset 'conventions' block, awaiting Deron's confirmation): Decimal arithmetic; size
from the unrounded risk %; heat compared unrounded; prices never rounded; outputs half-up to 2 dp.
"""
from datetime import date, datetime, timezone
from decimal import Decimal as D, ROUND_FLOOR, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from . import RULESET_ID, ENGINE_VERSION
from .trading_calendar import previous_trading_day

ET = ZoneInfo("America/New_York")

# v1.2 measures open risk as shares x |entry - stop|. Proposed P10 ("directional": a stop past entry
# on the profit side counts 0) awaits a ruling; change only with a new ruleset id.
OPEN_RISK_MODE = "abs"

PRECEDENCE = ["STOP_PENDING", "NO_TIMING_CALL", "WAIT_MODE", "STAGE_INVALID", "EARNINGS_IN_HOLD",
              "POSITION_LIMIT", "SECTOR_LIMIT", "HEAT_LIMIT", "EXIT_PLAN_INCOMPLETE", "OVERSIZED"]
RULE_VERDICT = {"A-14": "STOP_PENDING", "D-2": "NO_TIMING_CALL", "A-2d": "WAIT_MODE", "A-12": "STAGE_INVALID",
                "A-27": "EARNINGS_IN_HOLD", "A-23b": "POSITION_LIMIT", "A-23": "SECTOR_LIMIT", "A-21": "HEAT_LIMIT",
                "A-24": "EXIT_PLAN_INCOMPLETE"}
SECTOR_CAP_PCT = D(50)          # A-23
CORE_HEAT_PCT = D(5)            # C-1
WARN_POSITIONS_ABOVE = 8        # A-23b
SHIELD_PCT = D(30)              # A-18


class CheckInputError(ValueError):
    """Request can't be checked (HTTP 400)."""


def _num(x):
    if x is None or isinstance(x, bool):
        raise CheckInputError(f"expected a number, got {x!r}")
    return D(str(x))


def _r2(x): return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)
def _floor(x): return int(D(x).to_integral_value(rounding=ROUND_FLOOR))
def _out(x): return int(x) if x == x.to_integral_value() else float(x)


def _blk(rule, src, tier, sev, msg):
    return {"rule_id": rule, "source_ref": src, "tier": tier, "severity": sev, "message": msg}


def stop_cap_pct(dist_pct):     # A-17 bands, gaps closed by D-4
    return 30 if dist_pct < 5 else (15 if dist_pct < 8 else 8)


def position_risk(o, mode=OPEN_RISK_MODE):
    e, s = _num(o["entry"]), _num(o["stop"])
    if mode == "abs":
        return abs(e - s)
    return max(D(0), e - s) if o.get("direction", "long") == "long" else max(D(0), s - e)


def call_is_current(regime, now_utc):
    """D-2: the call is current if dated on or after the previous NYSE trading day (ET)."""
    if not regime or regime.get("state") is None or not regime.get("as_of"):
        return False
    today_et = now_utc.astimezone(ET).date()
    return date.fromisoformat(regime["as_of"]) >= previous_trading_day(today_et)


def wait_severity(facts):
    """M4-L4-S2: severe = index closes below its 50-day SMA AND 5+ distribution days in 5 weeks.
    Otherwise light (including Rick's Wait with the index above its 20 EMA; proposed, I-173).
    None when there are no facts."""
    ix = (facts or {}).get("index")
    if not ix:
        return None
    if _num(ix["close"]) < _num(ix["sma50"]) and int(ix["dist_days_5wk"]) >= 5:
        return "severe"
    return "light"


def parse_now(as_of_now):
    if as_of_now is None:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(as_of_now).replace("Z", "+00:00"))
    except ValueError:
        raise CheckInputError("as_of_now must be an ISO date-time")
    if dt.tzinfo is None:
        raise CheckInputError("as_of_now needs a time zone (e.g. ...Z)")
    return dt.astimezone(timezone.utc)


def check(req, now_utc, facts=None, facts_as_of=None):
    """req must already have passed validation.request_errors (the HTTP layer does this)."""
    c, p, rg = req["candidate"], req["profile"], req.get("regime") or {}
    acct = _num(p["account_size"])
    if acct <= 0:
        raise CheckInputError("account_size must be above 0")
    direction = c.get("direction")
    if direction not in ("long", "short"):
        raise CheckInputError("direction must be long or short")

    ops = p.get("open_positions") or []
    if ops:
        current = sum(_num(o["shares"]) * position_risk(o) for o in ops) / acct * 100
        count = len(ops)
    else:
        current = _num(p.get("declared_heat_pct") or 0)
        count = p.get("declared_open_count") or 0

    is_current = call_is_current(rg, now_utc)
    state = rg.get("state") if is_current else None
    personal = _num(p.get("heat_limit_pct", 5))
    limit = personal if state == "buy" else min(personal, CORE_HEAT_PCT)
    sev = wait_severity(facts) if state == "wait" else None
    regime_out = {"state": state, "severity": sev}
    meta = {"ruleset_id": RULESET_ID, "engine_version": ENGINE_VERSION}
    if facts_as_of:
        meta["engine_data_as_of"] = facts_as_of

    if c.get("stop_pending"):
        return {"shares": 0, "dollar_risk": 0, "pct_account": 0, "verdict": "STOP_PENDING",
                "blocks": [_blk("A-14", "M4-L3-S3", "core", "block",
                                "Rick hasn't set the stop yet. Size it once his stop alert arrives.")],
                "size_breakdown": None,
                "heat": {"current_pct": _out(_r2(current)), "after_pct": _out(_r2(current)), "limit_pct": _out(limit)},
                "regime": regime_out, **meta}

    entry, stop = _num(c["entry"]), _num(c["stop"])
    if entry <= 0:
        raise CheckInputError("entry must be above 0")
    rps = (entry - stop) if direction == "long" else (stop - entry)
    if rps <= 0:
        # The platform rejects these before calling; refuse rather than size a stop on the wrong side.
        raise CheckInputError("stop must be below entry for a long and above entry for a short")

    a_grade = ((c.get("self_declared_a_grade") or c.get("grade") == "A") and state == "buy"
               and p.get("risk_pct_a_grade") is not None)
    base = _num(p["risk_pct_a_grade"]) if a_grade else _num(p["risk_pct"])
    size_factor = c.get("size_factor")
    risk = base * (_num(size_factor) if size_factor is not None else D(1))
    dist_pct = rps / entry * 100
    cap = stop_cap_pct(dist_pct)
    formula = _floor(acct * risk / 100 / rps)                       # A-16
    stopcap = _floor(acct * cap / 100 / entry)                       # A-17
    shield = _floor(acct * SHIELD_PCT / 100 / entry)                 # A-18
    computed = min(formula, stopcap, shield)                         # A-19
    binding = [k for k, v in (("A-16", formula), ("A-17", stopcap), ("A-18", shield)) if v == computed]
    after = current + computed * rps / acct * 100

    blocks = []
    if not is_current:
        blocks.append(_blk("D-2", "M4-L4-S2-V", "core", "block",
                           "There's no current timing call, so nothing is sized until Rick's next call arrives."))
    if state == "wait" and direction == "long":
        msg = "The Market Timing Model is in Wait Mode, so no new long entries."
        if sev == "severe":
            msg += " Severe conditions: exit open positions."
        blocks.append(_blk("A-2d", "M4-L4-S2-V", "core", "block", msg))
    sym_facts = ((facts or {}).get("symbols") or {}).get(c.get("symbol"), {})
    if direction == "long" and sym_facts.get("stage") in (3, 4):
        blocks.append(_blk("A-12", "M2-L5", "core", "block",
                           f"The stock is in Stage {sym_facts['stage']}; long setups are valid only in late Stage 1 or Stage 2."))
    max_pos = p.get("max_positions", 4)
    if count + 1 > max_pos:
        blocks.append(_blk("A-23b", "M4-L3-S2-V", "core", "block",
                           f"This would be position {count + 1}; your limit is {max_pos}."))
    elif count + 1 > WARN_POSITIONS_ABOVE:
        blocks.append(_blk("A-23b", "M4-L3-S2-V", "core", "warn",
                           f"This would be position {count + 1}. Above 8 positions, check you can keep 8-day EMA discipline on every one."))
    if c.get("sector") is None:
        blocks.append(_blk("A-23", "M5-L2-S4-P", "core", "warn", "Sector cap not checked: this trade has no sector."))
    elif not ops and count > 0:
        blocks.append(_blk("A-23", "M5-L2-S4-P", "core", "warn",
                           "Sector cap not checked: no position list, only your declared open risk."))
    elif any(o.get("sector") is None for o in ops):
        blocks.append(_blk("A-23", "M5-L2-S4-P", "core", "warn", "Sector cap not checked: an open position has no sector."))
    else:
        sec_val = sum(_num(o["shares"]) * _num(o["entry"]) for o in ops if o.get("sector") == c["sector"]) + computed * entry
        sec_pct = sec_val / acct * 100                               # compared unrounded (conventions)
        if sec_pct > SECTOR_CAP_PCT:
            blocks.append(_blk("A-23", "M5-L2-S4-P", "core", "block",
                               f"This would put {_out(_r2(sec_pct))}% of your account in {c['sector']}, above the 50% sector limit."))
    if after > limit:
        blocks.append(_blk("A-21", "M5-L2-S3-V", "core", "block",
                           f"This trade would take your open risk to {_out(_r2(after))}%, above your {_out(limit)}% limit."))
    if (direction == "long" and c.get("stop_basis") == "ema20" and sym_facts.get("ema20") is not None
            and entry < _num(sym_facts["ema20"])):
        blocks.append(_blk("W-STOP-SIDE", "M4-L3-S3", "core", "warn",
                           "Your stop is based on the 20 EMA, but the entry is below the 20 EMA, so the stop would sit above your entry."))
    if direction == "short":
        blocks.append(_blk("P-SHORT", "PRACTICE", "practice", "warn",
                           "Shorts aren't covered by the TradeQuest setup rules. This checks your size and risk limits only."))

    def order(b):
        v = RULE_VERDICT.get(b["rule_id"])
        return (0 if b["severity"] == "block" else 1, PRECEDENCE.index(v) if v else 99)
    blocks.sort(key=order)
    hard = [b for b in blocks if b["severity"] == "block"]
    verdict = RULE_VERDICT[hard[0]["rule_id"]] if hard else "FITS"
    shares = 0 if hard else computed
    heat = {"current_pct": _out(_r2(current)), "after_pct": _out(_r2(after)), "limit_pct": _out(limit)}
    if any(b["rule_id"] == "A-21" and b["severity"] == "block" for b in blocks):
        heat["shares_within_limit"] = min(computed, _floor(max(D(0), limit - current) / 100 * acct / rps))
    return {"shares": shares, "dollar_risk": _out(_r2(shares * rps)), "pct_account": _out(_r2(shares * rps / acct * 100)),
            "verdict": verdict, "blocks": blocks,
            "size_breakdown": {"formula_shares": formula, "stop_cap_shares": stopcap, "shield_shares": shield,
                               "computed_shares": computed, "binding_rules": binding,
                               "stop_distance_pct": _out(_r2(dist_pct)), "stop_cap_pct": cap,
                               "risk_pct_used": _out(_r2(risk))},
            "heat": heat, "regime": regime_out, **meta}
