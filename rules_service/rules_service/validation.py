"""Request validation against the contract's own JSON Schemas (copied from the platform repo,
contracts/ at v2.1) plus a few checks the schemas can't express. Anything that fails is a 400."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

_DIR = Path(__file__).resolve().parent / "contracts"
_schemas = {f.name: json.loads(f.read_text(encoding="utf-8")) for f in _DIR.glob("*.schema.json")}
_registry = Registry().with_resources(
    [(s["$id"], Resource.from_contents(s)) for s in _schemas.values()]
    + [(name, Resource.from_contents(s)) for name, s in _schemas.items()])
_request = Draft202012Validator(_schemas["check-request.schema.json"], registry=_registry, format_checker=FormatChecker())

ALLOWED_TOP = {"candidate", "profile", "regime", "as_of_now", "facts"}


def request_errors(body):
    """Return a list of plain-language problems; empty when the request can be checked."""
    if not isinstance(body, dict):
        return ["body must be a JSON object"]
    errs = []
    for e in sorted(_request.iter_errors({k: v for k, v in body.items() if k in ("candidate", "profile", "regime")}),
                    key=lambda e: list(e.absolute_path))[:5]:
        where = "/".join(str(p) for p in e.absolute_path) or "request"
        errs.append(f"{where}: {e.message}")
    if errs:
        return errs
    c, p = body["candidate"], body["profile"]
    if not c.get("stop_pending"):
        if c.get("stop") is None:
            errs.append("candidate/stop: required unless stop_pending is true")
        elif (c["direction"] == "long" and not c["stop"] < c["entry"]) or (c["direction"] == "short" and not c["stop"] > c["entry"]):
            errs.append("candidate/stop: must be below entry for a long and above entry for a short")
    for i, o in enumerate(p.get("open_positions") or []):
        if not (isinstance(o.get("entry"), (int, float)) and o["entry"] > 0 and isinstance(o.get("stop"), (int, float)) and o["stop"] >= 0):
            errs.append(f"profile/open_positions/{i}: entry must be above 0 and stop 0 or more")
    return errs


def facts_errors(f):
    """Shape check for a facts object (request fixture or the daily file)."""
    if not isinstance(f, dict):
        return ["facts must be an object"]
    errs = []
    ix = f.get("index")
    if ix is not None:
        if not isinstance(ix, dict):
            errs.append("facts.index must be an object")
        else:
            for k in ("close", "sma50"):
                if not isinstance(ix.get(k), (int, float)) or isinstance(ix.get(k), bool):
                    errs.append(f"facts.index.{k} must be a number")
            if not isinstance(ix.get("dist_days_5wk"), int) or isinstance(ix.get("dist_days_5wk"), bool):
                errs.append("facts.index.dist_days_5wk must be a whole number")
    syms = f.get("symbols")
    if syms is not None:
        if not isinstance(syms, dict) or not all(isinstance(v, dict) for v in syms.values()):
            errs.append("facts.symbols must map each symbol to an object")
        else:
            for s, v in syms.items():
                if v.get("stage") is not None and v["stage"] not in (1, 2, 3, 4):
                    errs.append(f"facts.symbols.{s}.stage must be 1-4")
                if v.get("ema20") is not None and (not isinstance(v["ema20"], (int, float)) or isinstance(v["ema20"], bool)):
                    errs.append(f"facts.symbols.{s}.ema20 must be a number")
    if f.get("as_of") is not None and not (isinstance(f["as_of"], str) and len(f["as_of"]) == 10):
        errs.append("facts.as_of must be a date (YYYY-MM-DD)")
    return errs
