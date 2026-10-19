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
  7/10/9 months; that is the 4x/5x shortfall against the model (lesson 19). The goal model
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
- **Next pipeline work (no tester time):** researcher: the China release calendar for `china_release_aud` (below),
  NSXUSD M1 (NAS100) from histdata (else SPX as a stated proxy), and new ideas with a reason (lesson 10). Fidelity: the FTMO demo's symbol margin for XAUUSD/AUDCAD
  against the fitted 1:50 / 1:100, and the first demo week from 2026-10-19.
- **AurumFunded:** j12 (FTMO funded preset), j13 (FundedNext Stellar Instant), j14 (Instant Funding PRO) all judged
  PASS at step 16 (tester keeps 0.67-0.84 of the model's log growth, lesson 4 band). Open follow-ups needing no
  tester time: j12-vs-j3 deal lists on the three extra day-stop days; j14's floating-stop days to price the 1.7%
  stop; the EA never logs its trailing-stop floor (log line proposed). Prop routes and presets: see archive.
- **Demo (step 17):** AurumFunded 1.03 with both legs on, FTMO demo, attached 2026-10-17; first trades when gold
  opens Monday. The monitor reports in `docs/demo_log.md`; fidelity pairs demo fills with a tester run weekly.
  Watch: gold entries must come on the same days as the tester's (the `InpGoldMaxSpread=0.30` cap).
- **Tester queue** (`docs/autopilot/queue.json`): j1-j15 done or judged, nothing queued; the size cap
  closed without a tester job. Scan candidates scan_slot_EURUSD_s25_L4_short, s21_L8_short and
  scan_cal_wed_EURUSD_s25_L2_short rejected 2026-10-18 (gates.py failed 2026-10-17). Judgements live in each `backtests/<folder>/summary.md`.
- **Research pipeline:** simple-rule scans on the histdata symbols are exhausted (all four `edge_scan.py` families
  run; the record is `docs/trials.jsonl` and the Scans note in the archive) — a new scan needs new data and goes
  into `docs/autopilot/scan_requests.json`. Ideas: Osler round-number levels rejected at steps 5-7 (new rejected
  family). **Candidate `china_release_aud`** (idea 2026-10-18/1, step 4 done 2026-10-19, runs 1): the RBA Bulletin
  Dec 2016 PDF is now readable and was read in full; Table A1 matches the idea file (extra absolute AUD/USD move,
  -10..+10 min, 2008-16: GDP 0.06%, activity 0.04%, trade 0.03%, CPI 0.04%; volatility only, no direction or cost).
  Step 5 is blocked on data: **researcher, fetch the China release dates and times 2010-2025.09** (NBS GDP,
  activity, CPI; customs trade) from a dated calendar archive, into the repo through `holdout.drop()`. Then a
  quant-coder prototype on AUDUSD M1 (AUDCAD check), reported against same-time non-event days. Dropped unstarted
  2026-10-19: 2026-10-18/2 (S&P rebalance close, ~64 events) and 2026-10-17/4 (expiry-week drift, summary only).
  Still unstarted: 2026-10-17/1 and /3 (**unverified**, abstract only, go last), so the researcher is no longer
  skipped. `pdf_text.py` retries mirrors before marking a paper unreadable.

## Waiting on the owner

- Prop-firm facts: FundedNext Stellar Instant consistency rule; Instant Funding PRO account-drawdown % and EA
  policy; FTMO 1-Step maximum loss (details in the archive).
- Commit 031f5b6 carried 18 staged renames into `mql5/Experts/_archive/` (.ex5 rule broken): keep or revert.
- Anything in `docs/autopilot/approvals.json` with status "pending".
