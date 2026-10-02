import json, glob, copy
from datetime import datetime
from ref_engine import check
G="/tmp/claude-0/-home-claude/09ab03ba-d545-53a5-bc06-74bb2ab79102/scratchpad/m96/mtg-platform/contracts/golden/"
LIGHT={"as_of":"2026-09-25","dominant_index":"^IXIC","index":{"close":17800,"ema20":18050,"sma50":17600,"dist_days_5wk":3},"symbols":{}}
for f in sorted(glob.glob(G+"*.json")):
    g=json.load(open(f)); req=g["request"]; changes=[]
    now=req["candidate"]["timestamp"]
    if g["name"].startswith("004"):
        req["profile"]["open_positions"]=[{"symbol":"XOM","direction":"long","shares":450,"entry":40.0,"stop":35.0,"sector":"Energy"}]
        changes.append("open position moved out of Technology (MSFT 450 @ $400 was 360% of the account and also breached the 50% sector cap, A-23); same 4.5% open risk")
    exp=check(copy.deepcopy(req), datetime.fromisoformat(now.replace("Z","+00:00")), LIGHT)
    # keep the original messages where the rule set is unchanged
    old=g["expected"]
    if [b["rule_id"] for b in exp["blocks"]]==[b["rule_id"] for b in old["blocks"]]:
        exp["blocks"]=old["blocks"]
    else:
        changes.append("expected blocks now %s (was %s)"%([f"{b['rule_id']}:{b['severity']}" for b in exp["blocks"]],[f"{b['rule_id']}:{b['severity']}" for b in old["blocks"]]))
    g["as_of_now"]=now; changes.insert(0,"as_of_now set to the candidate timestamp so the staleness rule is repeatable (v2.2 item 1)")
    if req["regime"]["state"]=="wait":
        g["facts"]=LIGHT; changes.append("facts fixture added: severity 'light' depends on the index data, not the request")
    g["expected"]=exp; g["v2_2_changes"]=changes
    json.dump(g,open("proposed/fixes_to_001_012/"+f.split("/")[-1],"w"),indent=2)
    print(g["name"], "|", "; ".join(changes[1:]) or "as_of_now only")
