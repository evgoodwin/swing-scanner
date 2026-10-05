import json, os

os.environ["MTG_RULES_TEST_FACTS"] = "1"
os.environ["MTG_ENV"] = "test"
import pytest   # noqa: E402
from datetime import date   # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402
from rules_service import RULESET_ID   # noqa: E402
from rules_service import trading_calendar as cal   # noqa: E402
from rules_service import facts as facts_mod   # noqa: E402
from rules_service.app import app   # noqa: E402

client = TestClient(app)
REQ = {"candidate": {"symbol": "AAPL", "direction": "long", "entry": 182.5, "stop": 176.0, "source": "WD_ALERT",
                     "sector": "Technology", "timestamp": "2026-09-28T13:30:00Z"},
       "profile": {"account_size": 50000, "risk_pct": 1.0, "heat_limit_pct": 5, "max_positions": 4, "open_positions": []},
       "regime": {"state": "buy", "as_of": "2026-09-25"}, "as_of_now": "2026-09-28T13:30:00Z"}


def test_health():
    j = client.get("/health").json()
    assert j["ok"] and j["ruleset_id"] == RULESET_ID == "mtg_core@1.2"


def test_check_basic_fits():
    j = client.post("/check", json=REQ).json()
    assert j["verdict"] == "FITS" and j["shares"] == 76 and j["engine_version"]


def test_real_clock_makes_old_call_stale():
    body = {k: v for k, v in REQ.items() if k != "as_of_now"}
    assert client.post("/check", json=body).json()["verdict"] == "NO_TIMING_CALL"


def test_wrong_side_stop_is_400():
    body = json.loads(json.dumps(REQ)); body["candidate"]["stop"] = 190
    assert client.post("/check", json=body).status_code == 400


def test_bad_as_of_now_is_400():
    body = dict(REQ, as_of_now="yesterday")
    assert client.post("/check", json=body).status_code == 400


def test_facts_refused_without_test_switch(monkeypatch):
    monkeypatch.setenv("MTG_RULES_TEST_FACTS", "0")
    body = dict(REQ, facts={"as_of": "2026-09-25", "index": {"close": 1, "sma50": 2, "ema20": 2, "dist_days_5wk": 6}})
    r = client.post("/check", json=body)
    assert r.status_code == 400 and "test-only" in r.text


@pytest.mark.parametrize("env", ["production", " production", "PROD", "", "staging"])
def test_test_switch_refused_outside_test_envs(monkeypatch, env):
    monkeypatch.setenv("MTG_RULES_TEST_FACTS", "1"); monkeypatch.setenv("MTG_ENV", env)
    with pytest.raises(facts_mod.FactsError):
        facts_mod.test_facts_enabled()


def _mut(path, value):
    body = json.loads(json.dumps(REQ)); d = body
    for k in path[:-1]: d = d[k]
    d[path[-1]] = value
    return body


@pytest.mark.parametrize("path,value", [
    (("regime", "state"), "Wait"), (("regime", "state"), "sell"), (("regime", "as_of"), "2026-09-25T20:00:00Z"),
    (("profile", "risk_pct"), -1), (("profile", "risk_pct"), 2), (("candidate", "size_factor"), 0),
    (("candidate", "size_factor"), -1), (("profile", "heat_limit_pct"), 50), (("profile", "max_positions"), 99),
    (("profile", "declared_open_count"), 3.9), (("profile", "declared_heat_pct"), -50),
    (("candidate", "self_declared_a_grade"), "false"), (("candidate", "stop_pending"), "false"),
    (("candidate", "entry"), "182.5"), (("candidate", "stop"), -5), (("candidate",), None), (("regime",), "buy"),
    (("profile", "open_positions"), [{"symbol": "X", "direction": "long", "shares": -100000, "entry": 10, "stop": 9}]),
    (("profile", "risk_pct_a_grade"), 10),
])
def test_bad_inputs_are_400(path, value):
    r = client.post("/check", json=_mut(path, value))
    assert r.status_code == 400, (path, value, r.status_code, r.text)


@pytest.mark.parametrize("facts", [[1, 2], "x", {"symbols": {"AAPL": None}}, {"symbols": [1]}, {"index": [1]},
                                   {"symbols": {"AAPL": {"stage": 7}}}])
def test_bad_fixture_facts_are_400(facts):
    assert client.post("/check", json=dict(REQ, facts=facts)).status_code == 400


@pytest.mark.parametrize("content", ["[1,2]", '{"as_of": "2026-09-25", "index": [1]}', '{"as_of": "2026-09', "{}"])
def test_bad_facts_file_fails_closed(tmp_path, monkeypatch, content):
    f = tmp_path / "facts.json"; f.write_text(content)
    monkeypatch.setenv("MTG_FACTS_FILE", str(f))
    assert client.post("/check", json=REQ).status_code == 503
    h = client.get("/health").json()
    assert h["ok"] is False and h["facts"] != "ok"


def test_stale_facts_file_not_used(tmp_path, monkeypatch):
    f = tmp_path / "facts.json"
    f.write_text(json.dumps({"as_of": "2026-09-21", "index": {"close": 1, "ema20": 2, "sma50": 2, "dist_days_5wk": 6},
                             "symbols": {"AAPL": {"stage": 4}}}))
    monkeypatch.setenv("MTG_FACTS_FILE", str(f))
    j = client.post("/check", json=REQ).json()
    assert j["verdict"] == "FITS" and j["engine_data_as_of"] == "2026-09-21"


def test_stage_4_from_store_blocks(tmp_path, monkeypatch):
    f = tmp_path / "facts.json"
    f.write_text(json.dumps({"as_of": "2026-09-25", "symbols": {"AAPL": {"stage": 4}}}))
    monkeypatch.setenv("MTG_FACTS_FILE", str(f))
    assert client.post("/check", json=REQ).json()["verdict"] == "STAGE_INVALID"


def test_sector_cap_compared_unrounded():
    from rules_service.engine import check, parse_now
    # 50.004% of the account in Technology must block (rounds to 50.00 for display)
    req = json.loads(json.dumps(REQ))
    req["candidate"].update(entry=100.0, stop=99.0, size_factor=0.01)          # 5 shares, $500
    req["profile"]["open_positions"] = [{"symbol": "MSFT", "direction": "long", "shares": 1, "entry": 24502.0,
                                         "stop": 24501.99, "sector": "Technology"}]
    r = check(req, parse_now(REQ["as_of_now"]))
    assert r["verdict"] == "SECTOR_LIMIT" and "50%" in r["blocks"][0]["message"]


def test_wait_without_facts_has_null_severity():
    body = dict(REQ, regime={"state": "wait", "as_of": "2026-09-25"})
    j = client.post("/check", json=body).json()
    assert j["verdict"] == "WAIT_MODE" and j["regime"] == {"state": "wait", "severity": None}


def test_facts_store_file(tmp_path, monkeypatch):
    f = tmp_path / "facts.json"
    f.write_text(json.dumps({"as_of": "2026-09-25", "index": {"close": 17100, "ema20": 18050, "sma50": 17600, "dist_days_5wk": 6},
                             "symbols": {"AAPL": {"stage": 2, "ema20": 185.0}}}))
    monkeypatch.setenv("MTG_FACTS_FILE", str(f))
    body = json.loads(json.dumps(REQ)); body["regime"] = {"state": "wait", "as_of": "2026-09-25"}
    j = client.post("/check", json=body).json()
    assert j["regime"]["severity"] == "severe" and j["engine_data_as_of"] == "2026-09-25"
    assert "exit open positions" in j["blocks"][0]["message"]
    assert client.get("/health").json()["facts_as_of"] == "2026-09-25"


def test_w_stop_side_warns():
    body = json.loads(json.dumps(REQ)); body["candidate"]["stop_basis"] = "ema20"
    body["facts"] = {"as_of": "2026-09-25", "symbols": {"AAPL": {"stage": 2, "ema20": 185.0}}}
    j = client.post("/check", json=body).json()
    assert j["verdict"] == "FITS" and any(b["rule_id"] == "W-STOP-SIDE" and b["severity"] == "warn" for b in j["blocks"])


def test_calendar_matches_2026_list():
    d = date(2026, 1, 2)
    while d <= date(2026, 12, 31):
        exp = d - __import__("datetime").timedelta(days=1)
        while exp.weekday() >= 5 or exp in cal.NYSE_HOLIDAYS_2026:
            exp -= __import__("datetime").timedelta(days=1)
        assert cal.previous_trading_day(d) == exp, d
        d += __import__("datetime").timedelta(days=1)


def test_scan_missing_is_503(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SCAN_FILE", str(tmp_path / "none.json"))
    assert client.get("/scan").status_code == 503


def test_scan_strips_non_contract_fields(tmp_path, monkeypatch):
    f = tmp_path / "scan.json"
    f.write_text(json.dumps({"as_of": "2026-09-28T21:00:00Z", "universe_size": 3,
                             "candidates": [{"symbol": "AAPL", "direction": "long", "entry": 182.5, "stop": 176, "source": "SCANNER",
                                             "timestamp": "2026-09-28T21:00:00Z", "setup_type": "flat_base", "setup_status": "CONFIRMED",
                                             "rank": 1, "overlay_a": 170.2, "overlay_b": "x"}]}))
    monkeypatch.setenv("MTG_SCAN_FILE", str(f))
    j = client.get("/scan").json()
    assert j["ruleset_id"] == RULESET_ID and "overlay_a" not in j["candidates"][0] and "overlay_b" not in j["candidates"][0]


def test_scan_strips_nested_fields(tmp_path, monkeypatch):
    f = tmp_path / "scan.json"
    f.write_text(json.dumps({"as_of": "2026-09-28T21:00:00Z", "regime": {"state": "buy", "severity": None, "private_note": 1},
                             "candidates": [{"symbol": "AAPL", "direction": "long", "entry": 182.5, "stop": 176, "source": "SCANNER",
                                             "timestamp": "2026-09-28T21:00:00Z", "setup_type": "flat_base", "setup_status": "CONFIRMED",
                                             "rank": 1, "practice_flags": ["HIGH_TIGHT_FLAG", {"x": 1}], "sector": {"a": 1}}]}))
    monkeypatch.setenv("MTG_SCAN_FILE", str(f))
    j = client.get("/scan").json()
    assert j["regime"] == {"state": "buy", "severity": None}
    assert j["candidates"][0]["practice_flags"] == ["HIGH_TIGHT_FLAG"] and "sector" not in j["candidates"][0]


@pytest.mark.parametrize("content", ["[1]", '{"candidates": null}', '{"candidates": [1]}'])
def test_scan_bad_shape_is_503(tmp_path, monkeypatch, content):
    f = tmp_path / "scan.json"; f.write_text(content)
    monkeypatch.setenv("MTG_SCAN_FILE", str(f))
    assert client.get("/scan").status_code == 503
