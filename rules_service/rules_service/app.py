"""HTTP layer. Bind to 127.0.0.1:8791 only; the platform on the same box is the only caller.

POST /check   contract v2.1 check-request -> check-result (plus optional as_of_now, v2.2 item 1)
GET  /health  {ok, ruleset_id, engine_version, calendar, facts_as_of, test_facts}
GET  /scan    latest scan file written after the close (MTG_SCAN_FILE); 503 until one exists
"""
import json, logging, os, time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import RULESET_ID, ENGINE_VERSION
from . import facts as facts_mod
from .engine import check, parse_now, CheckInputError, ET
from .validation import request_errors
from .trading_calendar import SOURCE as CALENDAR_SOURCE

logging.basicConfig(level=os.environ.get("MTG_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rules_service")

TEST_FACTS = facts_mod.test_facts_enabled()     # raises at startup if combined with MTG_ENV=production
if TEST_FACTS:
    log.warning("MTG_RULES_TEST_FACTS=1: requests may carry their own market facts. Test machines only.")

DEFAULT_SCAN = Path(__file__).resolve().parent.parent / "data" / "scan_latest.json"

# Only contract fields leave /scan. Anything else in the scan file (e.g. personal overlays) is dropped.
CANDIDATE_KEYS = {"symbol", "direction", "asset_class", "entry", "stop", "targets", "sector", "setup_type",
                  "setup_status", "grade", "self_declared_a_grade", "entry_method", "stop_basis", "source",
                  "next_earnings_date", "timestamp", "size_factor", "stop_pending",
                  "rank", "rs_rising", "base_weeks", "practice_flags"}

app = FastAPI(title="MTG rules service", version=ENGINE_VERSION, docs_url=None, redoc_url=None, openapi_url=None)


def _err(status, msg):
    return JSONResponse(status_code=status, content={"error": msg})


@app.get("/health")
def health():
    try:
        store, facts_state = facts_mod.load_store(), "ok"
    except facts_mod.FactsUnavailable as e:
        store, facts_state = None, str(e)
    return {"ok": facts_state == "ok", "ruleset_id": RULESET_ID, "engine_version": ENGINE_VERSION,
            "calendar": CALENDAR_SOURCE, "facts_as_of": (store or {}).get("as_of"), "facts": facts_state,
            "test_facts": TEST_FACTS}


@app.post("/check")
async def post_check(request: Request):
    t0 = time.perf_counter()
    try:
        body = await request.json()
    except Exception:
        return _err(400, "body must be JSON")
    errs = request_errors(body)
    if errs:
        return _err(400, "; ".join(errs))
    try:
        now = parse_now(body.get("as_of_now"))
        if body.get("as_of_now"):
            log.info("as_of_now=%r", body["as_of_now"])
        facts, source, facts_as_of = facts_mod.resolve(body.get("facts"), now.astimezone(ET).date())
        result = check(body, now, facts, facts_as_of)
    except facts_mod.FactsUnavailable as e:
        return _err(503, str(e))
    except facts_mod.FactsError as e:
        return _err(400, str(e))
    except CheckInputError as e:
        return _err(400, str(e))
    except (ValueError, ArithmeticError):
        return _err(400, "cannot check this request: a value is out of range")
    # No account sizes or positions in the log, only the outcome.
    log.info("check %r %s verdict=%s rules=%s facts=%s %.1fms",
             body["candidate"].get("symbol"), body["candidate"].get("direction"), result["verdict"],
             ",".join(b["rule_id"] for b in result["blocks"]) or "-", source, (time.perf_counter() - t0) * 1000)
    return result


def _clean_candidate(c):
    out = {k: v for k, v in c.items() if k in CANDIDATE_KEYS}
    for k in ("targets", "practice_flags"):          # lists of plain values only
        if k in out:
            out[k] = [v for v in out[k] if isinstance(v, (int, float, str)) and not isinstance(v, bool)] \
                if isinstance(out[k], list) else []
    for k, v in list(out.items()):                     # no nested objects anywhere else
        if isinstance(v, (dict, list)) and k not in ("targets", "practice_flags"):
            out.pop(k)
    return out


@app.get("/scan")
def get_scan():
    path = Path(os.environ.get("MTG_SCAN_FILE", DEFAULT_SCAN))
    if not path.exists():
        return _err(503, "no scan yet")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("scan file unreadable: %s", e)
        return _err(503, "scan file unreadable")
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list) \
            or not all(isinstance(c, dict) for c in raw["candidates"]):
        log.error("scan file has the wrong shape")
        return _err(503, "scan file malformed")
    scan = {k: raw[k] for k in ("as_of", "universe_size") if k in raw}
    if isinstance(raw.get("regime"), dict):
        scan["regime"] = {k: raw["regime"].get(k) for k in ("state", "severity")}
    scan["ruleset_id"] = RULESET_ID
    scan["candidates"] = [_clean_candidate(c) for c in raw["candidates"]]
    dropped = sorted({k for c in raw["candidates"] for k in c} - CANDIDATE_KEYS)
    if dropped:
        log.warning("scan: dropped non-contract fields %s", dropped)
    return scan
