# mtg_core@1.2 — change list from v1.1

**From:** MTG-Core-1 (`mtg_core_ruleset_v1_1.yaml`) · **To:** `mtg_core_ruleset_v1_2.yaml`
**Authority:** MTG-Core Rulebook v1.1, signed by Deron Wagner (26 Sep 2026, Section A and decisions) and Rick Pedicelli (24 Sep 2026, Section B); Deron's rulings of 29 Sep 2026.
**Prepared by:** Ev Goodwin · 1 Oct 2026

Every change below names its reason and source. "Signed" means the signer's amendment on the v1.1 sheet. "Ruled 29 Sep" means Deron's "Decision on call" in the Engine Findings document. "Convention" means how the engine applies a signed rule where the sheet is silent — **those are listed separately in section 8 for Deron to confirm.**

---

## 1. Market timing

| # | Change | v1.1 | v1.2 | Reason and source |
|---|---|---|---|---|
| 1.1 | Model | Green / Yellow / Red with transitions | **Binary: Buy Mode / Wait-Sell Mode** | D-2 signed. Source M4-L4-S2. |
| 1.2 | Leaving Buy Mode | 5+ distribution days in 4 wks, or 6+ in 3 wks | **5+ distribution days in 5 weeks** | A-2 signed (Buy Mode = 4 or fewer in 5 wks). Script M4-L4 verified. |
| 1.3 | Severity in Wait-Sell | Red only | **Light**: dominant index below its 20-day EMA → pause new entries. **Severe**: below its 50-day moving average with heavy distribution → exit | A-2b signed; M4-L4-S2 (script verified). |
| 1.4 | Heavy distribution | undefined | 5+ distribution days in 5 weeks (A-1 definition) | Ruled 29 Sep. |
| 1.5 | Dominant index | per-benchmark | **Nasdaq Composite every day** for v1.2 | Ruled 29 Sep. M4-L4 says "usually Nasdaq, sometimes S&P"; no switching rule yet. |
| 1.6 | Risk by state | Green 1% / Yellow 0.5% / Red 0.25% | **Buy 1%** (A-grade opt-in up to 1.5%); **Wait-Sell: no new long entries** | D-3 and A-15 signed. The 0.25% Red entry is gone (resolves the A-2d vs A-15 contradiction). |
| 1.7 | New entries in Wait-Sell | blocked (all) | **Longs blocked; shorts not blocked** | Ruled 29 Sep (A-2d is about new longs). Vectors 006, 010. |
| 1.8 | Follow-through day | ≥1.5% on higher volume, day 4–7; IBD 25% variant pending | **≥1.5% on volume higher than the prior day; valid from day 4, no upper bound; days 4–7 strongest** | C-2 signed (per Rick). See 7.2: the course script says otherwise. |
| 1.9 | No current timing call | not handled | **NO_TIMING_CALL** block (D-2); never logged as Wait Mode | Ruled 29 Sep, vector 011. |
| 1.10 | Staleness | not handled | A call is current if dated today or the previous NYSE trading day | Ruled 29 Sep. Now fed by Rick's daily recap (Roadmap v4.1); rule unchanged. |
| 1.11 | Benchmarks | SPY, QQQ, IWM, DIA; crypto BTC | **SPY, QQQ, IWM, MAGS; no DIA. Crypto BTC or ETH, whichever is leading** | D-9 signed. |
| 1.12 | Timing record | — | Every published call stored (date, state, published time, source) | C-5 signed. Backfill from the Wagner Daily archive in Phase 2. |
| 1.13 | Scaling allowed | Green only | **Buy Mode only** | A-20 restated for the binary model. |

## 2. Setups

| # | Change | v1.1 | v1.2 | Reason and source |
|---|---|---|---|---|
| 2.1 | Setup list | 6 types incl. Gap Entry | **5 Core setups**: Base Breakout (Flat Base, Cup & Handle, Double Bottom as base types), Bull Flag, Pullback in Uptrend, First Pullback, Shakeout | D-1 signed. |
| 2.2 | Gap Entry | a setup | **An entry rule** (A-10) | D-1 signed. |
| 2.3 | High Tight Flag | setup 7 in Pine, "rare; reduced size" | **Practice only**, Rick's definition: +100% off the last base lows in ≤8 weeks, 2–3 week pause, ≤20–25% pullback. Scanner label "Rare pattern" (signed: "rare, high profit potential"; changed in the UX test) | C-3 signed. Corpus check 30 Sep: no lesson script mentions it; the M3-L3-S5 master script is a Double Bottom segment. |
| 2.4 | Base minimum | ~3 weeks (from M1-L1-P) | **5 weeks for stocks (ideal 8–12), 4 for crypto; shorter = consolidation** | A-3 signed. Script M3-L3 verified. The 3-week figure came from a derived study guide, not a script. |
| 2.5 | Flat base | — | 5–10 weeks | Script M3-L3 (base type named in D-1). Status SCRIPT-SOURCED; Deron to confirm. |
| 2.6 | Cup & Handle depth | 20–30% | **20–35%, base ≥ 7 weeks** | A-4 signed; script M3-L3-S3 verified. |
| 2.7 | Stage | placeholder (MA stack) | **M2-L5 stage analysis (10-week / 40-week MAs); daily MA stack accepted as the engine proxy** | D-5 and A-12 signed. Module 2 scripts not in the share yet: citation marked "not yet verified". |
| 2.8 | 20 EMA entry condition | none | **Confirmed: no 20 EMA entry rule** | Ruled 29 Sep (M3-L4, M4-L1). The only 20 EMA condition is on the index. |
| 2.9 | A-grade rubric | pending | Still pending; A-grade is self-declared until sourced. Minimum R:R 2:1 stands, not blocking | A-13 signed (left open). |

## 3. Stops and size

| # | Change | v1.1 | v1.2 | Reason and source |
|---|---|---|---|---|
| 3.1 | Stop-cap bands | 2–4% → 30, 5–7% → 15, 8%+ → 8 (gaps) | **Under 5% → 30; 5% to under 8% → 15; 8% and over → 8** | D-4 signed. Script M4-L3 verified for the bands. Vectors 017, 018 test the boundaries. |
| 3.2 | A-grade risk | ceiling 1.5% in Green | **Opt-in personal setting up to 1.5%, Buy Mode only, self-declared** | D-3 signed. Not Core. |
| 3.3 | Rick's size call | — | **size_factor 1 / 0.5 / 0.25 multiplies the risk % before the formula** (after choosing the A-grade value, per the contract's risk_pct_used definition). No size call → the platform does not size it as full | Ruled 29 Sep (contract v2.1, vector 009); v0.9.4. Vectors 014, 015. |
| 3.4 | Stop pending | — | **STOP_PENDING**: sizes nothing, reads as "coming", cleared by Rick's stop alert | Ruled 29 Sep, vector 012. |
| 3.5 | Shorts | long only | **Full sizing and risk rules; no setup or stage citation; P-SHORT warning on every short.** Scanner stays long-only | Ruled 29 Sep. |
| 3.6 | Price precision | — | **Prices never rounded**; only dollar risk and percentages round to 2 decimals | Platform found small crypto prices rounded to $0 (v0.9.4). Vector 026. |
| 3.7 | Risk rounding | — | **Size from the unrounded risk %; report risk_pct_used rounded.** A-grade 1.5% × quarter 0.25 = 0.375%: 28 shares, not 29 | Rounding first oversizes by a share. Case P09; the platform's golden test rounds first and needs the same fix. |

## 4. Portfolio limits

| # | Change | v1.1 | v1.2 | Reason and source |
|---|---|---|---|---|
| 4.1 | Heat limit | 5% (10% toggle agreed 15 Sep) | **5% default; personal limit up to 7%, Buy Mode only, one-time warning; min(personal, 5) in Wait-Sell. No 10% option** | C-1 and A-21 signed. Vectors 013, P07. |
| 4.2 | Heat breach | reduce weakest | **Block (HEAT_LIMIT) and show the shares that fit**; course guidance (reduce the weakest by RS) shown as advice | Ruled 29 Sep, vectors 004, 008. |
| 4.3 | Heat at exactly the limit | — | Fits (the limit is a maximum) | Vector 019. |
| 4.4 | Heat bands | 3–4% optimal, 2% floor | Unchanged, **fixed at any personal limit**; guidance only | D-7 signed. |
| 4.5 | Sector limit | not in v1.1 YAML | **≤ 50% of the account in one sector (A-23)**; warns "not checked" when the sector or position list is missing | A-23 signed; script M5-L2 verified (50%). Vectors 022–024. Measurement basis is a convention (8.4). |
| 4.6 | Positions | default 4, capacity-based | **Default 4; warn above 8; hard cap 10**; block when the trader's own limit is exceeded | A-23b signed (per Rick). Vectors 020, 021. |
| 4.7 | Drawdown alarm | drops posture one level | **Coaching nudge only, never scored** | D-11 signed. |

## 5. Exits

| # | Change | v1.1 | v1.2 | Reason and source |
|---|---|---|---|---|
| 5.1 | Exits by state | Green / Yellow / Red postures | **Buy: standard. Wait-Sell light: tighter trails. Severe: exit** | A-2e signed. |
| 5.2 | Stop-raising steps | rule | **Guidance only** | D-8 signed. |
| 5.3 | Scale-out default | open | **Course templates stay Core; the student chooses and is scored on following their own choice. Rick's plan is the preselected Practice default** | D-6 and A-26 signed. |
| 5.4 | Personal exit overlay (Ev-Exit-1) | inside the MTG ruleset file | **Removed from the MTG ruleset**; lives in personal settings only | Tier rule: personal never mixes with Core or Practice. |

## 6. Practice (Section B, Rick) — new in v1.2

| ID | Rule | Source |
|---|---|---|
| B-1 | ADR% (20-day) between 3 and 8 | Rick, signed |
| B-2 | Stops below the swing low if close; else the 8 or 20 EMA when entering on the average; else the reversal-day low | Rick, signed |
| B-3 | Buffer below the swing low under $50 (as typed: "usually just 10 about 21 cents" — about $0.10–0.21, to confirm with Rick); above $50/$100 just below the whole number; 4–10 positions max | Rick, signed |
| P-GAPDOWN | Gap down through a stop: wait 30 minutes, then stop at the 30-minute low minus $0.20, "to give the stock a chance to reverse higher." Diverges from course gap handling. Needs intraday bars (deferred) | Rick 27 Sep; ruled 29 Sep |
| P-HTF | High Tight Flag (see 2.3) | Rick, C-3 |
| P-SCALE-RICK | One scale at +15–30%, trail the rest on the 8 EMA (preselected default) | Rick, A-26 / D-6 |
| P-PARTICIPATION | Wait: none. Buy, starting out: 2–4 longs. Going well: 4–8 | Rick 27 Sep; ruled 29 Sep |
| P-INDEX-EMA | Rick uses the 21 EMA for indices, 20 for stocks. Core timing stays on the 20-day EMA (M4-L4) | Ev, 30 Sep |
| P-UNOFFICIAL | Unofficial setups are not Trade Check alerts at launch | Ruled 29 Sep |
| P-SHORT | Warning on every short (see 3.5) | Ruled 29 Sep |

## 7. Where v1.2 departs from the recorded course (for Deron)

These are deliberate, signed decisions. They are listed because students who took the lessons were taught otherwise, so the lessons need the same change.

1. **The traffic light (M5-L2-S1, "Portfolio Traffic Light Strategy").** The lesson teaches four levels: Green (80–100% invested, 5–8 positions, heat ≤5%), Yellow (60–80%, 4–6 positions, heat ≤4%), Red light (40–60%, 2–4 positions, "picky selection"), Red severe (0–25%, 0–2). v1.2 is binary with no exposure percentages, and light Wait-Sell allows no new longs. The RYG cheat sheet is already on the rewrite list (D-10); this lesson needs the same rewrite.
2. **Follow-through day volume (M4-L4).** The lesson says day 4–7 "with 25% volume increases." v1.2 uses volume higher than the prior day, valid from day 4 (C-2).
3. **Gap-down handling (M4-L2-S4, "Gap Protection Mastery").** Rick's gap-down rule is recorded as Practice; Core gap handling is unchanged.

## 8. Engine conventions — please confirm

How the engine applies signed rules where the sheet is silent. Each is in the ruleset under `conventions:` or the rule's `measure:`.

1. **Verdict order** when several rules fire, most severe first: STOP_PENDING, NO_TIMING_CALL, WAIT_MODE, STAGE_INVALID, EARNINGS_IN_HOLD, POSITION_LIMIT, SECTOR_LIMIT, HEAT_LIMIT, EXIT_PLAN_INCOMPLETE, OVERSIZED. Every rule that fires is listed. (The trader-type tips key on the verdict, so the order decides which tip shows.)
2. **Stale call = no call**, including the heat limit: min(personal, 5) until a current call arrives.
3. **Light is the catch-all within Wait-Sell**: severe only when the index is below its 50-day with 5+ distribution days; otherwise light, including Rick's judgment Wait with the index above its 20 EMA (Wagner Daily, 30 Sep).
4. **Sector limit measured at entry prices against account size**, including this trade at its computed size.
5. **Position limit blocks** when the trader's own max_positions is exceeded; the "above 8" warning applies whatever the personal limit.
6. **Rounding**: decimal arithmetic; shares floored; money and percentages rounded half-up to 2 decimals for output only; prices never rounded; risk % unrounded when sizing (3.7); open risk compared with the limit unrounded.
7. **50-day moving average for severity**: SMA proposed. M4-L4 says "fifty-day moving average"; the RYG sheet says EMA.

## 9. Still pending (guidance until ruled)

| Item | What's needed | Rule |
|---|---|---|
| Earnings inside the hold | The planned hold or an agreed default window (not in the v2.1 candidate) | A-27 |
| Five exit steps before arming | A trailing-method field; proposed: enforce when a plan is armed or logged, warn in /check | A-24 |
| A-grade rubric | Source in M4-L4-S4 | A-13 |
| Crypto | Deron's answers (fractional quantity, timing gate, weekends) | crypto decision (UX test D3) |
| Dominant-index switching | When the S&P replaces the Nasdaq (M4-L4: "sometimes") | A-2b |
| Sector risk | Whether to add a sector open-risk check (I-124) | A-23 |

## 10. Not in this release

- **Before-and-after scanner counts** (Deron, 29 Sep): the 5-week base minimum needs base measurement, which arrives with pattern detection on 14 Oct. The counts come with that release.
- **Crypto test cases**: after the crypto decision.

## 11. Course-material record

D-10 (signed): the RYG cheat sheet and the Follow-through day PDF are Core course material; the RYG sheet is rewritten as binary Buy/Wait-Sell and both go into M4-L4 resources. Lesson M5-L2-S1 joins that list (7.1).
- **Smoke-test conversion** (19 cases to the contract format): 5 Oct, as posted.
