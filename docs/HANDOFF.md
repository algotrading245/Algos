# Handoff: where the two-EA project stands (one page)

For a session that picks this work up without the earlier conversation. Last updated 2026-10-19 (owner's change 6:
this file is the current state only; the full history, all job judgements j1-j15, the **"Tested and rejected"** list,
the **Scans** record and the EA / prop-route details are in `docs/HANDOFF_archive.md`).

## Goal

Two MT5 expert advisors, and the work does not stop until both exist:

1. **5x EA**: turn $100 into $500 in a month with the highest probability — `mql5/Experts/AurumHydra/`.
2. **Funded-account EA**: pass a prop-firm challenge and keep the funded account — `mql5/Experts/AurumFunded/`.

Fixed rules: nothing enters an EA unless it survives real costs in both data halves (to 2017 / 2018 on); papers are
read in full before use (unverified ideas go last); order is Python backtest → Strategy Tester → demo → live; the
server 23:00-01:00 rollover stays out of intraday tests; holdout: 2025-10-13 on (`tools/holdout.py`) is the owner's,
agent tester runs end 2025-09-30, the clean out-of-sample test is the demo from 2026-10-19; commit and push after
each finished piece of work.

## How the work runs (2026-10-18)

- **Relay of agents** (`tools/autopilot/relay.ps1`, every 5 min): researcher → scanner → orchestrator → tester →
  fidelity, no gap inside a cycle, 30 min between cycles; a role that has nothing to do is skipped, and no role runs
  twice in one tick. One agent at a time (mutex); usage, session and quota limits back the relay off 60 min.
  Prompts: fixed parts first (memory, role) so repeats hit the cache, status last.
- **Model router** (`tools/autopilot/router.json` + `router.py`): one switch picks the provider for every role —
  **Claude Code** or **Qwen Code** — and each role maps to a tier (routine / code / judge) that each provider names a
  model for. Switch the whole system with `python tools/autopilot/router.py use qwen|claude`, one role apart with
  `... use claude --role orchestrator`, a tier's model with `... use qwen --tier code --model qwen3-coder-plus`;
  `... show` prints the current mapping. If the provider it points at cannot authenticate (a Qwen run with no API
  key) the run falls back to the other provider and says so in the log, so the pipeline never idles over a key.
  Qwen specifics: no `--agent` flag, so `run-agent.ps1` inlines the role definition into the prompt and the two
  subagents are mirrored into `.qwen/agents/` (`python tools/autopilot/mirror_agents.py` after any change to
  `.claude/agents/`); permissions come from `.qwen/settings.json` (committed: the deny list, which is the only gate
  because runs use `--approval-mode yolo` — deny still outranks yolo) and the API key is an environment variable in
  `~/.qwen/settings.json` (user level, outside the repo, never committed).
- **Mechanical work is scripts, not agents:** `tools/autopilot/tester_step.py` starts and collects tester jobs,
  writes each `summary.md`, commits, and routes a collected job to the orchestrator (`logs/autopilot/to-judge.json`);
  the tester agent only runs when the script writes `tester-help.json`. `tools/autopilot/scanner_step.py` works
  through `docs/autopilot/scan_requests.json` (the orchestrator appends requests; a survivor that passes every gate
  or a broken scan raises `scanner-flag.json` for the scanner agent). Both are started by the keeper every minute
  and have their own locks, so MT5 runs never block the agents. The keeper also keeps Terminal 16 (demo EA) open.
- **Shared memory** in `docs/memory/` (mission, lessons, decisions.jsonl) goes into every prompt; agents search it
  before deciding and log every decision. Orchestrator run limit per idea: 3 (`runs` in `docs/candidates.json`),
  then drop, move on, or ask the owner.
- **Terminals:** Terminal 16 ("MetaTrader 5 - 16") runs the FTMO demo EA (AurumFunded 1.03, XAUUSD M15,
  `AurumFunded_FTMO_phase1_legs.set`, legs on since a3); the tester is its own install `C:\MetaTrader 5 - Tester`
  (owner login done 2026-10-18). Live page: `python tools/live_server.py` (127.0.0.1:8765).

## Current state

- **Both EAs share one leg library** (`mql5/Include/Aurum/`; Hydra 1.33, Funded 1.03 are thin wrappers). Breakout
  and noise legs passed steps 15-16 and are on by default in the demo: Hydra 0.125 / 0.275, Funded half that.
  Other EAs are archived in `mql5/Experts/_archive/`.
- **AurumHydra (5x goal), InpTarget tested on 21 fresh-deposit months 2024.01-2025.09:** 3x in 9 of 21 (43%),
  4x in 4 (19%), 5x in 2 (10%), 0 ruin months — but the "0 ruin" hides broker stop-outs (margin level < 50%) in
  7/10/9 months; that is the 4x/5x shortfall against the model (lesson 19). These 21 months ran at 1:100 and j8a-c
  (5x 1/21) at 1:33, not the 1:500 asked; lesson 7 amended 2026-10-19 to judge each at its logged leverage. The goal model
  (`research/hydra_goal_margin_model.py`, EA+legs round 5: per-order clip, month-end boost ×2) gives P(goal)
  39.7 / 28.8 / 22.3% over 184 months 2010-2025.09 (edge 1.0, preset) — a **loose upper bound only**: reviewer
  REDO, the noise is still round 4's constant ticket (NSXUSD M1 missing), on the 21 tester months the model reaches
  the goal 10/10/9 times against the tester's 9/4/2. Model iteration stopped (run limit); do not quote r5 edge-0.7.
- **Size cap (candidate `hydra_size_cap`, CLOSED after run 3 of 3, 2026-10-19: keep InpGoalCap 50, no EA change):** `research/hydra_size_cap.py` fixed the
  round-5 REDO items (C1 no-clip branch + unit tests, fix before cross, boost haircut at edge 0.7; noise P&L and
  balance-vs-equity sizing stay stated limits) and swept static InpGoalCap 3-14 against 50. Keep cap 50: every cap
  <=14 loses 19-25 pp of P(goal) for near-zero stop-outs (with the fixes, cap 50 gives 39.7/28.8/22.8%). Reviewer
  PASS WITH CHANGES: caps 15-49 are untested (cap 50 binds in 55-76% of rounds, median day-1 size asked 36-47).
  **Run 2 (2026-10-19, `research/hydra_size_cap2.py` + `.out.txt`):** static caps 20-45 do not beat 50 by the
  pre-registered rule (3x to 2017: 27.5/31.9/38.5/39.6/42.9/44.0% vs 44.0%; 45 ties 50), so cap 50 stays. The
  dynamic arm was void: it projected margin before the EA's 50% free-margin clip and summed tickets not open
  together, so s_dyn <= 2.9 at every threshold (reviewer PASS WITH CHANGES; lesson logged).
  **Run 3 (2026-10-19, `research/hydra_size_cap3.py` + `.out.txt`):** clip-aware projection in the EA's order, legs
  as the peak open together, plan fitted to 2017. The pre-registered guard found every threshold 1.1-3 DEGENERATE
  (binds on 97.8-99.2% of days, median bound s_dyn 3.0-0.0), so no sweep ran and there were 0 new trials. Reviewer
  PASS WITH CHANGES: the result is real. The goal preset fits only through the 50% clip (legs alone 0.128 margin per
  unit of size), so a margin-level cap above 1 is a static cap of 0-3, which run 1 rejected. Lesson 20.
- **Next pipeline work (no tester time):** researcher: new ideas with a reason (lesson 10); no unstarted idea
  is left. NSXUSD M1 is now in `marketdata/histdata` (2010-11 to 2025-10, fetched 2026-10-19), so the noise
  leg's P&L in the goal model can be redone from data (the round-5 REDO item). Fidelity: the demo account's own
  leverage (and XAUUSD margin rate, about 2). This is now the deciding check for j12-j14: the tester install ran
  them at 1:100 (gold 1:50) and Terminal 16 ran j3 at 1:33 (gold 1:16.5). Also the first demo week from 2026-10-19.
  **Leverage log line (2026-10-19, AurumFunded 1.05 / AurumHydra 1.35, reviewer PASS WITH CHANGES, compile 0/0):**
  once a server day each EA prints "account leverage 1:n, margin of 1 lot in <currency>, XAUUSD m at p, ..." (gold,
  USDJPY, EURUSD, grid symbol, stock index; "n/a" for a symbol not in use). Logging only, no trading change. Fidelity
  reads it from the demo's EA log on its first day attached, and from the agent log of any new tester run. Hint: the
  AurumFunded header's default account is an FTMO Swing account at 1:30, close to j3's 1:33, not j12-j14's 1:100.
  **Tester leverage (2026-10-19, reviewer-checked, lesson 19 corrected):** the job's `leverage` has never been
  applied; each terminal tests at its saved [Tester] leverage. So every Terminal 16 run on 10-15/17/18 (Hydra
  j4-j9, the 10-17 month series and the 10-18 5xEQ runs, asked for 500) ran at 1:33, and every tester-install run
  on 10-18 (j12-j14, t3b-t5b) ran at 1:100; check the agent log for any other run. Re-read any Hydra conclusion drawn from Terminal 16 runs with that in mind (no re-run
  yet; holdout rule for j8b/j8c/j9 unchanged). Evidence: `research/demo_margin_terminals.py` + `.out.txt`.
  **Hydra leverage sensitivity (2026-10-19, `research/hydra_leverage_sens.py` + `.out.txt`, 0 trials):** the
  goal model (size-cap fixes, now the round-5 noise path from SPXUSD/NSXUSD M1) at cap 50, only the margin rates
  scaled. Calibration holds: at 1:100 the model's stop-outs on the 21 tester months are 8/8/9 vs the tester's
  7/10/9 (its goals 10/9/8 vs 9/4/2 still overstate). Over 184 months, edge 1.0, 3x/4x/5x, P(goal) / P(stop-out) /
  share below 0.5x: 1:100 40.8/32.1/24.5 / 20.1/26.6/33.7 / 31.0/30.4/32.1%; 1:500 53.3/45.1/40.2 / 17.9/20.1/22.8
  / 41.3/48.4/52.2%; 1:33 25.5/17.4/12.5%. Pre-registered rule B NOT MET (stop-outs fall 24-32%, not half): the
  tester's stop-outs are not mainly the leverage. Rule C MET (+13/+16 pp at 4x/5x). So a 1:500 account trades
  more goals for more deep losses (median 5x result 0.89x -> 0.31x), and the 1:100 tester figures (9/4/2 of 21)
  do not stand for a 1:500 account in either direction. Hydra figures only count at a leverage written into the job
  and checked in the log, so tools change (4) is now needed for Hydra too. The model's levels stay an upper bound.
- **AurumFunded:** j12 (FTMO funded preset), j13 (FundedNext Stellar Instant), j14 (Instant Funding PRO) all judged
  PASS at step 16 (tester keeps 0.67-0.84 of the model's log growth, lesson 4 band). **j12-vs-j3 closed
  2026-10-19** (`research/funded_j12_j3_daystops.py` + `.out.txt`): j12's 3 extra day stops are its XAUUSD bell at
  2-2.9x j3's lots. The cause is the test leverage, not the library: j3 ran on Terminal 16 at 1:33 (gold about
  1:16.5), and j12-j14 (and Hydra t3b-t5b) ran on the tester install at 1:100 (gold about 1:50), though every one
  of these jobs asked for 33. So the j12-j14 figures hold only if the demo account runs at 1:100; fidelity's
  leverage check decides that (lesson 19, corrected 2026-10-19). **j14's 1.7% floating stop priced 2026-10-19** (`research/funded_j14_floatstops.py` +
  `.out.txt`, closed baskets held on histdata to server 00:00): outside rollover (9 of 13 stops) it saved 7.06% and
  8 of 9 held baskets would have crossed the firm's assumed -2%; a 1.8 / 1.9 stop would have avoided 0 / 1 of 9. So
  1.7 stays. The other 4 stops are the XAUUSD 23:00 bell at 0.72-1.22 lots (5-20x the intraday gold legs), stopped
  26 s to 3 min after entry by a $1.4-2.4/oz move (checked on histdata: mostly real moves, not spread). On IF PRO the
  bell at that size can trip the Account Drawdown alone; its size follows the gold margin (1:50 at the tester
  install's 1:100), so the fidelity leverage check decides this too. Owner question stays: the PRO Account Drawdown figure.
  Still open: the EA never logs its trailing-stop floor (log line proposed). Prop routes and presets: see archive.
- **Demo (step 17): ALERT 2026-10-19. The EA is NOT attached** (re-checked 08:51: today's journal has no Experts
  line and the EA log still exists only for 20261017). AurumFunded 1.03 loaded on Terminal 16 on 2026-10-17
  at 04:33 and was removed at 04:57. The tester runs on that terminal (10-17 to 10-18 01:20) left no `<expert>` block
  in the saved charts. The keeper then restarted the terminal plain at 01:24 (it was a stale copy started before the
  attach branch existed), and the terminal has stayed open with no EA. So there are no demo trades, and the clean
  demo test has not started. Details are in `docs/demo_log.md` 2026-10-19. Fidelity has nothing to compare until the
  owner re-attaches the EA (approvals a4). The monitor reports in `docs/demo_log.md`; fidelity pairs demo fills with
  a tester run weekly.
  Watch: gold entries must come on the same days as the tester's (the `InpGoldMaxSpread=0.30` cap).
- **Tester queue** (`docs/autopilot/queue.json`): j1-j15 done or judged, nothing queued; the size cap
  closed without a tester job. Scan candidates scan_slot_EURUSD_s25_L4_short, s21_L8_short and
  scan_cal_wed_EURUSD_s25_L2_short rejected 2026-10-18 (gates.py failed 2026-10-17). Judgements live in each `backtests/<folder>/summary.md`.
- **Research pipeline:** simple-rule scans on the histdata symbols are exhausted (all four `edge_scan.py` families
  run; the record is `docs/trials.jsonl` and the Scans note in the archive) — a new scan needs new data and goes
  into `docs/autopilot/scan_requests.json`. Ideas: Osler round-number levels and China releases and AUD
  (`china_release_aud`, net -0.017 R a trade from 2018 at 1.1 bp) rejected at step 7; eight more ideas were dropped
  at step 4 on 2026-10-19 (paper read in full or unreadable, 0 trials). All of them are in the archive's "Tested and
  rejected" and "Dropped before any test" lists. **No unstarted idea is left**: the researcher's turn (researcher
  runs 1-9 on 2026-10-19 found 4 ideas, all dropped; the last, run 9's leveraged-ETF close flow, at 10:06). Do not
  re-propose carry or other slow cross-section FX books, or close-flow ideas on the index (see archive).
  `pdf_text.py` retries mirrors before marking a paper unreadable.

## Waiting on the owner

- **Urgent (a4): re-attach the demo EA.** On Terminal 16, open XAUUSD M15 and attach AurumFunded 1.05 (the
  current build in the repo; copy `AurumFunded.ex5` into the terminal's Experts folder first) with
  `AurumFunded_FTMO_phase1_legs.set` (Algo Trading on). Check that the journal says "expert AurumFunded (XAUUSD,M15)
  loaded successfully" and that the EA log has its "phase 1 started" line and, on the first tick, the "account
  leverage 1:n" line. Then save the profile, or close the
  terminal once so the chart files are written. Agents may not attach an EA.
- **Proposed tools/ changes (agents may not edit tools/):**
  (1) `keeper.ps1`: while Terminal 16 is running, look at the journal after its latest start for "expert
  AurumFunded ... loaded successfully" not followed by "removed". If that line is missing for more than 10 min, log
  an ALERT, or restart the terminal with `t16_attach.ini`. Today `Test-DemoEA` is checked only while the terminal
  is closed.
  (2) The keeper should restart itself when `keeper.ps1` or `common.ps1` is newer than its own start. The copy that
  ran at 01:24 on 10-18 was the 10-17 process running old code.
  (3) `demo_check.py`: raise an ALERT when a weekday has 0 EA lines, or when the journal's last Experts line for
  AurumFunded is "removed". Today it printed "ok" for a day with no EA.
  (4) `run-tester.ps1:151` writes `Leverage=$Leverage` (e.g. `33`), which the tester does not apply (the deposit
  is applied). Try `Leverage=1:$Leverage`, the format the tester logs. Then make `tester_step.py` read the agent
  log's "initial deposit X USD, leverage 1:n" line and fail the job if n differs from the job's `leverage`.
  `tester_step.py:300,342` should report the logged leverage, not the requested one. Until that is done, the
  leverage of every run is whatever the terminal has saved: Terminal 16 1:33, tester install 1:100.

- Prop-firm facts: FundedNext Stellar Instant consistency rule; Instant Funding PRO account-drawdown % and EA
  policy; FTMO 1-Step maximum loss (details in the archive).
- Commit 031f5b6 carried 18 staged renames into `mql5/Experts/_archive/` (.ex5 rule broken): keep or revert.
- Anything in `docs/autopilot/approvals.json` with status "pending".
