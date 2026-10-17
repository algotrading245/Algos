# Handoff: where the two-EA project stands

For a session that picks this work up without the earlier conversation (for example a cloud session). Last updated
2026-10-18.

## Goal

Two MT5 expert advisors, and the work does not stop until both exist:

1. **5x EA**: turn $100 into $500 in a month with the highest probability. This is `mql5/Experts/AurumHydra/`.
2. **Funded-account EA**: pass a prop-firm challenge and keep the funded account with the highest probability. This is
   `mql5/Experts/AurumFunded/`.

The owner gave a free hand: any source (SSRN, Google Scholar, anything else), any prebuilt strategy or own idea, and
the choice of prop firm and challenge is ours. What stays with the owner: buying a challenge, attaching EAs in MT5,
running the Strategy Tester and demo, and a yes before each live or real-money step.

Rules of the work:

- Nothing goes into an EA unless it survives realistic costs in both halves of the data (to 2017, and 2018 on;
  `SPLIT` in the tools).
- When a paper is used, read the full paper first (definitions, tables), not the abstract, and say in reports which
  papers were read in full.
- Order: Python backtest, then MT5 Strategy Tester, then demo, then live.
- Leave the rollover (server 23:00-01:00, the New York close) out of intraday tests or check it separately: histdata's
  bid quotes spike and snap back there, which looks like a strong reversal that cannot be traded (found 2026-10-15 in
  the AUD/NZD relative-move test). The current legs and both candidates already avoid those hours.
- Commit and push to the session's working branch after each finished piece of work (earlier sessions:
  `claude/exciting-hopper-r6sdmc`; the cloud session of 2026-10-14: `claude/intelligent-turing-j0nrmf`).

## Restructure of 2026-10-18 (owner's six steps)

1. **One leg library.** The legs, sizing and handlers of both EAs are in `mql5/Include/Aurum/` (`Inputs.mqh`,
   `Legs.mqh`). `AurumHydra.mq5` and `AurumFunded.mq5` are thin wrappers that `#define AURUM_*` defaults before the
   include (the include's `#ifndef` gives the rest). Breakout and noise legs are on by default: Hydra 0.125 / 0.275,
   Funded half that (0.0625 / 0.1375). All other EAs moved to `mql5/Experts/_archive/` (see its README).
   `tools/run-tester.ps1` reads the wrapper with its Aurum includes inlined and resolves the macros, so the source
   defaults it writes into tester.ini are the ones the EA compiles with.
2. **InpTarget** (3, 4 or 5) in AurumHydra: aim at that multiple with the goal scale that gave it the best odds
   (`tools/target_odds.py`: P(3x/4x/5x) and P(ruin) per scale; 2.5 is within a point of the best for all three).
   Presets `AurumHydra_target3x/4x/5x_FTMO.set`. `tools/months_summary.py` reports the share of months at 3x/4x/5x.
3. **Holdout.** `tools/holdout.py`: 2025-10-13 on (tester months after 2025.09) is the owner's. Agent runs
   (`AURUM_AGENT=1`, set by `run-agent.ps1`) are refused by run-tester/run-months on those dates; `tools/holdout_check.py`
   is the owner's one-time check and refuses agents. Honest note: j8b, j8c and j9 already ran 2025.10-2026.09 months
   before the holdout existed, so the agents have seen it. The clean out-of-sample test is the demo from 2026-10-19 on.
   **Model router** in `run-agent.ps1`: haiku for routine roles (monitor, researcher, scanner, tester), sonnet for code
   (fidelity, quant-coder), opus for judgment (orchestrator, reviewer). Same Claude Code login for all.
4. **Live page controls.** `python tools/live_server.py` (127.0.0.1:8765) now has buttons: pause/resume the relay
   (`logs/autopilot/PAUSE`), release Terminal 16, start an agent role now, and a form that appends a job to
   `queue.json` (holdout dates refused). POSTs need the local host, a local Origin and header `X-Aurum: 1`.
   The claude.ai dashboard is a read-only cloud page (it cannot reach this PC).
5. **Tester terminal** separate from the demo terminal: see "Terminals" below once installed.
6. **Improvement loop** on both EAs through the relay, on months up to 2025.09.

## Demo and autopilot (2026-10-17)

- **FTMO demo running:** AurumFunded 1.03 (repo version, candidate legs off) is attached in Terminal 16 to an XAUUSD
  M15 chart with the `AurumFunded_FTMO_phase1.set` preset (phase 1: 10% target, day stop 3%, final stop at 91.5% of
  the start balance), Algo Trading on. The EA logged "phase 1 started" on 2026-10-17; the first trades come when gold
  opens on Monday. The monitor agent reports them in `docs/demo_log.md`.
- **Terminal 16's `MQL5\Experts\AurumFunded` is a junction to the repo** (made with `tools/link-terminal.ps1`). Any
  recompile of AurumFunded changes the demo's binary and MT5 reloads the EA, which keeps its phase state in terminal
  global variables. The terminal's old AurumFunded folder and its three FTMO presets are backed up in the terminal's
  data folder under `backup\2026-10-17_before_repo_link`.
- **Tester queue** (`docs/autopilot/queue.json`, run by the tester agent this weekend): j1 AurumNoise US500, j2
  AurumNoise US100, j3 AurumFunded legs off/on (approval a1 given 2026-10-17), j4 AurumHydra legs off/on - all
  done; j5 AurumHydra size 1 legs off/on done but not a valid pair; j6 (replaces j5) done and judged; j7 failed;
  j8a-c (5x months) done and judged; j9 (gold spread-cap check) done and judged 2026-10-18; no job queued.
- **AurumNoise passed step 15 (orchestrator, 2026-10-17 05:25).** US500.cash (j1): -0.68%, 26.1% equity drawdown,
  452 trades, against +1.3% / 28.6% / 451 expected - flat as the Python model said; the profit was all 2024
  (+1,689), 2025 and 2026 lost. US100.cash (j2): +39.9%, 16.4%, 697 trades, against +44.7% / 18.5% / 701; every year
  positive. Both inside the release rule (return within 15 points, drawdown not above), so **j4 was released**
  (queued after j3). Noise is now at step 16, like the breakout: the j3 and j4 legs-on runs decide. Watch in them
  whether the S&P half helps at all in 2024-26; if not, that is a reason to look again, not to drop it from a
  32-month stretch (its Python halves are 0.61 / 1.08, and refitting weights on the tester window is ruled out).
- **j3 base run judged (orchestrator, 2026-10-17 05:55): matches.** AurumFunded 1.03, legs off, funded preset,
  2024-01 on: +167.7%, 6.67% equity drawdown, 17 day stops, against the queue's "+110%, 4.1%, no day stop". That
  expectation came from the 2026-10-15 run of **1.00**, whose cushion sizing was capped at 1.0; 1.01 caps it at 1.4,
  so after +3.5% every leg trades 1.4 times its size. On that sizing the Python model gives +331% / 7.2%
  (`research/funded_tester_gap.py`); the tester keeps 67% of its log growth (the 1.00 run kept 70%) and the drawdown is
  inside the model's 6.2-7.2%. The day stop is 3% of the *initial* balance, so as the account compounds it shrinks
  as a share of equity (1.1% at 2.7x), which is why it fires in 2025-26. On a real funded account payouts keep equity
  near the start, so the tester's 17 hits overstate it; the worst day (-2.70%) stays well inside FTMO's 5%. **Legs-on
  run, judged against the same sizing:** model +381% / 8.4%, so expect about +185-190% and 7.5-8% drawdown, with more
  day stops. Clearly below the base's +168% would count against the legs.
- **j3 legs-on run judged (orchestrator, 2026-10-17 07:10): both legs pass step 16 in AurumFunded.** +221.5%, 8.28%
  equity drawdown, 21 day stops, against the expected +185-190% / 7.5-8% (it kept 74% of the model's log growth, the
  base 67%). Return per drawdown 25.1 -> 26.7, worst day -2.70% -> -2.55%, 28 of 34 months positive (base 24). The
  2024 day stops are the same two days in both runs; the 4 extra come in late 2025-2026, when equity is 2.5x+ and the
  3%-of-initial stop is ~1.2% of equity (see above), so they do not count against the legs. USDJPY +3,179 -> +4,671;
  noise US100.cash +977, US500.cash -57 (the S&P half flat again on 2024-26 data).
- **a3 approved and applied (2026-10-17): step 17, both legs on in the FTMO demo.** Preset
  `AurumFunded_FTMO_phase1_legs.set` (phase1 plus `InpBreakRiskPct=0.125`, `InpNoiseMult=0.275`). The EA had been off
  every Terminal 16 chart since 04:57 (the tester hold's close dropped it, so no demo entries since); the keeper now
  starts Terminal 16 with `tools/autopilot/t16_attach.ini` whenever no saved chart has AurumFunded. Takes effect at the
  next start after the hold: check the journal for "16 inputs read from ... phase1_legs.set" and `tools/demo_check.py`.
- **Corr gate (`tools/gates.py`) now fails only positive correlation** (book <= +0.20, each leg <= +0.30); a negative
  one is a hedge and passes.
- **j4 (AurumHydra 5x) was a set-up fault, not an EA result.** Its `set` renamed only 4 of Hydra's 16 symbol inputs;
  `InpStocks` (SP500.r), `InpNasdaq` (NAS100.r), the four fix pairs and six yen crosses kept the other broker's
  `.pc` / `.r` names, so the fix, stock-fall, Tokyo morning, after-holiday and noise legs never traded (only EURUSD,
  USDJPY, AUDCAD did); the gold legs found the 100 deposit too small for the minimum lot; and the 5x preset stops
  after one goal round (January 2024). Off +9.5% / 15.0%, on +14.8% / 25.8% says nothing about the legs.
  **j5 replaces it** (queued): Hydra at size 1, no goal mode, from 10,000 at 1:500, new preset
  `mql5/Experts/AurumHydra/AurumHydra_FTMO_size1.set` with FTMO names for all 16 symbols. Expectation
  (`research/hydra_tester_expect.py`): model legs off +1184% / 10.7%, on +1574% / 11.5%; about +500% / +620% at the
  j3 runs' 70% of log growth, tester drawdown likely 15-25% (gold up to 6.2x equity, intraday dips). Step 16 test:
  return per drawdown higher with legs on. Later, for the 5x question itself: the 5x preset also needs these 16
  names, and one round at 100 tells little - a run of separate monthly rounds would.
- **j5 (orchestrator, 2026-10-17 10:05): no valid off/on pair, replaced by j6.** Both runs came out identical to the
  cent: +1460.44%, 13.11% equity drawdown, 4,174 trades, PF 1.53, return per drawdown 111, worst day -5.94%
  (2026-06-30), 29 of 34 months positive, all 14 symbols traded (XAUUSD +41.9k, USDJPY +37.0k, US500.cash -1.0k the
  only loser). Cause: **the Strategy Tester keeps the previous run's value of every input the preset leaves out.**
  The off run's report lists j4's legs-on values that the size1 preset did not write: `InpBreakRiskPct=0.5`,
  `InpNoiseMult=0.275`, `InpMonthEndBoost=2.0`, `InpMaxDrawdownPct=0.0` and the 5x goal inputs (inert at
  `InpGoalMult=0`). So both runs were legs on *plus* the month-end boost and no 35% halt; that is ~97% of the
  legs-on model's log growth, flattered by the boost. j3's report inputs were checked the same way and are clean.
  Fix: `AurumHydra_FTMO_size1.set` now writes those inputs at the EA defaults (legs 0, boost 1.0, halt 35, goal
  defaults); `-Set` still overrides them for the on run. **j6** (tag `size1b`) reruns the pair; expect the legs-on
  run near or a little under j5's figure and the legs-off run clearly lower, and check the input list in both
  reports before judging.
- **j6 judged (orchestrator, 2026-10-17 13:10): both legs pass step 16 in AurumHydra.** Inputs verified in both
  reports (off 0 / 0 / boost 1.0 / halt 35, on 0.5 / 0.275 / 1.0 / 35). Legs off +725.1%, 12.48% equity drawdown,
  PF 1.70, 2,262 trades; legs on +1076.2%, 15.54%, PF 1.49, 4,173 trades. Return per drawdown 58.1 -> 69.2 (+19%;
  model 110 -> 136, +24%). At size 1 the tester kept more of the model's log growth than the Funded runs did (off
  83%, on 87%, against 67-74%). `research/hydra_j6_compare.py` (daily curves and the deals by symbol) shows the
  deepest stretch moves: legs off it is 2024-07/08 (July -6.0% off, +1.8% on: USDJPY breakout +4.1, US100 +1.7,
  US500 +1.8 points); legs on it is 2026-01 (-8.3% off, -13.0% on: noise -3.9, breakout -1.0, next to AUDCAD -4.5
  and EURUSD -2.2 in both). Noise's own share (no index trades with legs off): US100.cash +4,181, US500.cash -1,092,
  the S&P half negative a third time on the same 2024-26 window Python already had flat; not new evidence, weights
  not refitted. **Month-end boost:** j5 against j6-on is in effect a clean boost pair (the halt never fired):
  boost 2.0 gave +1460% / 13.11%, return per drawdown 111 against 69. The fix legs trade only on that day, so the
  boost doubles their whole size: a re-weighting (a rejected family; a quarter-end x2 gave 3.37 -> 3.31 after 2017)
  measured on the tester window, so not adopted for size 1; it stays in the 5x preset as tested.
- **Next for the pipeline:** step 17 for both candidates is under way in the demo (a3 approved). The 5x question
  itself was run as the month series j8a-c (below); queue jobs now carry `months` {from, to} for that.
- **j8a-c judged (orchestrator, 2026-10-17 23:55): 5x reached in 1 of 21 months, against the preset header's 9 of
  21.** Same goal inputs as `AurumHydra_5x_month.set` (23 days, scale 2.5, boost 2.0), FTMO's 16 names, a fresh
  10,000 at 1:500 each month, EA 1.33 (the 9/21 was 1.31 on the `.pc` broker). Only 2026.01 reached 5x (gold
  +40.5k); median about 1x, 2 of 21 months below 0.5x. Not released, settings not changed to fit. **Cause, from
  `research/hydra_5x_months_check.py` and the tester log:** the round needs the gold hold (sized ~47 at the round's
  start), and gold made no trade in 7 of 21 months.
  - 2026.05-09: the hold's trend signal (20/60/120/250-day closes) was 0 on 62-100% of days - the strategy itself,
    gold fell from its high.
  - 2026.02 and 2026.04: the signal was positive (0.93, 0.45) but no buy went through, and 2026.03 opened only on
    03.09. The j6 size-1 run shows the same: from 2026.02.03 to 03.09 only reductions (which skip the spread check).
    Most likely cause: `InpGoldMaxSpread = 0.30` is in price units, set when gold was ~2,000; at ~5,000 gold and
    40-45% volatility FTMO's XAUUSD spread is above 0.30 for days, and Hold() then returns before buying (it also
    gates the dip and bell legs). Margin is ruled out (~0.2 lots on 10,000 at 1:500).
  - 2025 had gold every month and still 0/12 at 5x: the 2025 hold paid in 01/03/09 and lost 3.4-5.8k in each of
    04-07, and 2026 gold volatility (22-48%) cuts the hold through min(3, 10.7% / vol). So the spread cap does not
    explain the whole gap; the FTMO-data result stands as the tester's answer for EA 1.33.
  - Worst single day: 2026.04.17 -22.8%, the AUDCAD grid (-1,832 that month).
  - **j9 queued** (2026.02-04, `InpGoldMaxSpread=1.0`, tag `5xS`): a cause check only, not a 5x result.
  - There is no `docs/candidates.md` entry for the 5x preset (it is the EA's own goal mode, not a candidate leg), so
    nothing was updated there.
- **j9 judged (orchestrator, 2026-10-18 00:05): the cap was the cause, but lifting it makes the 5x months worse.**
  2026.02-04 with `InpGoldMaxSpread=1.0`: gold traded in all three months (cause confirmed) and lost -6,490 / -5,492
  / -3,304; multiples 0.34x / 0.49x / 0.57x against 1.33x / 0.91x / 0.72x with the cap at 0.30 (j8b/j8c). The
  hold bought at the round's start and took the 2026 gold drops at full goal size (worst days 02-02 -66.3%, 03-03
  -54.4%, 04-29 -43.1%). On those days a wide spread goes with fast gold, so the fixed 0.30 cap has worked as an
  unplanned volatility filter. **The j8 answer, 1 of 21 months at 5x for EA 1.33 on FTMO data, stands; the cap stays
  unchanged** (choosing a cap from three tester months would be fitting the tester window, and the only evidence so
  far favours the current value). The remaining gap to the preset header's 9/21 (EA 1.31 on a `.pc` broker at 3 cents
  a lot) cannot be rerun on Terminal 16. For the 5x goal the tester evidence now says the goal mode's gold hold is
  too large for 2025-26 gold (22-48% volatility). A smaller goal size, or a hold that does not enter at the round's
  start in high volatility, would be a new idea: it goes through the gates on the Python model from 2010, not a
  setting picked on j8/j9.
- **Demo note (revised 2026-10-18): AurumFunded has the same `InpGoldMaxSpread = 0.30`** (`AurumFunded.mq5:246`).
  The tester runs on FTMO's ticks with the same cap, so j3's figures already include the days it blocks, and demo and
  tester should agree. No EA change is proposed any more (j9 above). The monitor/fidelity agent should still check
  that gold entries in the demo come on the same days as in a tester run over those days; a demo that never buys gold
  while the tester does would be a fidelity finding.
- **Proposed tool change (`tools/months_summary.py`):** its "round" field and refusal count read the tester's
  `summary.txt`, which is one log for the whole day and every run, so both are polluted by the other months. Cut
  each month's lines by the run's start and end time (as done by hand for j8), and count the EA's silent
  InpMarginPct clip too, which is not a refusal in the log. Also: the AUDCAD grid retries every second while the
  market is closed (log spam, a small later EA fix).
- **Proposed tool change (agents may not edit `tools/`):** `tools/run-tester.ps1` should write *every* input of the
  EA into `[TesterInputs]` - parse the `input` lines of the `.mq5` for their defaults, then apply the preset, then
  `-Set` - so no run can inherit a value from the terminal's last run of the same EA. Until then every preset used
  in the queue must list each input that any other preset or `compare_set` changes.
- `backtests/2026-10-17_0056_AurumBreakout_USDJPY/` holds only a `tester.ini` (an aborted start before the 01:18
  run); left untracked.
- **Autopilot = agent relay** (`tools/autopilot/relay.ps1`, task "Aurum Relay" every 5 min; it replaced the
  fixed-time Orchestrator, Tester and Researcher tasks). Each agent ends with `HANDOFF: <role> <reason>`;
  `run-agent.ps1` writes it to `logs/autopilot/relay.json` and the relay starts that agent 15 min later
  (`$GapMinutes` in `common.ps1`). Order per tick: PAUSE / busy / usage-limit back-off (60 min) -> tester work in the
  weekend window -> due hand-over -> after 2 h idle the researcher (if none for a day) or the orchestrator. No daily caps (removed
  by the owner 2026-10-17 21:51); one agent at a time. Keeper (every 15 min) and Monitor (Mon-Fri 23:15) stay fixed tasks.

## Current state (updated 2026-10-17 13:40; the rest of this section is from 2026-10-15)

- **EAs in the repo:** AurumFunded 1.03, AurumHydra 1.33, standalone AurumBreakout 1.01 and AurumNoise 1.01. All four
  were compiled by `tools/run-tester.ps1` on Terminal 16 for the 2026-10-17 Strategy Tester runs (j1-j6), so they
  compile without errors; the warning count was not recorded in any summary. Recompile with
  `tools/autopilot/compile.ps1` and record 0/0 before the next EA change is merged.
- **Candidate legs, still off by default in both main EAs; both passed steps 15 and 16 on 2026-10-17** (see "Demo and
  autopilot" above): USD/JPY London breakout (Sharpe ~1.2 / 0.8 at the real 1.2 bp, a yen effect seen in every yen
  market) and noise-area momentum on the S&P 500 and Nasdaq (~0.7 / 0.9 at their spreads). Together: AurumFunded 3.24
  -> ~3.5 from 2018, Hydra 3.37 -> ~3.6-3.7 (5x-month chance ~55% -> ~59%). Step 17 (demo with the legs on) waits on
  the owner (a3).
- **5x tester series (2026-10-17 15:45): queued and started as j7.** `tools/run-months.ps1` runs one fresh-deposit
  tester run per calendar month (2025-01 to 2026-09, leverage 500, deposit 10000), each with its own `to` date, so
  rounds no longer replay to today; `tools/months_summary.py` gives the share of months at 5x. Its per-month refusal
  count reads the day-wide tester log, so it is not reliable yet (see the proposed months_summary change above).
- **j7 failed; replaced by j8a-c (orchestrator, 2026-10-17 16:20).** Three faults: the array splat (fixed), the tag
  chain in `tools/run-months.ps1` line 88 (`$tag` is `$Tag` in PowerShell, so tags grow `5x_202501_202502_...` and
  paths overflow from the 12th month; since fixed as `$monthTag`), and the job itself: `AurumHydra_5x_month.set` leaves the
  symbols at the source's `.pc` / `.r` defaults, so every month stopped at OnInit ("symbol XAUUSD.pc is not
  available") and the 11 "done" months are empty reports. New preset `AurumHydra_5x_month_FTMO.set` (the 5x goal
  inputs, FTMO's 16 names). j8a/b/c run 2025.01-07, 2025.08-2026.02, 2026.03-09 with tags `5xA/B/C`, short enough for
  the chained tags (52 characters at most; j7 broke at 86). Judged 2026-10-17 23:55: 1/21 (see "Demo and autopilot"). The untracked
  `backtests/2026-10-17_15*_AurumHydra_5x_*` folders of j7 hold nothing usable and can be deleted.
- **Tester inputs:** `tools/run-tester.ps1` writes the EA source defaults before the preset and `set`, so a run no
  longer inherits inputs from an earlier one (the j4/j5 lesson).
- **Demo vs tester fills:** `tools/fill_check.py` pairs each demo entry with the tester's entry for the same day, leg,
  symbol and side (missing/extra entries, fill gap in bp, lot ratio). No demo entries yet on 2026-10-17; the fidelity
  agent queues a tester run over the demo days once there are some.
- **Scans:** `tools/edge_scan.py` families slot, own, cal (weekday, turn of month) and vol (high/low 20-day vol
  regime) have all been run on the histdata symbols. The cal/vol run (21,240 trials, all in `docs/trials.jsonl`) left
  one survivor, `scan_cal_wed_EURUSD_s25_L2_short`, which failed halves (1.03 / 0.41), DSR (0.125) and goal (3.37 ->
  3.33). Simple rule scans on these instruments are exhausted; do not rerun them. New edges need a reason (a flow, a
  paper) or new data, and the scanner agent only runs on a family or data not scanned yet.
- **Ideas:** the researcher's first batch is `docs/ideas/2026-10-17.md` (4 ideas, abstracts only). Next runs lead
  with non-paper sources (open code, write-ups, market structure). Idea 2, Osler's round-number stop cascades (NY
  Fed SR125 / SR150), was read in full and tested on 2026-10-18 (`research/osler_round.py`, USDJPY + EURUSD M1
  2009-26, 512 variants against 300 arbitrary-level grids): **rejected at steps 5-7**. No variant reaches net Sharpe 0.5
  in both halves. The median gross per trade is negative, and round levels do no better than arbitrary ones
  (median -0.14 / -0.09 bp). Touch reversals are 1-3 pp lower at round levels, the opposite of the paper. The new
  rejected family is "Round-number levels". Ideas 1, 3 and 4 in that file are still abstract-only (Krohn-Vala auctions,
  S&P expiry pinning, expiry-week drift). The next idea needs a full read or a new researcher batch before any code.
  Process note: the quant-coder subagent has no Bash in the relay ("don't ask" mode), so it writes the script unrun and
  the orchestrator runs it with `python research/<name>.py`. Commit 031f5b6 (pushed) also carried 18 renames that
  were already staged before the run: the old EAs (Bell, Burst, Lattice, Legion, Meridian, Orient, Quartet, Snap,
  Tokyo, .mq5 and .ex5) moved to `mql5/Experts/_archive/`. They are 100% renames of tracked files, but the .ex5 rule
  was broken. Owner: keep them or revert. Agents: run `git diff --cached --name-only` before committing (proposed
  check for the finish procedure).
- **Agents (relay roles and models):** orchestrator (Opus, judges and plans), reviewer (Opus, on request), researcher
  (Haiku, daily), scanner (Haiku, on hand-over), fidelity (Sonnet, weekly or on hand-over), tester operator (Sonnet,
  weekend window), monitor (Haiku, daily demo check). Opus stays on judgement only.
- **Prop routes** (simulated median to the first payout at 70% of the edge): FundedNext Stellar Instant 1.4 months (4.3
  if it has a 40% consistency rule), Instant Funding PRO 2.5 months (preset with the Smart Drawdown lock and a
  floating-loss stop; 2.0 months with the DP fast sizing `FAST_IF`, none lost even at half the edge), FTMO 1-Step 7.8
  months, FTMO 2-Step 9.6 months. Presets for all four in `mql5/Experts/AurumFunded/`.
- **Waiting on the owner:** Strategy Tester runs (README "Tests to run next"); FundedNext: consistency rule on Stellar
  Instant?; Instant Funding: PRO's Account Drawdown %, EA policy, server clock; FTMO: the 1-Step's maximum loss (10% or 6%).
- **Research this session** (all in `research/` and the rejected list below): volatility-managed sizing, DQN, Deep
  Momentum Network, exponentiated-gradient weights, gold Forecast-to-Fill (look-ahead), ORB, night scalper, grids on
  15 pairs, cross-session metals, shocks, pairs, holiday transfers, SGE, oil-CAD, Bitcoin weekends - rejected; the
  London breakout and the tick/spread checks of both candidates - kept.

## EA 2: AurumFunded (written as v1.00; now 1.03, run in the Strategy Tester 2026-10-15 and 2026-10-17, see above)

Firm chosen: **FTMO 2-Step Challenge, Swing account**. Targets 10% then 5%, daily loss 5% of the initial balance
measured from the balance at midnight CE(S)T on equity, maximum loss 10% static, no time limit, at least 4 trading
days a phase, EAs allowed, Swing has no news or weekend restriction, leverage 1:30. Backup: **The5ers High Stakes**
(10% / 5%, 5% daily, 10% maximum, 3 profitable days a phase, 1:100, no orders within 2 minutes of high-impact news).
Rules were read on the firms' own pages on 2026-10-14; check them again before a challenge is bought.

The EA is AurumHydra v1.32 without its grid and gold hold, at half size (`InpSizeMult 0.5`), plus a guard
(`PropGuard` in the source): day stop at 3%, final stop at 8.5%, sizes shrink once equity is within 6.5% of the
final stop, stop at the target once the minimum trading days are done, a broker-side stop on each gold unit, and no
trading on days the server clock is not New York + 7 hours. State is kept in terminal global variables, so a restart
does not lose the day's starting balance. Presets for phase 1, phase 2 and the funded account are next to the source.

Simulated on daily leg results 2010-2026 (`python tools/backtest_prop.py`, legs in
`marketdata/hydra_legs_daily.csv.gz`). Daily data cannot see a day that dips below a limit and recovers, so these are
upper bounds:

| Edge assumed | Size | Shrink rule | Pass | Median days | Funded alive after 12 months | Paid in 12 months |
|---|---|---|---|---|---|---|
| as backtested | 0.5 | on | 100% | 124 | 100% | 33% |
| as backtested | 1.0 | on | 100% | 68 | 100% | 64% |
| half | 0.5 | off | 94% | 223 | 93% | 19% |
| half | 0.5 | on | 100% | 238 | 100% | 18% |
| a third | 0.5 | on | 92% | 287 | 100% | 13% |
| a third | 1.0 | on | 66% | 105 | 59% | 20% |

The pass column above counts only challenges that ended; challenges still open at the 500-day limit are left out,
which flatters the small sizes. `python tools/prop_stress.py` counts open ones as not passed and adds a pessimistic
intraday stand-in (any day closing below -1.5% booked as a hit of the 3% day stop). At size 0.5, passed / failed
within 250 trading days: 96/0 at the backtested edge, 55/0 at half the edge, 46/0.2 at half with the stand-in, 37/0.4
at a third; within 500 days 100/0, 89/0, 82/4, 66/10. Size 1.0 within 250 days: 99/0, 74/15, 58/27, 52/31. FTMO has
no time limit, so size 0.5 stays the default: it keeps failures near zero, and larger sizes are faster only when
the edge holds. FTMO's 2-Step rules (10% / 5%, 5% daily on closed and open results, 10% static, 4 days, no time
limit) were checked again through third-party pages and FTMO's own 2-Step page on 2026-10-14.

**Strategy Tester, phase 1 (2026-10-15, owner's FTMO demo):** passed on 2024-10-25, 10 months after a 2024-01-01
start, equity drawdown at most 4.7%, worst day -1.6%, no day stop. All legs but the quartet's bell, Tokyo and midday
match the Python model; those three earned +2.0% against about 7% in the model. Details in
`backtests/2026-10-15_funded_phase1/summary.md`.
Phase 2 preset from the same 2024-01-01 start: passed (+5%) on 2024-02-20, drawdown 1.9%
(`backtests/2026-10-15_funded_phase2/summary.md`).
Funded-account preset, 2024-01-01 to 2026-10-14: +110% in 34 months, equity drawdown at most 4.1%, worst day -1.6%,
worst month -2.1%, mean month +2.25%, 23 of 34 months positive; about 70% of the Python model's log growth
(`backtests/2026-10-15_funded_account/summary.md`).

**v1.01 (2026-10-15): cushion sizing.** Size x (equity - final stop) / 8.5%, between 0.3 and 1.4: 1 at the start,
smaller toward the final stop, up to 1.4 with profit. On the path to the first payout (`tools/prop_sizing.py`, 70%
of the edge) the first payout comes within 9 months 46% of the time (old rule 37%), median 9.6 months (10.6), and
with half the edge and pessimistic intraday dips no path fails (7.8%). Not yet re-run in the Strategy Tester.
Firms (`tools/prop_firms.py`): an 8%/5% two-step (FundedNext Stellar, FundingPips) brings the first payout about a
month sooner than FTMO's 10%/5% (median 8.8-9.0 months against 9.8 at 70% of the edge); FTMO kept for its record.

**Fastest first payout: an instant account** (`tools/prop_instant.py`). FundedNext Stellar Instant (no challenge,
no daily limit, 6% trailing maximum loss, payout on the 14-day cycle, 70-80% share, $49.99 for 2K to $599.99 for 20K,
no refund, EAs need an add-on). With AurumFunded at size 0.3 and a guard 4.5% under the peak
(`AurumFunded_FundedNext_instant.set`): first payout within 1 month 43%, 3 months 74%, median 1.4 months, no
account lost (70% of the edge); half edge with pessimistic dips 59% within 3 months, 1.1% lost. The first claim is
about 1.7% of the account; the FTMO challenge pays far more per month but takes about 9.6 months to the first payout.

With AurumNoise added (0.55 of the S&P 500 + Nasdaq basket, 0.75 bp) the funded legs' Sharpe goes from 2.97 to 3.11,
the FTMO first payout within 6 months from 19% to 25% (median 9.6 -> 9.2 months), the instant account's within 3
months from 74% to 76%: worth having, but the challenge's speed is set by earning 15% at limited risk.

**Deadline sizing (`tools/prop_dp.py`, dynamic programming = what an RL agent would learn):** passes both phases
within 9 months 82% of the time at 70% of the edge with 1% failed (cushion rule 57%, 0%), but fails about 20% if the
live edge is only half. Use it only once live results confirm the edge; until then the cushion rule.
AurumFunded 1.02 has it as `InpPropFast` (off by default) in a safe form: the table only while equity is at or above
the phase's start, the cushion rule below - both phases within 9 months 67% (cushion rule 57%), median 7.3 months
(8.0), no failure even at half the edge with pessimistic dips. Not yet run in the Strategy Tester.

Open points for EA 2:

- Run in the MT5 Strategy Tester on FTMO's data (2026-10-15 phase runs, 2026-10-17 j3); the symbol names in the inputs
  (`XAUUSD`, `US500.cash`, `US100.cash`, the dollar pairs and yen crosses) all traded there, so they are FTMO's.
- FTMO's server clock is assumed to follow European summer time (`InpEuClock true`). The EA checks the clock live and
  skips the day if it is off.
- Margin: FTMO Swing leverage is quoted (by a user on FTMO's feature board, not on FTMO's own page) as 1:30 on
  currencies, 1:9 on metals, 1:15 on indices. A gold unit at size 0.5 is about 1.2-1.5x equity at usual gold
  volatility and 3.1x at most (`InpMaxLeverage` 6.2 x 0.5), so 15-35% of equity in margin at 1:9, inside the
  per-order cap `InpMarginPct` (50% of free margin). The currency legs are far smaller. The tester run will confirm.
- The gold-unit broker stop is not in the Python model.

## EA 1: AurumHydra (v1.32)

Eight legs: quartet (gold session dip, bell fade, Tokyo fixing, EUR/USD midday), AUD/CAD grid, gold hold, month-end
fix on dollar pairs, the same on yen crosses, stock-fall fix, Tokyo morning, day after a US holiday. Combined Sharpe
3.0 (2.6 to 2017, 3.4 from 2018), volatility 24.5% a year. By calendar year the whole book's Sharpe is between 2.0 and 5.5 in every year
2010-2026 (AurumFunded's legs 1.9 to 5.3); 2023-2026 3.3; 2026 to date 2.0, with the quartet at 0.9, the weakest
year since 2023. With a Sharpe of 3 the best reachable chance of 5x in a
month is about 51%; the goal mode of the EA tests at 47% (preset `AurumHydra_5x_month.set`). If the live Sharpe is lower, the best chance falls with it: 34% at 1.5, 29% at 1.0, and 20% with no edge at all
(a fair bet sized to reach 5x does so one time in five), from P = N(N^-1(0.2) + Sharpe x sqrt(1/12)) (Browne 1999,
reaching a goal by a deadline). More chance needs more
Sharpe, which means new legs that are uncorrelated with these.

**Candidate leg (2026-10-15): noise-area intraday momentum on the S&P 500 and Nasdaq CFDs** (Zarattini, Aziz,
Barbon 2025, read in full; `research/noise_area_index.py`). Bands of the average move from the 9:30 open over 14
days, checked every half hour from 10:00 New York, trailing stop at the band or the session average price, flat
at 16:00, sized to 2% daily volatility. Half S&P 500 (band multiple 1.5), half Nasdaq (1.0): Sharpe 0.88 at 0.75
bp a round trip (0.61 to 2017, 1.08 from 2018), 0.57 at 1.5 bp; correlation with the Hydra legs -0.02. With the
weight fitted to 2017, Hydra from 2018 goes from 3.38 to 3.55 (0.75 bp) or 3.46 (1.5 bp). Standalone MQL5 version
`mql5/Experts/AurumNoise/` (presets for US500.cash and US100.cash), written without a compiler at hand: next is a
Strategy Tester run on FTMO's data, 2024-01 on, to see the real spread and slippage (Python on 2024-01 to 2026-10
from 10,000 at full size: US500 +1,550 before cost, +472 at 0.75 bp, drawdown 24-27%, 451 trades; US100 +5,352
before cost, +3,746 at 0.75 bp, +2,307 at 1.5 bp, drawdown 17-23%, 701 trades), then a merge into AurumHydra and
AurumFunded if it holds. Histdata's tick quotes put the spreads at 0.7-1.0 bp (S&P 500) and 0.3 bp (Nasdaq),
so 0.75 bp is about right on average. DAX, FTSE, Nikkei,
currencies, oil, silver and gold do not add.

**Candidate leg (2026-10-15): USD/JPY London breakout** (the retail "London breakout" concept, own test;
`research/london_breakout.py`). Range = high and low of server 01:00-09:00; from 10:00 to 18:00 server follow the
first 5-minute break of it, stop at the range's other side, flat at 18:00. Sharpe 0.97 at 0.8 bp a round trip
(0.96 to 2017, 0.98 from 2018, positive in 16 of 17 years, 0.59 at 1.5 bp), every shifted window 0.73-1.17;
upside breaks carry it (t 4.4). Trading each side on its own (a buy and a sell stop that each fire once a day,
chosen on 2010-2017) gives 1.40 / 1.08 and is AurumBreakout 1.01's default; on real bid/ask ticks (2024-01 to
2026-09, `research/breakout_ticks.py`) fills cost ~1.2 bp all in, at which the leg is 1.18 / 0.83 and still lifts
AurumFunded 3.24 -> 3.30; the same breaks on the other dollar pairs do not earn, but before cost every yen cross (EUR/JPY 1.50, GBP/JPY 1.23,
CAD/JPY 1.21, AUD/JPY 0.63) and the Nikkei (1.37) show it in both halves - a yen effect, too costly outside USD/JPY. Correlation with the Hydra legs |r| <= 0.03. At 0.5% risk a trade Hydra 3.37 ->
3.48 from 2018 (3.66 with the noise leg), AurumFunded 3.24 -> 3.34; at AurumFunded's volatility 0.125% risk a
trade gives 3.30 with a lower drawdown (11.4% -> 10.8%). Gold, EUR/JPY and the other majors do not hold. Standalone
MQL5 version `mql5/Experts/AurumBreakout/`: run in the Strategy Tester on USDJPY 2024-01 on (2026-10-17, +9.96%,
4.02% eq DD, 771 trades, matches Python; step 15 passed).
AurumFunded 1.03 carries the same leg, off by default (`InpBreakRiskPct=0`; 0.125 is the size tested next to the
other legs, a quarter of the fix leg's risk): server hours 01:00-09:00 range, 10:00-18:00 trading, each side once a
day at market when the ask / bid reaches the range, magic +26 / +27, sized through `SizeMult()` so the prop cushion
and guards apply, closed by `CloseEverything()`. It also carries the noise-area leg, off by default
(`InpNoiseMult=0`; 0.275 per index is the tested weight 0.55 split over two): S&P 500 = `InpStocks` with band 1.5,
Nasdaq = `InpNasdaq` (US100.cash) with band 1.0, checks at server 17:00-22:30 (10:00-15:30 New York), flat at 23:00,
notional = min(4, 2% / 14-day volatility) x equity x `InpNoiseMult` x `SizeMult()`, magic +28 / +29. (Written
uncompiled; since built and run in the tester, see "Current state".) Order of tests, all done by 2026-10-17 (steps 15
and 16 passed; AurumNoise in the tester: US500 -0.68% / 26.09%, US100 +39.93% / 16.41%): the standalone AurumBreakout and AurumNoise first; if they hold, AurumFunded
1.03 with `InpBreakRiskPct=0.125` and `InpNoiseMult=0.275`. AurumHydra 1.33 carries the same two legs, off by default and with
the same inputs; for the 5x-month goal the tested weights are breakout at 0.5% risk a trade (`InpBreakRiskPct=0.5`,
weight fitted to 2017) and the noise leg at 0.275 per index. Hydra has no clock check, so in the weeks the US and
European summer times differ its legs - old and new - run an hour off New York, as before.

Both candidate legs in the prop simulators at AurumFunded's volatility (`tools/prop_candidates.py`, breakout on
both sides): FTMO first payout within 12 months 67% -> 72% (breakout), 72% (noise), 75% (both) at 70% of the edge,
no FTMO failures even at half the edge; the instant account's median 1.4 months unchanged; Sharpe from 2018 3.24 ->
3.49 with both (at the measured costs). Neither enters the prop presets before its tester run. News rules: FTMO Swing has none; FundedNext Stellar Instant counts
only 40% of the profit of trades executed within 5 minutes of a listed high-impact release (losses in full; help
centre article 11641410). The breakout trades through 8:30 New York (server 15:30): entries within 15 minutes of it
are 8% of trades and its best ones (+0.125 R against +0.049 R, both halves, 2010-2026), so no news filter - on the
instant account the rule trims part of their profit on release days. Consistency: sources disagree on whether Stellar Instant has a 40%
best-day rule; with it the first payout's median goes from 1.4 to 4.3 months (`tools/prop_consistency.py`), and
neither a later claim nor a larger size helps. Confirm with FundedNext before buying - it decides the instant account's
speed (FTMO stays at ~9.6 months). Alternative without that doubt: **Instant Funding PRO** (instantfunding.com, rules read
2026-10-15: no target, no daily limit, no consistency rule, 10% maximum loss that tightens to 5% for good once +5%,
first payout after 14 days once +5%, then weekly; no weekend holding without an add-on; metals and indices 1:5 for
now). `tools/prop_instantfunding.py`: size 0.5 gives a median 2.5 months to the first payout and no lost accounts
even at half the edge; size 0.7 2.0 months (6.7% lost at half the edge). EA policy to confirm with them first. AurumFunded 1.03 follows the tightening with
`InpPropLockPct=5` / `InpPropLockStopPct=3.5` (final stop -8.5% until +5% is first reached, then -3.5%); a fixed
-4.5% stop instead would lose 18% of accounts at half the edge. Preset `AurumFunded_InstantFunding_pro.set`. Instant Funding also has an "Account Drawdown": open positions losing a set % of the starting
balance together are closed by the firm (2% in their example; first time the split falls to 50%, second time the
account is lost). At size 0.5 AurumFunded's legs close a day beyond -2% about 0.5 times a year (-1.5%: 1.7 times),
more often intraday; so the EA has `InpPropFloatPct` (closes everything for the day first, 1.7 in the preset) - ask
the firm for PRO's figure. FTMO's 1-Step (reviews, to verify on ftmo.com: 10% target, 3% daily, 10% end-of-day trailing
maximum, 50% best day) at size 0.5 with a 2% EA day stop: first payout median 7.8 months, none failed even at half
the edge (`tools/prop_ftmo_1step.py`) - a little faster than the 2-Step, slower than the instant accounts. For AurumHydra's 5x month: Sharpe from 2018
3.37 -> 3.71 with both legs (breakout at 0.5% a trade, weight fitted to 2017), so P = N(N^-1(0.2) + S sqrt(1/12))
goes from 55% to 59%.

Tested and rejected (do not repeat): Asian dip buy and shock fade, LBMA auction dip, burst fade, channel breakout,
deep and reinforcement learning replications, HFT, market intraday momentum (unconditional, both-agree, big-move),
minute slot scan, daily ML, noise-area momentum, session-open drift, overnight-intraday reversal, scalp concepts,
tick ML scalp, FX fixing reversals, pre-FOMC drift, overnight drift, FOMC cycle, FX local hours, pre-announcement
drift, turn of month, market return around the clock, Bitcoin intraday momentum, market intraday momentum under
short-gamma proxies (high VIX, falling or jump day), shorter last windows, next-day fade of the last half hour, crude oil
intraday momentum on EIA report days (Wen, Indriawan, Lien, Xu 2023; `research/oil_eia_intraday.py`),
time-series momentum on 20 daily futures (Sharpe 0.5 at best; `research/futures_tsmom.py`), time-series momentum on
Bitcoin and Ether (Sharpe 0.5 to 0.7 long-short since 2022 before CFD swap; `research/crypto_tsmom.py`), and in `research/daily_candidates.py`: SPY before holidays, SPY under
a VIX term-structure filter, gold/silver ratio fade, Monday after a falling Friday, SPY after VIX spikes, daily and
weekly reversal in US stocks, gold month-end flow; gold's London bias and weekend-gap fades (`research/gold_london_and_gaps.py`); hour-of-day returns of the hourly FX, gold and crypto
series (`research/hourly_seasonality.py`); drift after payrolls and FOMC decisions in the dollar pairs, gold and
the S&P 500 (`research/post_announcement_drift.py`); VWAP trend trading on the
Nasdaq and S&P 500 (Zarattini, Aziz 2023; dies on costs at 18 reversals a day, `research/vwap_trend_index.py`); front-running
pension rebalancing (Harvey, Mazzoleni, Melone 2025; month-end half holds after the paper but adds nothing to Hydra
in 2018-2023, `research/rebalancing_frontrun.py` - a lead to re-check); volatility-managed sizing of the legs (Moreira, Muir 2017; the legs earn in proportion to their volatility, so it only lowers the Sharpe, `research/vol_managed_legs.py`); the gold "Forecast-to-Fill" trend rule (Singha et al. 2025; its Sharpe 2.9 is same-close look-ahead, 0.5 when filled next day, `research/gold_forecast_to_fill.py`); Deep Momentum Networks (Lim, Zohren, Roberts 2019; Sharpe-optimised LSTM on the 20 futures, 2011-26 Sharpe 0.1 against 0.55 long only, `research/deep_momentum.py`); the AUDCAD grid on 15 other pairs (none holds after 2017, `research/grid_crosses.py`); the 5-minute opening range breakout on the Nasdaq and S&P 500 (Zarattini, Aziz 2023; 0.5-0.7 on true highs and lows, adds nothing next to the noise-area leg, `research/orb_index.py`); cross-session momentum in gold and silver (from the title of Wei 2026, the paper is behind SSRN; works only in the 2023-26 gold rally, `research/cross_session_metals.py`); the deep Q-learning trader of Zhang, Zohren, Roberts 2020 on the 20 futures (seeds give +0.54 to -0.17 at 2 bp, all <= 0 at 10 bp, `research/drl_futures.py`); a larger fix-leg size at quarter-ends (one-off check: quarter-end fixes earn the same as other month-ends, 64 vs 49 bp to 2017 and 84 vs 89 bp from 2018, and x2 at quarter-ends takes Hydra from 3.37 to 3.31 after 2017); the after-holiday leg for the yen and sterling (Japanese and English holidays: +2.9 bp t 1.3 and nothing, `research/after_holiday_other.py`); gold and silver in the month-end fix leg (one-off check with `fix(pairs=...)`: gold t 1.2, silver t 2.2 but correlated 0.35 with the fix leg, Hydra from 2018 3.37 -> 3.34-3.36); the "night scalper" fade of 15-minute Bollinger breaks after the New York rollover on 11 pairs (1-2 bp a trade before costs, -1.5 at 1 bp, `research/night_scalper.py`); oil leading USD/CAD intraday (Ferraro, Rogoff, Rossi 2015 in spirit; one-off check: a 15-minute WTI move predicts the next 15-30 minutes of USD/CAD by 0.06-0.09 bp, t 3, far below cost; big oil moves no more); fading Bitcoin's weekend move over Monday (one-off check, 478 weeks, 10 bp: -44 bp a week, weekend and Monday uncorrelated; following it worked only from 2022); fading silver's 15-minute moves against gold over the next hour (one-off check: a real reversal, 2.2 bp at |z| > 2, t 6.8 in both halves, but silver plus gold cost ~5 bp; at |z| > 5-6 about +0.3 bp net and unstable); the same fade on AUD/USD vs NZD/USD (t 14, 1.2-1.75 bp against ~2.4 bp of cost) and GBP/USD vs EUR/USD (0.4 bp) - intraday relative moves revert, but by less than the spread (by session the AUD/NZD one is 0.3-2.0 bp, best London at 2.0; much of the all-hours figure is the rollover's quote spikes); gold around the Shanghai Gold Benchmark auctions, 10:15 and 14:15 Beijing (one-off check: windows of 15-120 minutes earn 0-1 bp, the same before the benchmark began in 2016 - the Asian-hours drift, below cost); an intraday Nasdaq / S&P 500 pairs fade (-2.8 bp a trade, the spread trends a little within the day but not enough to pay two legs, `research/index_pair_intraday.py`); fading 15-minute price shocks on 11 instruments (Grant, Wolf, Yu 2005; 0 bp before cost, `research/shock_reversal_fx.py`); online re-weighting of the legs by exponentiated gradient (Helmbold et al. 1998; 2.7 from 2018 against 3.37 fixed, `research/online_leg_weights.py`). Re-fitting the leg weights for the highest Sharpe does not hold
out of sample, so the EA's weights stay. The scans are in `research/`.

## Cloud sessions

The cloud container has no route to histdata.com, Dukascopy or Yahoo (the proxy refuses them), so the minute data
cannot be rebuilt there; only what is in the repository can be used (hourly gold and Hydra pairs from 2009, daily
futures, stocks, ETFs, volatility indices, crypto hourly from 2017). Allowing those hosts in the environment's network
settings would lift that. raw.githubusercontent.com and web search do work; no GitHub repository was found that holds
the minute data itself.

## Tools and data

- `tools/backtest_hydra.py`: every Hydra leg on minute data. `tools/backtest_prop.py`: the challenge simulator.
- Minute data (`marketdata/histdata/*_M1.csv.gz`, 7 GB) is not on GitHub; `tools/` has the histdata.com downloader
  that rebuilds it. Without it the challenge simulator still runs from the cached daily leg results.
- Compiling: `metaeditor64.exe /compile:<file> /include:<terminal data folder>\MQL5 /log:<file>`; see
  `tools/run-backtest.ps1`.
