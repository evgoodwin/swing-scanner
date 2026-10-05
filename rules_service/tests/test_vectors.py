"""Runs every contract vector through the HTTP API (TestClient), with the test facts switch on.
Golden 001-012 are the corrected versions (as_of_now + facts) proposed in the Oct 2 review."""
import json, os
from pathlib import Path

import pytest

os.environ["MTG_RULES_TEST_FACTS"] = "1"
os.environ["MTG_ENV"] = "test"
from fastapi.testclient import TestClient   # noqa: E402
from rules_service.app import app            # noqa: E402

client = TestClient(app)
ROOT = Path(__file__).resolve().parent.parent / "vectors"
FILES = sorted((ROOT / "golden").glob("*.json")) + sorted((ROOT / "proposed").glob("*.json"))
# Expected differences: vectors that assume a proposal this ruleset hasn't adopted.
XFAIL = {"P10_locked_profit_stop_counts_zero": "open-risk measure is |entry - stop| in mtg_core@1.2; P10 awaits a ruling"}
IGNORE = {"engine_version", "engine_data_as_of"}
# Block messages are screen wording, not rule outcomes. Vectors 001-012 carry the platform's wording and
# 013+ carry ours; they differ for A-2d, A-21, A-14, D-2 and P-SHORT. Compared without the text until
# one wording is agreed (README, open item 4).


def strip_messages(res):
    res = {k: v for k, v in res.items() if k not in IGNORE}
    res["blocks"] = [{k: v for k, v in b.items() if k != "message"} for b in res.get("blocks", [])]
    return res


def body_for(doc):
    req = dict(doc["request"])
    req["as_of_now"] = doc.get("as_of_now") or req["candidate"].get("timestamp")
    if doc.get("facts"):
        req["facts"] = doc["facts"]
    return req


@pytest.mark.parametrize("path", FILES, ids=[f.stem for f in FILES])
def test_vector(path):
    doc = json.loads(path.read_text())
    if path.stem in XFAIL:
        pytest.xfail(XFAIL[path.stem])
    r = client.post("/check", json=body_for(doc))
    assert r.status_code == 200, r.text
    assert strip_messages(r.json()) == strip_messages(doc["expected"])
