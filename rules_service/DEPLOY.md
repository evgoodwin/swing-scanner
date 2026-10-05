# Deploying the rules service (Rhomuel)

The engine behind Trade Check runs contract v2.1 and ruleset **mtg_core@1.2**. It listens on **127.0.0.1:8791**, on the same box as the platform, and runs on Python 3.12 (tested on 3.12.3 and 3.14).

Nginx and Caddy never route to it; only the platform calls it. It holds no secrets, and it logs no account sizes or positions.

The code is in Ev's repo `evgoodwin/swing-scanner`, in the `rules_service/` folder. Clone it with the server's deploy key (the read-only one added 30 Sep). The rest of that repo is Ev's scanner and isn't run here.

## 1. Service user, code, Python

```bash
sudo useradd --system --home /opt/mtg-engine --shell /usr/sbin/nologin mtgengine
sudo git clone git@github.com:evgoodwin/swing-scanner.git /opt/mtg-engine
sudo python3.12 -m venv /opt/mtg-engine/.venv
sudo /opt/mtg-engine/.venv/bin/pip install -r /opt/mtg-engine/rules_service/requirements.txt
sudo chown -R mtgengine:mtgengine /opt/mtg-engine
sudo mkdir -p /var/lib/mtg-engine && sudo chown mtgengine:mtgengine /var/lib/mtg-engine
```

## 2. Test before starting

```bash
cd /opt/mtg-engine/rules_service
sudo -u mtgengine env PYTHONDONTWRITEBYTECODE=1 /opt/mtg-engine/.venv/bin/python -m pytest -q -p no:cacheprovider
```

Expect **93 passed, 1 xfailed**. The tests turn on the market-facts test fixture inside the test run only. The running service never accepts that fixture in production.

## 3. Environment

```bash
sudo mkdir -p /etc/mtg-engine
sudo cp /opt/mtg-engine/rules_service/deploy/env.example /etc/mtg-engine/env
sudo chown root:mtgengine /etc/mtg-engine/env && sudo chmod 640 /etc/mtg-engine/env
```

No edits are needed today. Never set `MTG_RULES_TEST_FACTS` on this server: with `MTG_ENV=production` the service refuses to start if it's set.

## 4. Service

```bash
sudo cp /opt/mtg-engine/rules_service/deploy/mtg-rules.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mtg-rules
sudo journalctl -u mtg-rules -n 20            # expect: "Uvicorn running on http://127.0.0.1:8791"
curl -s http://127.0.0.1:8791/health
```

The health check should return `{"ok":true,"ruleset_id":"mtg_core@1.2",...,"calendar":"exchange_calendars ...","test_facts":false}`.

## 5. Replay the vectors against the running service

```bash
cd /opt/mtg-engine/rules_service && /opt/mtg-engine/.venv/bin/python tools/replay.py
```

Expect **34 passed, 0 failed, 7 skipped**. Six of the skipped vectors need the facts fixture and are already covered by step 2. The seventh, P10, is waiting on a ruling.

## 6. Point the platform at it

Check `ENGINE_URL` in `/etc/mtg-platform/env`. The v0.9.6 guide said to leave it at 8788, so it may still be set to that. It must be `http://127.0.0.1:8791`. Then run `sudo systemctl restart mtg-platform`.

Then run the platform's own replay: `ENGINE_URL=http://127.0.0.1:8791 npm run replay-golden`.
- **As the script stands:** 3/26 match. The script sends no `as_of_now`, so the engine checks every vector against today's date, and most come back NO_TIMING_CALL. That's review item 1, not an engine fault.
- **With the one-line change** in `deploy/replay-golden.as_of_now.diff`: **24/26 match**. The change sends the vector's `as_of_now`, or its candidate timestamp if there isn't one.
- **The two left, 004 and 008,** conflict with the 50% sector cap. Their corrected versions are in PR #13 (review item 3).

## Runbook

| Need | Command |
|---|---|
| Is it up | `curl -s http://127.0.0.1:8791/health` |
| Logs | `sudo journalctl -u mtg-rules -f` (one line per check: symbol, verdict, rules fired, ms) |
| Restart | `sudo systemctl restart mtg-rules` |
| Update | Pull the repo the way you deploy the platform, then `sudo /opt/mtg-engine/.venv/bin/pip install -r /opt/mtg-engine/rules_service/requirements.txt`, re-run step 2, `sudo systemctl restart mtg-rules`, then step 5 |
| Roll back | `git checkout <previous commit>` in /opt/mtg-engine, restart, then step 5 |

## Not live yet (by design)

- **`GET /scan`** answers 503 "no scan yet" until the scan job writes `/var/lib/mtg-engine/scan_latest.json`.
- **Wait-mode severity and the stage check** need the nightly market-facts file (`MTG_FACTS_FILE`). Until that job exists, severity is reported as null and stage isn't checked.
- **Earnings-in-hold (A-27) and the exit-plan check (A-24)** wait on Deron's rulings.
- **There's no shared key** between the platform and the engine; it's localhost only. Hakim to say whether he wants one.
