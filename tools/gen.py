import json, copy
from datetime import datetime
from ref_engine import check

TS = "2026-09-28T13:30:00Z"           # Monday; Friday 25 Sep call is current (previous trading day)
CALL = {"state": "buy", "as_of": "2026-09-25"}
LIGHT = {"as_of": "2026-09-25", "dominant_index": "^IXIC", "index": {"close": 17800, "ema20": 18050, "sma50": 17600, "dist_days_5wk": 3}, "symbols": {}}
SEVERE = {"as_of": "2026-09-25", "dominant_index": "^IXIC", "index": {"close": 17100, "ema20": 18050, "sma50": 17600, "dist_days_5wk": 6}, "symbols": {}}
ABOVE20 = {"as_of": "2026-09-29", "dominant_index": "^IXIC", "index": {"close": 18400, "ema20": 18250, "sma50": 17900, "dist_days_5wk": 4}, "symbols": {}}

def cand(**kw):
    c = {"symbol": "AAPL", "direction": "long", "entry": 182.5, "stop": 176.0, "source": "WD_ALERT",
         "asset_class": "equity", "sector": "Technology", "timestamp": TS, "targets": [195]}
    c.update(kw); return {k: v for k, v in c.items() if v is not None or k in ("sector", "stop")}
def prof(**kw):
    p = {"account_size": 50000, "risk_pct": 1.0, "risk_pct_a_grade": None, "heat_limit_pct": 5, "max_positions": 4, "open_positions": []}
    p.update(kw); return p
def pos(sym, sector, shares, entry, stop, direction="long"):
    return {"symbol": sym, "direction": direction, "shares": shares, "entry": entry, "stop": stop, "sector": sector}
XOM45 = pos("XOM", "Energy", 450, 40.0, 35.0)       # 4.5% open risk, 36% of account
XOM40 = pos("XOM", "Energy", 400, 40.0, 35.0)       # 4.0% open risk, 32% of account
SMALL = [pos("JPM", "Financials", 10, 250.0, 232.0), pos("LLY", "Health Care", 3, 800.0, 740.0),
         pos("CAT", "Industrials", 8, 350.0, 327.5), pos("COST", "Consumer Staples", 3, 900.0, 840.0),
         pos("NEE", "Utilities", 36, 75.0, 70.0), pos("AMZN", "Consumer Discretionary", 15, 190.0, 178.0),
         pos("PLD", "Real Estate", 20, 120.0, 111.0), pos("LIN", "Materials", 6, 450.0, 420.0)]   # each about 5% of the account, $180 open risk

V = []   # (folder, name, note, request, now, facts, requires)
def add(folder, name, note, req, now=TS, facts=None, requires=None):
    V.append((folder, name, note, req, now, facts, requires or []))

R = lambda c, p, r=CALL: {"candidate": c, "profile": p, "regime": r}
# ---------- golden: computable from the request alone, signed rules ----------
add("golden", "013_personal_heat_7_buy_fits", "Personal heat limit 7% (C-1) honoured in Buy Mode: 4.5% open + 0.99% = 5.49% fits under 7%.",
    R(cand(), prof(heat_limit_pct=7, open_positions=[XOM45])))
add("golden", "014_quarter_size_call", "Rick called quarter size (size_factor 0.25). Risk 1% x 0.25 = 0.25%. Formula 19 binds.",
    R(cand(size_factor=0.25), prof()))
add("golden", "015_a_grade_with_half_size", "A-grade opt-in 1.5% x Rick's half size 0.5 = 0.75% risk (contract: multiply after choosing the A-grade value). Formula 57 binds.",
    R(cand(self_declared_a_grade=True, size_factor=0.5), prof(risk_pct_a_grade=1.5)))
add("golden", "016_a_grade_not_applied_without_call", "A-grade 1.5% applies only in Buy Mode (D-3). With no timing call it is not applied: computed size uses 1%, and NO_TIMING_CALL blocks.",
    R(cand(self_declared_a_grade=True), prof(risk_pct_a_grade=1.5), {"state": None, "as_of": None}))
add("golden", "017_stop_band_boundary_5pct", "Stop exactly 5.00% from entry is in the 15% band (D-4: 5% to under 8%). Cap 75 beats formula 100.",
    R(cand(symbol="ABC", entry=100.0, stop=95.0, targets=[115]), prof()))
add("golden", "018_stop_band_boundary_8pct", "Stop exactly 8.00% from entry is in the 8% band (D-4: 8% and over). Cap 40 beats formula 62.",
    R(cand(symbol="ABC", entry=100.0, stop=92.0, targets=[124]), prof()))
add("golden", "019_heat_exactly_at_limit_fits", "4.00% open + exactly 1.00% = 5.00%, equal to the 5% limit: fits (limit is a maximum, A-21).",
    R(cand(symbol="ABC", entry=50.0, stop=48.0, targets=[57.5]), prof(open_positions=[XOM40])))
add("golden", "020_position_limit_blocks", "Four positions open, personal limit 4 (A-23b default). A fifth is blocked: POSITION_LIMIT.",
    R(cand(), prof(open_positions=SMALL[:4])))
add("golden", "021_ninth_position_warns", "Personal limit 10 (A-23b cap). Eight open; the ninth fits with a warning above 8 (per Rick, signed).",
    R(cand(), prof(max_positions=10, open_positions=SMALL)))
add("golden", "022_sector_cap_blocks", "Technology already $14,985 (29.97%) in MSFT. Adding 76 AAPL ($13,870) takes Technology to 57.71% of the account, above the 50% sector limit (A-23). Measured at entry prices against account size.",
    R(cand(), prof(open_positions=[pos("MSFT", "Technology", 37, 405.0, 395.0)])))
add("golden", "023_sector_unknown_warns", "Candidate has no sector: A-23 is skipped and a warn block says so (contract candidate.sector). Trade fits.",
    R(cand(sector=None), prof()))
add("golden", "024_declared_positions_sector_warns", "Phase 1 stand-ins only (declared 2.0% open risk, 2 positions, no list): sector cap can't be checked, warn. Trade fits.",
    R(cand(), prof(declared_heat_pct=2.0, declared_open_count=2)))
add("golden", "025_breakeven_and_short_open_risk", "Open risk counts |entry - stop| per position: a breakeven long adds 0, an open short adds 1.0%. Current 1.0% + 0.99% = 1.99%.",
    R(cand(), prof(open_positions=[pos("XOM", "Energy", 300, 40.0, 40.0), pos("TSLA", "Consumer Discretionary", 50, 250.0, 260.0, "short")])))
add("golden", "026_sub_dollar_price_precision", "Prices are never rounded: entry 0.5432, stop 0.5012, risk 0.0420 a share. Formula 11904 binds; dollar risk $499.97.",
    R(cand(symbol="XYZ", entry=0.5432, stop=0.5012, sector="Health Care", targets=[0.62]), prof()))
# ---------- proposed: need v2.2 as_of_now, a market-facts fixture, or a pending ruling ----------
add("proposed", "P01_tuesday_after_labor_day_current", "Edge case 5: Tuesday 8 Sep after the Labor Day holiday; Friday 4 Sep's call is the previous trading day's, so current. Needs as_of_now (v2.2 item 1).",
    R(cand(timestamp="2026-09-08T13:30:00Z"), prof(), {"state": "buy", "as_of": "2026-09-04"}), now="2026-09-08T13:30:00Z", requires=["as_of_now"])
add("proposed", "P02_call_two_trading_days_old", "Wednesday 30 Sep with Monday 28 Sep's call: older than the previous trading day, so NO_TIMING_CALL. Needs as_of_now.",
    R(cand(timestamp="2026-09-30T14:00:00Z"), prof(), {"state": "buy", "as_of": "2026-09-28"}), now="2026-09-30T14:00:00Z", requires=["as_of_now"])
add("proposed", "P03_before_8am_previous_day_current", "Tuesday 29 Sep 7:00 AM ET, before the day's call: Monday's call is current. Needs as_of_now.",
    R(cand(timestamp="2026-09-29T11:00:00Z"), prof(), {"state": "buy", "as_of": "2026-09-28"}), now="2026-09-29T11:00:00Z", requires=["as_of_now"])
add("proposed", "P04_monday_after_thanksgiving_stale", "Monday 30 Nov with Wednesday 25 Nov's call: Friday 27 Nov was a trading day (early close), so the call is stale. Needs as_of_now.",
    R(cand(timestamp="2026-11-30T14:30:00Z"), prof(), {"state": "buy", "as_of": "2026-11-25"}), now="2026-11-30T14:30:00Z", requires=["as_of_now"])
add("proposed", "P05_severe_wait_blocks_and_says_exit", "Wait Mode, severe: Nasdaq below its 50-day with 6 distribution days in 5 weeks (M4-L4-S2, A-1). Block message says to exit open positions (v2.2 item 3). Needs the facts fixture.",
    R(cand(), prof(), {"state": "wait", "as_of": "2026-09-25"}), facts=SEVERE, requires=["facts_fixture"])
add("proposed", "P06_wait_with_index_above_20ema_is_light", "Rick's Wait on 30 Sep with the Nasdaq above its 20 EMA (a judgment call on breadth). Proposed: severity is light whenever Rick says Wait and the severe test isn't met (I-173). Needs the facts fixture and Deron's OK.",
    R(cand(timestamp="2026-09-30T14:00:00Z"), prof(), {"state": "wait", "as_of": "2026-09-30"}), now="2026-09-30T14:00:00Z", facts=ABOVE20, requires=["facts_fixture", "ruling"])
add("proposed", "P07_short_in_wait_heat_limit_5", "Short on a Wait day with personal limit 7%: limit drops to 5% outside Buy Mode (C-1). 4.5% open + 1.0% = 5.5% blocks; 50 shares fit. Needs the facts fixture for severity.",
    R(cand(symbol="NFLX", direction="short", entry=120.0, stop=125.0, targets=[105]), prof(heat_limit_pct=7, open_positions=[XOM45]), {"state": "wait", "as_of": "2026-09-25"}), facts=LIGHT, requires=["facts_fixture"])
add("proposed", "P09_risk_rounded_after_sizing", "A-grade 1.5% x quarter size 0.25 = 0.375% risk. Size from the unrounded 0.375% ($187.50 / $6.50 = 28.8 -> 28), report risk_pct_used 0.38. Rounding first (0.38% -> 29 shares) oversizes. The platform's golden.test.js rounds first and needs the same fix.",
    R(cand(self_declared_a_grade=True, size_factor=0.25), prof(risk_pct_a_grade=1.5)), requires=["platform_test_fix"])
add("proposed", "P08_stage_4_blocks_long", "AAPL in Stage 4 per the 10/40-week MAs (A-12, D-5, M2-L5): long setups invalid. Needs the facts fixture; M2-L5 script not yet verified.",
    R(cand(), prof()), facts={**LIGHT, "symbols": {"AAPL": {"stage": 4}}}, requires=["facts_fixture"])

for folder, name, note, req, now, facts, requires in V:
    exp = check(copy.deepcopy(req), datetime.fromisoformat(now.replace("Z", "+00:00")), facts or LIGHT)
    doc = {"name": name, "note": note, "ruleset": "mtg_core@1.2", "request": req, "expected": exp}
    if requires: doc["requires"] = requires
    if "as_of_now" in requires: doc["as_of_now"] = now
    if facts: doc["facts"] = facts
    json.dump(doc, open(f"{folder}/{name}.json", "w"), indent=2)
    hard = [b["rule_id"] for b in exp["blocks"]]
    print(f"{name:45s} {exp['verdict']:15s} sh={exp['shares']:<6} comp={exp['size_breakdown']['computed_shares'] if exp['size_breakdown'] else '-':<6} risk={exp['dollar_risk']:<8} heat={exp['heat']} sev={exp['regime']['severity']} rules={hard}")
