"""Replay the contract vectors against a RUNNING rules service over HTTP (standard library only).

    python tools/replay.py                               # http://127.0.0.1:8791, vectors/ next to this file
    python tools/replay.py --url http://127.0.0.1:8791 --dir ../vectors

Sends each vector's request with as_of_now (the vector's own, else the candidate's timestamp), so the
result doesn't depend on today's date. Vectors that need the market-facts fixture are skipped unless
--with-facts is given AND the service runs with MTG_RULES_TEST_FACTS=1 (test machines only); the
in-process test suite (python -m pytest -q) covers them. Compares rule outcomes, not message wording.
Exit code 0 when everything compared matches.
"""
import argparse, json, sys, urllib.request, urllib.error
from pathlib import Path

XFAIL = {"P10_locked_profit_stop_counts_zero": "open-risk measure awaits a ruling"}
IGNORE = {"engine_version", "engine_data_as_of"}


def outcome(res):
    res = {k: v for k, v in res.items() if k not in IGNORE}
    res["blocks"] = [{k: v for k, v in b.items() if k != "message"} for b in res.get("blocks", [])]
    return res


def post(url, body):
    req = urllib.request.Request(url + "/check", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8791")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "vectors"))
    ap.add_argument("--with-facts", action="store_true")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    try:
        with urllib.request.urlopen(url + "/health", timeout=5) as r:
            print("health:", r.read().decode())
    except Exception as e:
        print(f"cannot reach {url}/health: {e}"); return 2
    files = sorted(Path(a.dir).rglob("*.json"))
    passed = failed = skipped = 0
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        name = f.stem
        if name in XFAIL:
            print(f"skip {name}: {XFAIL[name]}"); skipped += 1; continue
        if doc.get("facts") and not a.with_facts:
            print(f"skip {name}: needs the facts fixture (covered by pytest)"); skipped += 1; continue
        body = dict(doc["request"])
        body["as_of_now"] = doc.get("as_of_now") or body["candidate"].get("timestamp")
        if doc.get("facts") and a.with_facts:
            body["facts"] = doc["facts"]
        status, got = post(url, body)
        if status == 200 and outcome(got) == outcome(doc["expected"]):
            print(f"pass {name}"); passed += 1
        else:
            failed += 1
            print(f"FAIL {name} (HTTP {status})\n  expected {json.dumps(outcome(doc['expected']))[:400]}\n  got      {json.dumps(outcome(got))[:400]}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
