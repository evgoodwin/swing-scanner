# MTG rules service (skeleton, for Ev's review)

The Python engine behind the platform's Trade Check. Implements **contract v2.1** and ruleset **mtg_core@1.2**
and listens on **127.0.0.1:8791** (8788 is Cairn's on the server). This folder is new and self-contained.
It does not import or change anything else in `C:\SwingScanner`.

Status: reviewed and run by Ev (2 Oct). Deploy steps for the server are in `DEPLOY.md`.

## Try it on your PC

Type one line at a time (plain `python`, your main Python, not the scanner's venv):
```
cd C:\SwingScanner\rules_service
python -m pip install -r requirements.txt
python -m pytest -q
python run_rules_service.py
```
The tests should end with "93 passed, 1 xfailed". The last command keeps running: open
http://127.0.0.1:8791/health in a browser, then stop it with Ctrl+C. Checked on Ev's PC 2 Oct 2026 (Python 3.14).

## Endpoints

| Call | What it does |
|---|---|
| `GET /health` | `{ok, ruleset_id, engine_version, calendar, facts_as_of, facts, test_facts}`. `ok` is false when the facts file is present but unusable. |
| `POST /check` | check-request → check-result. Optional `as_of_now` (ISO time with zone) fixes "today" for the timing-call staleness rule (v2.2 item 1). Without it, the real clock in New York time is used. |
| `GET /scan` | Returns the latest scan file (`MTG_SCAN_FILE`, default `data\scan_latest.json`) with only contract fields. 503 "no scan yet" until the scan job writes one. |

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MTG_RULES_PORT` | 8791 | Port |
| `MTG_FACTS_FILE` | not set | Market facts from the daily job (index close, 50-day SMA, 20 EMA, distribution days; per-symbol stage, 20 EMA). Not set → Wait severity is null and the stage check is skipped. Present but unreadable or malformed → `/check` answers 503 (fails closed). Older than the previous trading day → not used, and its date is reported as `engine_data_as_of`. |
| `MTG_RULES_TEST_FACTS` | off | `1` lets a request carry its own `facts` (the test fixture from the review). Allowed only when `MTG_ENV` is `dev`, `test` or `local`; otherwise the service refuses to start. Every use is logged. Without it, a request with `facts` gets a 400. |
| `MTG_ENV` | not set | `production` on the server; `test` on your PC when using fixtures. |
| `MTG_SCAN_FILE` | `data\scan_latest.json` | Where `/scan` reads from |

## What it checks

Every request is first validated against the contract's own JSON Schemas (copied into `rules_service/contracts/`
from the platform repo) plus a stop-side check. Bad input gets a 400 with a plain reason, never a size.

Same order as the ruleset's verdict precedence: A-14 stop pending, D-2 timing call current (NYSE calendar from
`exchange_calendars`), A-2d Wait Mode (longs only), A-12 stage (needs facts), A-23b position count, A-23 sector
cap, A-21 open-risk limit with `shares_within_limit`, then warnings (W-STOP-SIDE when facts have the 20 EMA,
P-SHORT). Sizing is A-16/A-17/A-18, smallest wins, with D-3 A-grade and Rick's size call. Decimal arithmetic,
size from the unrounded risk %, heat compared unrounded, prices never rounded.

Not yet: A-27 earnings in hold and A-24 exit plan (waiting on candidate inputs and a ruling), OVERSIZED (no
input), crypto (pending). A wrong-side numeric stop gets a 400; the platform already rejects those.

## Server

See `DEPLOY.md` (Rhomuel). The systemd unit and env template are in `deploy/`, and `tools/replay.py` replays the
vectors against the running service over HTTP.

## Tests

`tests/test_service.py` covers health, the real clock, the facts switch and its environment guard, bad inputs
(unknown regime states, negative or out-of-range numbers, text where true/false belongs, wrong-side stops),
bad or stale facts files, the stage check from the facts file, the sector cap at 50.004%, and `/scan` filtering.

`tests/test_vectors.py` sends every vector in `vectors/` through the HTTP API: corrected 001–012, golden
013–030, proposed P01–P11. Rule outcomes match on all of them except P10, which is marked expected-to-fail until the open-risk ruling.
Also checked by driving the running service with the platform's own result validator: 41 of 41 accepted.

The reference calculator (`tools/ref_engine.py`) and this engine share an author, so the platform's
`golden.test.js` remains the independent check on the arithmetic. A separate review ran 100,000 random requests
through both and found no difference on valid input; its input-handling findings are fixed and tested.

## Open items before the server

1. **Platform URL.** The platform's default `ENGINE_URL` is `http://127.0.0.1:8788`. Rhomuel needs to set
   `ENGINE_URL=http://127.0.0.1:8791`.
2. **No authentication.** The service binds to 127.0.0.1 only and the platform sends no key. Hakim to say
   whether a shared-key header is wanted.
3. **Facts file.** The daily job that writes `MTG_FACTS_FILE` isn't built. Until it is, Wait severity is null
   and stage isn't checked. The distribution-day definition must come from the course before it is.
4. **Block wording.** Vectors 001–012 (platform) and 013+ (ours) word the same blocks differently. Tests compare
   rule, tier, severity and order, not the text. Pick one wording (Deron/Duy).
5. **Scan adapter.** `scanner.run_scan` doesn't produce `setup_type`/`setup_status`/`rank` in contract form
   yet, so nothing writes `scan_latest.json`. Personal overlays never leave `/scan`: unknown fields are dropped.
6. **`as_of_now`** is accepted on every request and logged. It's the proposed v2.2 item 1, awaiting Deron.
7. **Missing `size_factor` is sized as full**, as vectors 001–012 expect. The ruleset says the platform shows
   "Size call not set" instead (v0.9.4), so the platform should never send a WD alert without it.
8. **`swing_risk` is not reused.** Its Phase 2 rules (traffic-light tiers, no stop-distance band, R/R and grade
   C blockers) aren't mtg_core@1.2.
