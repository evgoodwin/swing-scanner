"""Market facts the rules need beyond the request: the dominant index (Wait-mode severity, M4-L4-S2)
and per-symbol stage / 20 EMA (A-12, W-STOP-SIDE).

Production: read from MTG_FACTS_FILE, written after the close by the daily fetch job (not built yet).
Tests: a request may carry its own "facts" object ONLY when MTG_RULES_TEST_FACTS=1 AND MTG_ENV is
dev, test or local. With the switch on and any other MTG_ENV (or none), the service refuses to start.
Every use is logged.

A facts file that is present but unreadable or malformed makes /check answer 503 (fail closed: no
stage or severity check is silently skipped). Facts older than the previous trading day are not used.

Shape (same for both):
{"as_of": "2026-09-25", "dominant_index": "^IXIC",
 "index": {"close": 17800, "ema20": 18050, "sma50": 17600, "dist_days_5wk": 3},
 "symbols": {"AAPL": {"stage": 2, "ema20": 180.1, "next_earnings_date": "2026-10-29"}}}
"""
import json, logging, os
from datetime import date
from pathlib import Path

from . import validation
from .trading_calendar import previous_trading_day

log = logging.getLogger("rules_service.facts")


class FactsError(Exception):
    pass


class FactsUnavailable(Exception):
    pass


TEST_ENVS = {"dev", "test", "local"}


def test_facts_enabled() -> bool:
    on = os.environ.get("MTG_RULES_TEST_FACTS", "").strip() == "1"
    env = os.environ.get("MTG_ENV", "").strip().lower()
    if on and env not in TEST_ENVS:
        raise FactsError(f"MTG_RULES_TEST_FACTS=1 needs MTG_ENV set to dev, test or local (it is {env or 'unset'!r})")
    return on


def load_store():
    """Facts from the daily job's file; None when no file is configured or written yet.
    Raises FactsUnavailable when the file exists but can't be used."""
    path = os.environ.get("MTG_FACTS_FILE")
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        log.warning("MTG_FACTS_FILE %s not found; severity and stage checks skipped", p)
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("MTG_FACTS_FILE unreadable: %s", e)
        raise FactsUnavailable("market facts file unreadable")
    errs = validation.facts_errors(data)
    if errs or not data.get("as_of"):
        log.error("MTG_FACTS_FILE malformed: %s", "; ".join(errs) or "no as_of")
        raise FactsUnavailable("market facts file malformed")
    return data


def resolve(request_facts, today_et):
    """Return (facts or None, source, store_as_of) for one check. today_et is the check's date in New York."""
    if request_facts is not None:
        if not test_facts_enabled():
            raise FactsError("'facts' in the request is test-only (MTG_RULES_TEST_FACTS=1 on a test machine)")
        errs = validation.facts_errors(request_facts)
        if errs:
            raise FactsError("; ".join(errs))
        log.warning("TEST FACTS FIXTURE used for this check")
        return request_facts, "test_fixture", None
    store = load_store()
    if store is None:
        return None, "none", None
    as_of = date.fromisoformat(store["as_of"])
    if as_of < previous_trading_day(today_et):
        log.warning("market facts dated %s are stale for %s; severity and stage not checked", as_of, today_et)
        return None, "stale", store["as_of"]
    return store, "store", store["as_of"]
