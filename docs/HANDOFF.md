# Handoff: where the two-EA project stands (one page)

For a session that picks this work up without the earlier conversation. Last updated 2026-10-18 (owner's change 6:
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
  fidelity, no gap inside a cycle, 30 min between cycles. Models: Opus judges and plans (orchestrator, reviewer),
  Sonnet codes and confirms routine judge runs (quant-coder, fidelity, a judge run whose fixed expect check matched),
  Haiku does routine work (researcher, tester help, monitor). One agent at a time (mutex); usage limits back the
  relay off 60 min. Prompts: fixed parts first (memory, role) so repeats hit the cache, status last.
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
  (`research/hydra_goal_margin_model.py`, EA+legs round 4) now gives P(goal) 35.9 / 26.1 / 19.0% over 184 months
  2010-2025.09 — **upper bounds**: reviewer REDO, the other legs' per-order 50% free-margin clip is biased low, the
  edge penalty unclipped, month-end boost and noise hours/size missing.
- **Next pipeline work (no tester time):** quant-coder round 5 of the margin model (sequential per-order clip with
  the pair count per leg, edge penalty × clip ratio, month-end boost ×2, noise from 17:00 with vol leverage, a clip-
  path check), then the reviewer; then the margin-aware size cap (inputs off by default, the 21 months as a check
  only); then fidelity: the FTMO demo's symbol margin for XAUUSD/AUDCAD against the fitted 1:50 / 1:100.
- **AurumFunded:** j12 (FTMO funded preset), j13 (FundedNext Stellar Instant), j14 (Instant Funding PRO) all judged
  PASS at step 16 (tester keeps 0.67-0.84 of the model's log growth, lesson 4 band). Open follow-ups needing no
  tester time: j12-vs-j3 deal lists on the three extra day-stop days; j14's floating-stop days to price the 1.7%
  stop; the EA never logs its trailing-stop floor (log line proposed). Prop routes and presets: see archive.
- **Demo (step 17):** AurumFunded 1.03 with both legs on, FTMO demo, attached 2026-10-17; first trades when gold
  opens Monday. The monitor reports in `docs/demo_log.md`; fidelity pairs demo fills with a tester run weekly.
  Watch: gold entries must come on the same days as the tester's (the `InpGoldMaxSpread=0.30` cap).
- **Tester queue** (`docs/autopilot/queue.json`): j1-j15 done or judged, nothing queued; the next job comes from
  the round-5 model work above. Judgements live in each `backtests/<folder>/summary.md`.
- **Research pipeline:** simple-rule scans on the histdata symbols are exhausted (all four `edge_scan.py` families
  run; the record is `docs/trials.jsonl` and the Scans note in the archive) — a new scan needs new data and goes
  into `docs/autopilot/scan_requests.json`. Ideas: Osler round-number levels rejected at steps 5-7 (new rejected
  family); ideas 1, 3, 4 of `docs/ideas/2026-10-17.md` are **unverified** (abstract only) and go last; the
  2026-10-18 batch waits for the orchestrator's pick. `pdf_text.py` retries mirrors before marking a paper
  unreadable.

## Waiting on the owner

- Prop-firm facts: FundedNext Stellar Instant consistency rule; Instant Funding PRO account-drawdown % and EA
  policy; FTMO 1-Step maximum loss (details in the archive).
- Commit 031f5b6 carried 18 staged renames into `mql5/Experts/_archive/` (.ex5 rule broken): keep or revert.
- Anything in `docs/autopilot/approvals.json` with status "pending".
