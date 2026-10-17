window.AURUM = {
 "generated": "2026-10-17T05:26",
 "pipeline": {
  "about": "The 20 steps every idea goes through, in order; an idea stops at the first failed gate. 'agent' is the role file in .claude/agents/, 'orchestrator' is the main Opus session. The dashboard (python tools/dashboard.py) reads this file.",
  "phases": {
   "A": "Measure",
   "B": "Ideas and data",
   "C": "Prototype",
   "D": "Proof",
   "E": "Fit with the book",
   "F": "Build",
   "G": "Live test",
   "H": "Go live"
  },
  "steps": [
   {
    "n": 1,
    "phase": "A",
    "name": "Set the measure",
    "detail": "P(5x in a month) = N(N^-1(0.2) + Sharpe sqrt(1/12)) for Hydra; first-payout time and failure rate for Funded",
    "model": "opus",
    "agent": "orchestrator",
    "gate": null
   },
   {
    "n": 2,
    "phase": "B",
    "name": "Find ideas",
    "detail": "Papers and concepts, checked against the rejected list in docs/HANDOFF.md and docs/candidates.json; up to 5 a week",
    "model": "haiku searches, opus picks",
    "agent": "researcher",
    "gate": null
   },
   {
    "n": 3,
    "phase": "B",
    "name": "Read the full paper",
    "detail": "Definitions, tables, costs, sample; no testing from an abstract",
    "model": "opus",
    "agent": "orchestrator",
    "gate": null
   },
   {
    "n": 4,
    "phase": "B",
    "name": "Get the data",
    "detail": "tools/ downloaders into marketdata/",
    "model": "haiku",
    "agent": "researcher",
    "gate": null
   },
   {
    "n": 5,
    "phase": "C",
    "name": "Check the data",
    "detail": "Time zone, 23:00-01:00 rollover quotes, gaps, duplicates",
    "model": "sonnet",
    "agent": "quant-coder",
    "gate": null
   },
   {
    "n": 6,
    "phase": "C",
    "name": "Prototype",
    "detail": "research/<idea>.py; for ML: replicate the paper, purge and embargo, several seeds, simple baselines",
    "model": "sonnet",
    "agent": "quant-coder",
    "gate": null
   },
   {
    "n": 7,
    "phase": "C",
    "name": "Real costs, then 1.5-2x",
    "detail": "Measured spreads and fills; writes marketdata/candidates/<id>.csv and <id>_stress.csv",
    "model": "sonnet",
    "agent": "quant-coder",
    "gate": "costs"
   },
   {
    "n": 8,
    "phase": "D",
    "name": "Out of sample",
    "detail": "Settings fitted to 2017, judged from 2018; shifted windows, every year, random-entry baseline",
    "model": "opus",
    "agent": "reviewer",
    "gate": "halves"
   },
   {
    "n": 9,
    "phase": "D",
    "name": "Deflated Sharpe",
    "detail": "Every trial counted (docs/trials.jsonl + 47 before the log)",
    "model": "opus",
    "agent": "reviewer",
    "gate": "dsr"
   },
   {
    "n": 10,
    "phase": "E",
    "name": "Correlation and book Sharpe",
    "detail": "Against the Hydra book and each leg; weight fitted to 2017",
    "model": "opus",
    "agent": "reviewer",
    "gate": "corr"
   },
   {
    "n": 11,
    "phase": "E",
    "name": "Goal simulation",
    "detail": "Hydra's P(5x) and the prop simulators (tools/backtest_prop.py, prop_candidates.py)",
    "model": "sonnet runs, opus judges",
    "agent": "quant-coder",
    "gate": "goal"
   },
   {
    "n": 12,
    "phase": "F",
    "name": "Standalone MQL5 EA",
    "detail": "Broker stops, unique magic, state that survives a restart, server-clock check",
    "model": "sonnet",
    "agent": "quant-coder",
    "gate": null
   },
   {
    "n": 13,
    "phase": "F",
    "name": "Compile 0/0",
    "detail": "metaeditor64 /compile: 0 errors, 0 warnings",
    "model": "sonnet",
    "agent": "quant-coder",
    "gate": null
   },
   {
    "n": 14,
    "phase": "F",
    "name": "Merge into Hydra and Funded",
    "detail": "Off by default, through SizeMult() and the prop guards",
    "model": "sonnet, opus reviews",
    "agent": "quant-coder",
    "gate": null
   },
   {
    "n": 15,
    "phase": "G",
    "name": "Strategy Tester",
    "detail": "Real ticks from 2024-01 on FTMO's data; must match the Python figures",
    "model": "sonnet runs, opus judges gaps",
    "agent": "tester-operator",
    "gate": null
   },
   {
    "n": 16,
    "phase": "G",
    "name": "Leg on vs off in the main EA",
    "detail": "Return per drawdown must rise; no day stop in Funded",
    "model": "sonnet runs, opus decides",
    "agent": "tester-operator",
    "gate": null
   },
   {
    "n": 17,
    "phase": "G",
    "name": "Demo forward test 2-4 weeks",
    "detail": "FTMO demo terminal; daily check-ins in docs/demo_log.md, weekly review",
    "model": "haiku daily, opus weekly",
    "agent": "monitor",
    "gate": null
   },
   {
    "n": 18,
    "phase": "H",
    "name": "Recheck firm rules, pick preset",
    "detail": "The firm's own pages on the day",
    "model": "opus",
    "agent": "orchestrator",
    "gate": null
   },
   {
    "n": 19,
    "phase": "H",
    "name": "Buy or go live",
    "detail": "The owner only",
    "model": "owner",
    "agent": "owner",
    "gate": null
   },
   {
    "n": 20,
    "phase": "H",
    "name": "Monitor, handoff, push",
    "detail": "Daily check-ins; docs/HANDOFF.md; commit and push",
    "model": "haiku monitors, sonnet writes",
    "agent": "monitor",
    "gate": null
   }
  ]
 },
 "ledger": {
  "about": "The candidate ledger: one entry per idea, its pipeline step (docs/pipeline.json) and status. tools/gates.py writes the 'gates' field; the orchestrator writes the rest. Status: idea, testing, tester, demo, live, rejected.",
  "candidates": [
   {
    "id": "breakout",
    "name": "USD/JPY London breakout",
    "source": "retail London-breakout concept, own test; research/london_breakout.py, research/breakout_ticks.py",
    "status": "tester",
    "step": 16,
    "ea": "mql5/Experts/AurumBreakout/ (standalone), AurumFunded 1.03 and AurumHydra 1.33 off by default (InpBreakRiskPct)",
    "summary": "Range 01:00-09:00 server, each side once a day on a break 10:00-18:00, stop at the far side, flat at 18:00. Sharpe 1.18 to 2017 / 0.83 from 2018 at the measured 1.2 bp, 0.59 at 1.5 bp; |corr| with Hydra <= 0.03.",
    "stress_sharpe": 0.59,
    "expected_tester": {
     "symbol": "USDJPY",
     "from": "2024-01-01",
     "to": "2026-10-01",
     "deposit": 10000,
     "trades": 777,
     "win_rate": 47,
     "profit_factor": 1.14,
     "return_pct": 8.6,
     "eq_dd_max_pct": 5.0
    },
    "notes": "The gates' own 2017-fitted weight (k=0.5 of Hydra's volatility) adds nothing from 2018 (3.37 -> 3.36): the leg was stronger to 2017 (1.18) than after (0.83), so the fit over-weights it. At AurumFunded's tested size (weight 1 = 0.125% risk) Hydra 3.37 -> 3.43. HANDOFF's 0.5% risk for Hydra (weight 4) gives about 3.46. The tester run decides whether it stays.",
    "gates": {
     "id": "breakout",
     "when": "2026-10-17T01:19:58",
     "verdict": "PASS",
     "gates": [
      {
       "gate": "halves",
       "pass": true,
       "figure": "1.18 / 0.83",
       "rule": ">= 0.5 to 2017 and from 2018"
      },
      {
       "gate": "costs",
       "pass": true,
       "figure": "0.59",
       "rule": ">= 0.3 at 1.5x cost"
      },
      {
       "gate": "dsr",
       "pass": true,
       "figure": "0.969 (N=47, luck bar 0.55)",
       "rule": ">= 0.9"
      },
      {
       "gate": "corr",
       "pass": true,
       "figure": "book -0.00, max leg hold -0.03",
       "rule": "|book| <= 0.2, |leg| <= 0.3"
      },
      {
       "gate": "goal",
       "pass": true,
       "figure": "Hydra 2018+ 3.37 -> 3.43 at weight 1; P(5x) 55.2% -> 55.9%",
       "rule": "Sharpe gain >= 0.03, weight fixed by --weight"
      }
     ],
     "weight": 1.0,
     "p5x": [
      0.5522581158607921,
      0.5588167045143293
     ],
     "dry_run": true,
     "note": "seeded from a dry run (no trial logged: both legs are inside the 47 counted before the log)"
    },
    "tester": [
     {
      "run": "backtests/2026-10-17_0118_AurumBreakout_USDJPY",
      "symbol": "USDJPY",
      "trades": 771,
      "win_rate": 47.73,
      "profit_factor": 1.16,
      "return_pct": 9.96,
      "eq_dd_max_pct": 4.02,
      "verdict": "matches the Python figures; step 15 passed"
     }
    ]
   },
   {
    "id": "noise",
    "name": "Noise-area intraday momentum, S&P 500 and Nasdaq",
    "source": "Zarattini, Aziz, Barbon 2025 (read in full); research/noise_area_index.py",
    "status": "tester",
    "step": 16,
    "ea": "mql5/Experts/AurumNoise/ (standalone), AurumFunded 1.03 and AurumHydra 1.33 off by default (InpNoiseMult)",
    "summary": "Bands of the average move from the 9:30 open, checked each half hour from 10:00 New York, trailing stop, flat at 16:00, 2% daily vol. Sharpe 0.88 at 0.75 bp (0.61 / 1.08), 0.57 at 1.5 bp; corr with Hydra -0.02.",
    "stress_sharpe": 0.57,
    "expected_tester": [
     {
      "symbol": "US500.cash",
      "from": "2024-01-01",
      "to": "2026-10-01",
      "deposit": 10000,
      "trades": 451,
      "return_pct": 1.3,
      "eq_dd_max_pct": 28.6
     },
     {
      "symbol": "US100.cash",
      "from": "2024-01-01",
      "to": "2026-10-01",
      "deposit": 10000,
      "trades": 701,
      "return_pct": 44.7,
      "eq_dd_max_pct": 18.5
     }
    ],
    "notes": "Weight fitted to 2017: 0.61 (EA uses 0.55, 0.275 per index). Hydra from 2018 3.37 -> 3.56.",
    "gates": {
     "id": "noise",
     "when": "2026-10-17T01:19:58",
     "verdict": "PASS",
     "gates": [
      {
       "gate": "halves",
       "pass": true,
       "figure": "0.64 / 1.10",
       "rule": ">= 0.5 to 2017 and from 2018"
      },
      {
       "gate": "costs",
       "pass": true,
       "figure": "0.57",
       "rule": ">= 0.3 at 1.5x cost"
      },
      {
       "gate": "dsr",
       "pass": true,
       "figure": "0.938 (N=47, luck bar 0.55)",
       "rule": ">= 0.9"
      },
      {
       "gate": "corr",
       "pass": true,
       "figure": "book -0.02, max leg cross -0.03",
       "rule": "|book| <= 0.2, |leg| <= 0.3"
      },
      {
       "gate": "goal",
       "pass": true,
       "figure": "Hydra 2018+ 3.37 -> 3.56 at weight 0.609; P(5x) 55.2% -> 57.4%",
       "rule": "Sharpe gain >= 0.03, weight fitted to 2017"
      }
     ],
     "weight": 0.6088017801888469,
     "p5x": [
      0.5522581158607921,
      0.5736192480341962
     ],
     "dry_run": true,
     "note": "seeded from a dry run (no trial logged: both legs are inside the 47 counted before the log)"
    },
    "tester": [
     {
      "run": "backtests/2026-10-17_0457_AurumNoise_US500",
      "symbol": "US500.cash",
      "trades": 452,
      "win_rate": 39.6,
      "profit_factor": 1.0,
      "return_pct": -0.68,
      "eq_dd_max_pct": 26.09,
      "verdict": "matches the Python figures (return 2.0 points under, drawdown 2.5 under, trades 452 vs 451); the S&P half was already weak in 2024-26 in Python and is flat here (2024 +17%, 2025 and 2026 losing)"
     },
     {
      "run": "backtests/2026-10-17_0500_AurumNoise_US100",
      "symbol": "US100.cash",
      "trades": 697,
      "win_rate": 40.75,
      "profit_factor": 1.18,
      "return_pct": 39.93,
      "eq_dd_max_pct": 16.41,
      "verdict": "matches the Python figures (return 4.8 points under, drawdown 2.1 under, trades 697 vs 701; every year positive); step 15 passed for both indices, step 16 = j3 and j4 legs on vs off"
     }
    ]
   }
  ],
  "rejected": [
   {
    "family": "Gold intraday fades",
    "examples": "Asian dip buy, shock fade, LBMA auction dip, burst fade, Shanghai benchmark windows, London bias, weekend gaps",
    "why": "below cost or gone after 2017"
   },
   {
    "family": "Breakouts other than USD/JPY",
    "examples": "channel breakout, other dollar pairs, yen crosses, Nikkei, gold, 5-minute ORB on indices",
    "why": "too costly outside USD/JPY, or adds nothing next to the noise leg"
   },
   {
    "family": "Machine learning and RL",
    "examples": "deep and RL replications, daily ML, tick ML scalp, Deep Momentum Networks, deep Q-learning on 20 futures",
    "why": "Sharpe <= 0.5 or seed-dependent; nothing after costs"
   },
   {
    "family": "Intraday momentum variants",
    "examples": "market intraday momentum (all forms), Bitcoin intraday, oil on EIA days, VWAP trend, shorter windows",
    "why": "fails one half or dies on cost"
   },
   {
    "family": "Calendar and announcement drifts",
    "examples": "pre-FOMC, FOMC cycle, overnight drift, turn of month, post-payroll and FOMC drift, holidays elsewhere",
    "why": "no edge after 2017 or below cost"
   },
   {
    "family": "Relative-value fades",
    "examples": "silver vs gold, AUD/NZD, GBP/EUR, Nasdaq/S&P pairs, FX fixing reversals, 15-minute shocks",
    "why": "real reversion, smaller than the spread"
   },
   {
    "family": "Daily and slow strategies",
    "examples": "time-series momentum on futures and crypto, VIX filters, reversal in stocks, gold/silver ratio",
    "why": "Sharpe 0.5-0.7 at best, correlated or costly"
   },
   {
    "family": "Re-weighting the book",
    "examples": "volatility-managed sizing, exponentiated-gradient weights, re-fitted weights, quarter-end size-up",
    "why": "lowers Sharpe out of sample"
   },
   {
    "family": "Scalps and HFT",
    "examples": "HFT, scalp concepts, night scalper on 11 pairs",
    "why": "1-2 bp before cost"
   }
  ]
 },
 "gates": {
  "breakout": {
   "id": "breakout",
   "when": "2026-10-17T01:19:58",
   "verdict": "PASS",
   "gates": [
    {
     "gate": "halves",
     "pass": true,
     "figure": "1.18 / 0.83",
     "rule": ">= 0.5 to 2017 and from 2018"
    },
    {
     "gate": "costs",
     "pass": true,
     "figure": "0.59",
     "rule": ">= 0.3 at 1.5x cost"
    },
    {
     "gate": "dsr",
     "pass": true,
     "figure": "0.969 (N=47, luck bar 0.55)",
     "rule": ">= 0.9"
    },
    {
     "gate": "corr",
     "pass": true,
     "figure": "book -0.00, max leg hold -0.03",
     "rule": "|book| <= 0.2, |leg| <= 0.3"
    },
    {
     "gate": "goal",
     "pass": true,
     "figure": "Hydra 2018+ 3.37 -> 3.43 at weight 1; P(5x) 55.2% -> 55.9%",
     "rule": "Sharpe gain >= 0.03, weight fixed by --weight"
    }
   ],
   "weight": 1.0,
   "p5x": [
    0.5522581158607921,
    0.5588167045143293
   ],
   "dry_run": true,
   "note": "seeded from a dry run (no trial logged: both legs are inside the 47 counted before the log)"
  },
  "noise": {
   "id": "noise",
   "when": "2026-10-17T01:19:58",
   "verdict": "PASS",
   "gates": [
    {
     "gate": "halves",
     "pass": true,
     "figure": "0.64 / 1.10",
     "rule": ">= 0.5 to 2017 and from 2018"
    },
    {
     "gate": "costs",
     "pass": true,
     "figure": "0.57",
     "rule": ">= 0.3 at 1.5x cost"
    },
    {
     "gate": "dsr",
     "pass": true,
     "figure": "0.938 (N=47, luck bar 0.55)",
     "rule": ">= 0.9"
    },
    {
     "gate": "corr",
     "pass": true,
     "figure": "book -0.02, max leg cross -0.03",
     "rule": "|book| <= 0.2, |leg| <= 0.3"
    },
    {
     "gate": "goal",
     "pass": true,
     "figure": "Hydra 2018+ 3.37 -> 3.56 at weight 0.609; P(5x) 55.2% -> 57.4%",
     "rule": "Sharpe gain >= 0.03, weight fitted to 2017"
    }
   ],
   "weight": 0.6088017801888469,
   "p5x": [
    0.5522581158607921,
    0.5736192480341962
   ],
   "dry_run": true,
   "note": "seeded from a dry run (no trial logged: both legs are inside the 47 counted before the log)"
  }
 },
 "trials": 0,
 "props": {
  "about": "Prop routes for AurumFunded, from docs/HANDOFF.md (simulators in tools/prop_*.py, 70% of the back-tested edge). Firm rules were read on the firms' own pages on 2026-10-14/15; check again before buying. The dashboard reads this file.",
  "chosen": "FTMO 2-Step Challenge, Swing account",
  "routes": [
   {
    "route": "FundedNext Stellar Instant",
    "median_months": 1.4,
    "alt_months": 4.3,
    "alt_if": "if it has a 40% best-day consistency rule",
    "preset": "AurumFunded_FundedNext_instant.set",
    "rules": "no challenge, no daily limit, 6% trailing max loss, 14-day payout cycle, 70-80% share, EA add-on",
    "open": "confirm the consistency rule with FundedNext"
   },
   {
    "route": "Instant Funding PRO",
    "median_months": 2.5,
    "alt_months": 2.0,
    "alt_if": "with DP fast sizing FAST_IF",
    "preset": "AurumFunded 1.03 lock preset",
    "rules": "no target, no daily limit, no consistency rule, 10% max loss tightening to 5% once +5%, first payout after 14 days",
    "open": "Account Drawdown %, EA policy, server clock"
   },
   {
    "route": "FTMO 1-Step",
    "median_months": 7.8,
    "preset": "AurumFunded FTMO 1-Step preset",
    "rules": "one phase",
    "open": "maximum loss: 10% or 6%"
   },
   {
    "route": "FTMO 2-Step (chosen)",
    "median_months": 9.6,
    "preset": "AurumFunded_FTMO_phase1/phase2/funded.set",
    "rules": "10% then 5% target, 5% daily on equity from midnight CE(S)T, 10% static max, 4 trading days, no time limit, 1:30",
    "open": "none"
   }
  ],
  "guard": {
   "day_stop_pct": 3,
   "final_stop_pct": 8.5,
   "shrink_within_pct": 6.5,
   "firm_daily_pct": 5,
   "firm_max_pct": 10
  },
  "tester": [
   {
    "run": "backtests/2026-10-15_funded_phase1",
    "what": "phase 1 passed on 2024-10-25, 10 months after start"
   },
   {
    "run": "backtests/2026-10-15_funded_account",
    "what": "funded preset: +110% in 34 months, max equity DD 4.08%, worst day -1.64%"
   }
  ]
 },
 "runs": [
  {
   "name": "2026-10-17_0505_AurumFunded_funded_off",
   "state": "no report (run killed or still going)"
  },
  {
   "name": "2026-10-17_0500_AurumNoise_US100",
   "job": {
    "Expert": "AurumNoise",
    "Symbol": "US100.cash",
    "From": "2024.01.01",
    "To": "2026.10.17",
    "Deposit": 10000,
    "Leverage": 100,
    "Period": "M1",
    "Set": "",
    "Started": "2026-10-17T05:00:33.2372167+02:00"
   },
   "summary": "# AurumNoise US100.cash, M1, 2024-01-01 to 2026-10-17 (job j2)\n\nReal ticks (99% history quality, 185.2M ticks), deposit 10,000, leverage 1:100, preset AurumNoise_US100.set.\n\n| Figure | Tester | Expected (README test 2) | Gap |\n|---|---|---|---|\n| Net profit | +3,992.54 (+39.93%) | +44.7% | -4.8 points |\n| Max equity drawdown | 2,329.02 (16.41%) | 18.5% | 2.1 points less |\n| Max balance drawdown | 2,186.45 (15.52%) | n/a | |\n| Trades | 697 | n/a | |\n| Win rate | 40.75% (284 won) | n/a | |\n| Profit factor | 1.18 (gross +26,438.03 / -22,445.49) | n/a | |\n| Sharpe / recovery | 3.23 / 1.71 | n/a | |\n| Worst day | -2.92% (2025-04-07) | n/a | |\n\nBy year (net): 2024 +2,456.15, 2025 +763.12, 2026 +773.27.\nMonths positive: 18 of 34. Worst months: 2026-01 -1,214.02, 2025-09 -1,000.53, 2025-07 -430.10. Best: 2025-10 +1,077.31, 2024-12 +954.45.\n\nLog: no \"not found\", \"cannot\", \"failed\" or margin errors in the collected lines. Final balance 13,992.54.\n\nReading for the orchestrator (no judgement made here): close to the expectation, slightly less profit and\nslightly less drawdown. All three years are positive.\n",
   "state": "done",
   "result": {
    "expert": "AurumNoise",
    "symbol": "US100.cash",
    "period": "M1 (2024.01.01 - 2026.10.17)",
    "deposit": 10000.0,
    "net": 3992.54,
    "gross_profit": 26438.03,
    "gross_loss": -22445.49,
    "profit_factor": 1.18,
    "recovery": 1.71,
    "sharpe": 3.23,
    "trades": 697.0,
    "won": "284 (40.75%)",
    "eq_dd_max": "2 329.02 (16.41%)",
    "eq_dd_rel": "16.41% (2 329.02)",
    "bal_dd_max": "2 186.45 (15.52%)",
    "ticks": 185213154.0,
    "history_quality": "99% real ticks",
    "win_rate": 40.75,
    "eq_dd_max_pct": 16.41,
    "bal_dd_max_pct": 15.52,
    "deals": 1395,
    "curve": [
     [
      "2024-01-02",
      10050.29
     ],
     [
      "2024-01-03",
      10025.04
     ],
     [
      "2024-01-05",
      9903.78
     ],
     [
      "2024-01-08",
      10140.52
     ],
     [
      "2024-01-10",
      10150.04
     ],
     [
      "2024-01-11",
      10113.34
     ],
     [
      "2024-01-17",
      10025.61
     ],
     [
      "2024-01-18",
      9960.62
     ],
     [
      "2024-01-19",
      10139.94
     ],
     [
      "2024-01-24",
      10106.44
     ],
     [
      "2024-01-29",
      10109.36
     ],
     [
      "2024-01-30",
      10049.13
     ],
     [
      "2024-01-31",
      10179.02
     ],
     [
      "2024-02-01",
      10125.5
     ],
     [
      "2024-02-02",
      10283.96
     ],
     [
      "2024-02-05",
      10281.42
     ],
     [
      "2024-02-06",
      10196.44
     ],
     [
      "2024-02-07",
      10149.26
     ],
     [
      "2024-02-09",
      10266.26
     ],
     [
      "2024-02-12",
      10245.02
     ],
     [
      "2024-02-15",
      10243.97
     ],
     [
      "2024-02-16",
      10134.77
     ],
     [
      "2024-02-20",
      10097.37
     ],
     [
      "2024-02-21",
      10084.74
     ],
     [
      "2024-02-22",
      10146.62
     ],
     [
      "2024-03-01",
      10302.97
     ],
     [
      "2024-03-05",
      10408.93
     ],
     [
      "2024-03-07",
      10466.45
     ],
     [
      "2024-03-08",
      10435.07
     ],
     [
      "2024-03-12",
      10500.48
     ],
     [
      "2024-03-13",
      10500.48
     ],
     [
      "2024-03-14",
      10334.23
     ],
     [
      "2024-03-15",
      10404.63
     ],
     [
      "2024-03-18",
      10387.95
     ],
     [
      "2024-03-27",
      10404.72
     ],
     [
      "2024-04-01",
      10155.25
     ],
     [
      "2024-04-02",
      10119.85
     ],
     [
      "2024-04-03",
      10089.92
     ],
     [
      "2024-04-04",
      10328.65
     ],
     [
      "2024-04-05",
      10441.28
     ],
     [
      "2024-04-09",
      10365.76
     ],
     [
      "2024-04-11",
      10471.94
     ],
     [
      "2024-04-12",
      10409.0
     ],
     [
      "2024-04-15",
      10500.13
     ],
     [
      "2024-04-17",
      10631.87
     ],
     [
      "2024-04-19",
      10859.39
     ],
     [
      "2024-04-23",
      10963.91
     ],
     [
      "2024-04-26",
      10967.2
     ],
     [
      "2024-04-30",
      10972.49
     ],
     [
      "2024-05-01",
      10938.82
     ],
     [
      "2024-05-03",
      10862.48
     ],
     [
      "2024-05-10",
      10759.54
     ],
     [
      "2024-05-14",
      10720.59
     ],
     [
      "2024-05-15",
      10856.66
     ],
     [
      "2024-05-16",
      10852.44
     ],
     [
      "2024-05-17",
      10795.68
     ],
     [
      "2024-05-20",
      10806.67
     ],
     [
      "2024-05-22",
      10739.3
     ],
     [
      "2024-05-23",
      10771.33
     ],
     [
      "2024-05-24",
      10846.57
     ],
     [
      "2024-05-27",
      10846.57
     ],
     [
      "2024-05-28",
      10813.23
     ],
     [
      "2024-05-30",
      10822.66
     ],
     [
      "2024-05-31",
      10715.54
     ],
     [
      "2024-06-03",
      10667.15
     ],
     [
      "2024-06-05",
      10853.56
     ],
     [
      "2024-06-12",
      10870.08
     ],
     [
      "2024-06-14",
      10852.84
     ],
     [
      "2024-06-17",
      10997.4
     ],
     [
      "2024-06-20",
      10950.33
     ],
     [
      "2024-06-21",
      10865.96
     ],
     [
      "2024-06-24",
      10857.18
     ],
     [
      "2024-06-25",
      10761.77
     ],
     [
      "2024-06-27",
      10710.92
     ],
     [
      "2024-06-28",
      10629.47
     ],
     [
      "2024-07-01",
      10551.8
     ],
     [
      "2024-07-02",
      10703.31
     ],
     [
      "2024-07-03",
      10703.31
     ],
     [
      "2024-07-04",
      10813.79
     ],
     [
      "2024-07-05",
      10954.04
     ],
     [
      "2024-07-10",
      10981.6
     ],
     [
      "2024-07-11",
      11304.26
     ],
     [
      "2024-07-12",
      11293.44
     ],
     [
      "2024-07-15",
      11270.76
     ],
     [
      "2024-07-16",
      11206.56
     ],
     [
      "2024-07-17",
      11366.28
     ],
     [
      "2024-07-18",
      11238.42
     ],
     [
      "2024-07-19",
      11113.84
     ],
     [
      "2024-07-24",
      11378.55
     ],
     [
      "2024-07-25",
      11241.0
     ],
     [
      "2024-07-29",
      11189.79
     ],
     [
      "2024-07-30",
      11314.3
     ],
     [
      "2024-07-31",
      11221.24
     ],
     [
      "2024-08-01",
      11298.63
     ],
     [
      "2024-08-02",
      11235.62
     ],
     [
      "2024-08-06",
      11047.96
     ],
     [
      "2024-08-08",
      11076.82
     ],
     [
      "2024-08-13",
      11090.26
     ],
     [
      "2024-08-15",
      11108.0
     ],
     [
      "2024-08-22",
      11117.88
     ],
     [
      "2024-08-23",
      11004.51
     ],
     [
      "2024-08-26",
      10976.46
     ],
     [
      "2024-08-28",
      10977.73
     ],
     [
      "2024-08-29",
      10951.5
     ],
     [
      "2024-09-03",
      11267.34
     ],
     [
      "2024-09-05",
      11206.1
     ],
     [
      "2024-09-06",
      11490.9
     ],
     [
      "2024-09-11",
      11488.06
     ],
     [
      "2024-09-12",
      11476.12
     ],
     [
      "2024-09-20",
      11425.97
     ],
     [
      "2024-09-25",
      11420.12
     ],
     [
      "2024-09-27",
      11293.99
     ],
     [
      "2024-10-01",
      11361.8
     ],
     [
      "2024-10-07",
      11323.05
     ],
     [
      "2024-10-08",
      11387.91
     ],
     [
      "2024-10-09",
      11400.12
     ],
     [
      "2024-10-14",
      11356.83
     ],
     [
      "2024-10-15",
      11586.2
     ],
     [
      "2024-10-16",
      11450.57
     ],
     [
      "2024-10-23",
      11435.05
     ],
     [
      "2024-10-25",
      11317.67
     ],
     [
      "2024-10-29",
      11371.53
     ],
     [
      "2024-10-30",
      11341.53
     ],
     [
      "2024-10-31",
      11511.63
     ],
     [
      "2024-11-01",
      11350.74
     ],
     [
      "2024-11-05",
      11396.46
     ],
     [
      "2024-11-06",
      11416.97
     ],
     [
      "2024-11-07",
      11512.6
     ],
     [
      "2024-11-11",
      11497.92
     ],
     [
      "2024-11-12",
      11451.59
     ],
     [
      "2024-11-15",
      11620.81
     ],
     [
      "2024-11-18",
      11627.83
     ],
     [
      "2024-11-19",
      11597.72
     ],
     [
      "2024-11-20",
      11510.28
     ],
     [
      "2024-11-21",
      11468.15
     ],
     [
      "2024-11-27",
      11501.7
     ],
     [
      "2024-11-29",
      11501.7
     ],
     [
      "2024-12-02",
      11653.46
     ],
     [
      "2024-12-06",
      11703.87
     ],
     [
      "2024-12-09",
      11706.33
     ],
     [
      "2024-12-11",
      11834.13
     ],
     [
      "2024-12-13",
      11740.17
     ],
     [
      "2024-12-16",
      11902.77
     ],
     [
      "2024-12-17",
      11838.02
     ],
     [
      "2024-12-18",
      12480.27
     ],
     [
      "2024-12-20",
      12568.48
     ],
     [
      "2024-12-23",
      12579.36
     ],
     [
      "2024-12-24",
      12579.36
     ],
     [
      "2024-12-26",
      12696.19
     ],
     [
      "2024-12-27",
      12633.58
     ],
     [
      "2024-12-30",
      12563.8
     ],
     [
      "2024-12-31",
      12456.15
     ],
     [
      "2025-01-02",
      12415.41
     ],
     [
      "2025-01-03",
      12420.78
     ],
     [
      "2025-01-06",
      12449.72
     ],
     [
      "2025-01-07",
      12617.18
     ],
     [
      "2025-01-10",
      12610.05
     ],
     [
      "2025-01-15",
      12556.39
     ],
     [
      "2025-01-22",
      12557.1
     ],
     [
      "2025-01-24",
      12518.64
     ],
     [
      "2025-01-28",
      12606.03
     ],
     [
      "2025-01-29",
      12494.9
     ],
     [
      "2025-01-31",
      12450.58
     ],
     [
      "2025-02-04",
      12542.19
     ],
     [
      "2025-02-07",
      12688.96
     ],
     [
      "2025-02-13",
      12671.03
     ],
     [
      "2025-02-20",
      12537.83
     ],
     [
      "2025-02-21",
      13093.2
     ],
     [
      "2025-02-24",
      13059.97
     ],
     [
      "2025-02-25",
      13091.57
     ],
     [
      "2025-02-26",
      12913.61
     ],
     [
      "2025-02-27",
      12945.97
     ],
     [
      "2025-02-28",
      12948.09
     ],
     [
      "2025-03-03",
      13158.79
     ],
     [
      "2025-03-04",
      13031.16
     ],
     [
      "2025-03-05",
      13030.6
     ],
     [
      "2025-03-06",
      13075.25
     ],
     [
      "2025-03-07",
      13009.54
     ],
     [
      "2025-03-10",
      13314.49
     ],
     [
      "2025-03-13",
      13248.63
     ],
     [
      "2025-03-14",
      13199.49
     ],
     [
      "2025-03-17",
      13211.57
     ],
     [
      "2025-03-18",
      13160.91
     ],
     [
      "2025-03-19",
      13130.81
     ],
     [
      "2025-03-21",
      13101.62
     ],
     [
      "2025-03-26",
      13268.61
     ],
     [
      "2025-03-28",
      13483.03
     ],
     [
      "2025-03-31",
      13437.35
     ],
     [
      "2025-04-01",
      13427.14
     ],
     [
      "2025-04-02",
      13291.52
     ],
     [
      "2025-04-03",
      13211.85
     ],
     [
      "2025-04-04",
      13477.49
     ],
     [
      "2025-04-07",
      13084.35
     ],
     [
      "2025-04-08",
      13035.73
     ],
     [
      "2025-04-09",
      13945.93
     ],
     [
      "2025-04-10",
      14015.09
     ],
     [
      "2025-04-11",
      13982.48
     ],
     [
      "2025-04-21",
      14044.01
     ],
     [
      "2025-04-22",
      14014.19
     ],
     [
      "2025-04-24",
      14065.87
     ],
     [
      "2025-04-28",
      14055.88
     ],
     [
      "2025-04-30",
      13980.77
     ],
     [
      "2025-05-08",
      13953.03
     ],
     [
      "2025-05-13",
      14090.32
     ],
     [
      "2025-05-21",
      14035.24
     ],
     [
      "2025-05-22",
      13874.16
     ],
     [
      "2025-05-27",
      13932.37
     ],
     [
      "2025-05-30",
      13709.09
     ],
     [
      "2025-06-02",
      13731.35
     ],
     [
      "2025-06-03",
      13755.4
     ],
     [
      "2025-06-05",
      13736.9
     ],
     [
      "2025-06-16",
      13760.52
     ],
     [
      "2025-06-17",
      13685.27
     ],
     [
      "2025-06-18",
      13647.2
     ],
     [
      "2025-06-19",
      13547.76
     ],
     [
      "2025-06-20",
      13353.4
     ],
     [
      "2025-06-23",
      13465.09
     ],
     [
      "2025-06-24",
      13464.19
     ],
     [
      "2025-06-26",
      13453.64
     ],
     [
      "2025-06-27",
      13417.94
     ],
     [
      "2025-07-01",
      13363.17
     ],
     [
      "2025-07-02",
      13436.21
     ],
     [
      "2025-07-03",
      13436.21
     ],
     [
      "2025-07-04",
      13481.82
     ],
     [
      "2025-07-09",
      13261.21
     ],
     [
      "2025-07-10",
      13200.37
     ],
     [
      "2025-07-14",
      13225.71
     ],
     [
      "2025-07-16",
      13128.24
     ],
     [
      "2025-07-17",
      13353.53
     ],
     [
      "2025-07-21",
      13273.05
     ],
     [
      "2025-07-22",
      13053.22
     ],
     [
      "2025-07-25",
      12996.13
     ],
     [
      "2025-07-31",
      12987.84
     ],
     [
      "2025-08-01",
      12669.09
     ],
     [
      "2025-08-04",
      12743.14
     ],
     [
      "2025-08-05",
      12692.45
     ],
     [
      "2025-08-06",
      12866.83
     ],
     [
      "2025-08-08",
      12900.19
     ],
     [
      "2025-08-12",
      13014.53
     ],
     [
      "2025-08-15",
      12880.18
     ],
     [
      "2025-08-19",
      13107.29
     ],
     [
      "2025-08-20",
      12940.3
     ],
     [
      "2025-08-22",
      12956.77
     ],
     [
      "2025-08-28",
      12917.89
     ],
     [
      "2025-08-29",
      12979.94
     ],
     [
      "2025-09-04",
      13039.85
     ],
     [
      "2025-09-08",
      13060.55
     ],
     [
      "2025-09-15",
      13022.0
     ],
     [
      "2025-09-17",
      12743.24
     ],
     [
      "2025-09-18",
      12558.94
     ],
     [
      "2025-09-22",
      12611.33
     ],
     [
      "2025-09-23",
      12650.09
     ],
     [
      "2025-09-24",
      12487.99
     ],
     [
      "2025-09-25",
      12138.41
     ],
     [
      "2025-09-26",
      12135.23
     ],
     [
      "2025-09-29",
      11979.41
     ],
     [
      "2025-10-01",
      12031.52
     ],
     [
      "2025-10-03",
      11914.64
     ],
     [
      "2025-10-07",
      11963.76
     ],
     [
      "2025-10-08",
      12230.93
     ],
     [
      "2025-10-09",
      12136.71
     ],
     [
      "2025-10-10",
      13512.35
     ],
     [
      "2025-10-13",
      13453.65
     ],
     [
      "2025-10-14",
      13324.72
     ],
     [
      "2025-10-15",
      13281.46
     ],
     [
      "2025-10-16",
      13114.37
     ],
     [
      "2025-10-17",
      12971.01
     ],
     [
      "2025-10-20",
      13027.74
     ],
     [
      "2025-10-21",
      13039.44
     ],
     [
      "2025-10-22",
      13100.12
     ],
     [
      "2025-10-23",
      13112.67
     ],
     [
      "2025-10-30",
      13056.72
     ],
     [
      "2025-11-05",
      13121.27
     ],
     [
      "2025-11-06",
      13372.65
     ],
     [
      "2025-11-07",
      13421.3
     ],
     [
      "2025-11-10",
      13324.14
     ],
     [
      "2025-11-13",
      13570.89
     ],
     [
      "2025-11-14",
      13539.93
     ],
     [
      "2025-11-17",
      13419.5
     ],
     [
      "2025-11-18",
      13091.74
     ],
     [
      "2025-11-19",
      12978.25
     ],
     [
      "2025-11-20",
      13258.42
     ],
     [
      "2025-11-21",
      13184.13
     ],
     [
      "2025-11-24",
      13383.49
     ],
     [
      "2025-12-05",
      13307.33
     ],
     [
      "2025-12-11",
      13084.11
     ],
     [
      "2025-12-12",
      13185.14
     ],
     [
      "2025-12-15",
      13091.62
     ],
     [
      "2025-12-17",
      13323.32
     ],
     [
      "2025-12-19",
      13195.46
     ],
     [
      "2025-12-31",
      13219.27
     ],
     [
      "2026-01-02",
      13091.01
     ],
     [
      "2026-01-06",
      13026.76
     ],
     [
      "2026-01-07",
      12915.7
     ],
     [
      "2026-01-08",
      12659.66
     ],
     [
      "2026-01-09",
      12684.59
     ],
     [
      "2026-01-13",
      12602.59
     ],
     [
      "2026-01-14",
      12508.98
     ],
     [
      "2026-01-21",
      12440.63
     ],
     [
      "2026-01-23",
      12296.58
     ],
     [
      "2026-01-26",
      12311.65
     ],
     [
      "2026-01-29",
      12159.06
     ],
     [
      "2026-01-30",
      12005.25
     ],
     [
      "2026-02-02",
      11988.18
     ],
     [
      "2026-02-03",
      12162.47
     ],
     [
      "2026-02-04",
      12249.13
     ],
     [
      "2026-02-05",
      12198.67
     ],
     [
      "2026-02-06",
      12319.89
     ],
     [
      "2026-02-09",
      12323.81
     ],
     [
      "2026-02-12",
      12537.25
     ],
     [
      "2026-02-17",
      12495.12
     ],
     [
      "2026-02-18",
      12598.23
     ],
     [
      "2026-02-20",
      12334.61
     ],
     [
      "2026-02-23",
      12254.26
     ],
     [
      "2026-02-24",
      12211.17
     ],
     [
      "2026-02-25",
      12169.21
     ],
     [
      "2026-02-26",
      12253.36
     ],
     [
      "2026-03-04",
      12234.79
     ],
     [
      "2026-03-10",
      12127.75
     ],
     [
      "2026-03-12",
      12116.37
     ],
     [
      "2026-03-13",
      12083.62
     ],
     [
      "2026-03-17",
      12066.79
     ],
     [
      "2026-03-18",
      11957.71
     ],
     [
      "2026-03-20",
      12141.16
     ],
     [
      "2026-03-23",
      12005.7
     ],
     [
      "2026-03-24",
      11996.47
     ],
     [
      "2026-03-26",
      12103.0
     ],
     [
      "2026-03-27",
      12156.2
     ],
     [
      "2026-03-30",
      12205.0
     ],
     [
      "2026-03-31",
      12382.87
     ],
     [
      "2026-04-01",
      12358.02
     ],
     [
      "2026-04-06",
      12289.25
     ],
     [
      "2026-04-07",
      12241.8
     ],
     [
      "2026-04-09",
      12195.67
     ],
     [
      "2026-04-14",
      12310.6
     ],
     [
      "2026-04-15",
      12365.97
     ],
     [
      "2026-04-20",
      12313.86
     ],
     [
      "2026-04-22",
      12295.93
     ],
     [
      "2026-04-24",
      12395.15
     ],
     [
      "2026-04-28",
      12387.85
     ],
     [
      "2026-04-29",
      12360.87
     ],
     [
      "2026-04-30",
      12251.67
     ],
     [
      "2026-05-01",
      12214.7
     ],
     [
      "2026-05-04",
      12132.07
     ],
     [
      "2026-05-05",
      12181.67
     ],
     [
      "2026-05-06",
      12290.88
     ],
     [
      "2026-05-07",
      12272.48
     ],
     [
      "2026-05-08",
      12470.71
     ],
     [
      "2026-05-11",
      12355.49
     ],
     [
      "2026-05-12",
      12313.16
     ],
     [
      "2026-05-13",
      12331.49
     ],
     [
      "2026-05-14",
      12379.07
     ],
     [
      "2026-05-15",
      12247.47
     ],
     [
      "2026-05-18",
      12236.03
     ],
     [
      "2026-05-19",
      12161.19
     ],
     [
      "2026-05-20",
      12254.76
     ],
     [
      "2026-05-26",
      12248.5
     ],
     [
      "2026-05-27",
      12229.42
     ],
     [
      "2026-05-28",
      12250.83
     ],
     [
      "2026-05-29",
      12169.32
     ],
     [
      "2026-06-01",
      12162.65
     ],
     [
      "2026-06-03",
      12014.67
     ],
     [
      "2026-06-05",
      12702.4
     ],
     [
      "2026-06-08",
      12676.72
     ],
     [
      "2026-06-09",
      12740.02
     ],
     [
      "2026-06-10",
      12781.74
     ],
     [
      "2026-06-11",
      12840.06
     ],
     [
      "2026-06-12",
      12752.15
     ],
     [
      "2026-06-15",
      12766.19
     ],
     [
      "2026-06-16",
      12921.19
     ],
     [
      "2026-06-24",
      12816.17
     ],
     [
      "2026-06-25",
      12714.99
     ],
     [
      "2026-06-29",
      12769.25
     ],
     [
      "2026-06-30",
      12827.25
     ],
     [
      "2026-07-02",
      12817.94
     ],
     [
      "2026-07-06",
      12826.45
     ],
     [
      "2026-07-07",
      12788.85
     ],
     [
      "2026-07-09",
      12779.59
     ],
     [
      "2026-07-13",
      12745.07
     ],
     [
      "2026-07-15",
      12724.36
     ],
     [
      "2026-07-16",
      12720.05
     ],
     [
      "2026-07-23",
      12723.83
     ],
     [
      "2026-07-24",
      12677.82
     ],
     [
      "2026-07-27",
      12533.73
     ],
     [
      "2026-07-28",
      12317.07
     ],
     [
      "2026-07-29",
      12546.3
     ],
     [
      "2026-07-30",
      12558.91
     ],
     [
      "2026-08-03",
      12713.35
     ],
     [
      "2026-08-04",
      12933.05
     ],
     [
      "2026-08-13",
      12903.94
     ],
     [
      "2026-08-24",
      12829.77
     ],
     [
      "2026-08-27",
      12837.82
     ],
     [
      "2026-08-28",
      12778.06
     ],
     [
      "2026-09-03",
      12994.61
     ],
     [
      "2026-09-04",
      12909.22
     ],
     [
      "2026-09-15",
      12989.96
     ],
     [
      "2026-09-16",
      12780.25
     ],
     [
      "2026-09-21",
      13130.07
     ],
     [
      "2026-09-22",
      13179.35
     ],
     [
      "2026-09-23",
      13230.92
     ],
     [
      "2026-09-28",
      13121.36
     ],
     [
      "2026-09-30",
      13124.66
     ],
     [
      "2026-10-05",
      13273.2
     ],
     [
      "2026-10-08",
      13295.77
     ],
     [
      "2026-10-12",
      13254.75
     ],
     [
      "2026-10-14",
      13514.0
     ],
     [
      "2026-10-16",
      13992.54
     ]
    ],
    "by_year": {
     "2024": 2456.15,
     "2025": 763.12,
     "2026": 773.27
    },
    "by_month": {
     "2024-01": 179.02,
     "2024-02": -32.4,
     "2024-03": 258.1,
     "2024-04": 567.77,
     "2024-05": -256.95,
     "2024-06": -86.07,
     "2024-07": 591.77,
     "2024-08": -269.74,
     "2024-09": 342.49,
     "2024-10": 217.64,
     "2024-11": -9.93,
     "2024-12": 954.45,
     "2025-01": -5.57,
     "2025-02": 497.51,
     "2025-03": 489.26,
     "2025-04": 543.42,
     "2025-05": -271.68,
     "2025-06": -291.15,
     "2025-07": -430.1,
     "2025-08": -7.9,
     "2025-09": -1000.53,
     "2025-10": 1077.31,
     "2025-11": 326.77,
     "2025-12": -164.22,
     "2026-01": -1214.02,
     "2026-02": 248.11,
     "2026-03": 129.51,
     "2026-04": -131.2,
     "2026-05": -82.35,
     "2026-06": 657.93,
     "2026-07": -268.34,
     "2026-08": 219.15,
     "2026-09": 346.6,
     "2026-10": 867.88
    },
    "by_symbol": {
     "US100.cash": 3992.54
    },
    "worst_day": {
     "day": "2025-04-07",
     "pct": -2.92
    },
    "months_positive": 18,
    "months": 34,
    "return_pct": 39.93
   },
   "expected": {
    "symbol": "US100.cash",
    "from": "2024-01-01",
    "to": "2026-10-01",
    "deposit": 10000,
    "trades": 701,
    "return_pct": 44.7,
    "eq_dd_max_pct": 18.5
   }
  },
  {
   "name": "2026-10-17_0457_AurumNoise_US500",
   "job": {
    "Expert": "AurumNoise",
    "Symbol": "US500.cash",
    "From": "2024.01.01",
    "To": "2026.10.17",
    "Deposit": 10000,
    "Leverage": 100,
    "Period": "M1",
    "Set": "",
    "Started": "2026-10-17T04:57:14.4475183+02:00"
   },
   "summary": "# AurumNoise US500.cash, M1, 2024-01-01 to 2026-10-17 (job j1)\n\nReal ticks (99% history quality, 47.5M ticks), deposit 10,000, leverage 1:100, preset AurumNoise_US500.set.\n\n| Figure | Tester | Expected (README test 2) | Gap |\n|---|---|---|---|\n| Net profit | -68.46 (-0.68%) | +1.3% | -2.0 points |\n| Max equity drawdown | 3,321.72 (26.09%) | 28.6% | 2.5 points less |\n| Max balance drawdown | 3,165.34 (25.03%) | n/a | |\n| Trades | 452 | n/a | |\n| Win rate | 39.6% (179 won) | n/a | |\n| Profit factor | 1.00 (gross +14,370.21 / -14,438.67) | n/a | |\n| Sharpe / recovery | -0.11 / -0.02 | n/a | |\n| Worst day | -2.19% (2025-08-01) | n/a | |\n\nBy year (net): 2024 +1,688.78, 2025 -663.05, 2026 -1,094.19.\nMonths positive: 13 of 34. Worst months: 2025-09 -754.32, 2025-11 -676.82, 2026-03 -549.85. Best: 2024-12 +1,230.82.\n\nLog: no \"not found\", \"cannot\", \"failed\" or margin errors in the collected lines. Final balance 9,931.54.\n\nReading for the orchestrator (no judgement made here): a flat result (about break-even) instead of a small gain,\nwith a slightly smaller drawdown than expected. The profit came all in 2024; 2025 and 2026 lost.\n",
   "state": "done",
   "result": {
    "expert": "AurumNoise",
    "symbol": "US500.cash",
    "period": "M1 (2024.01.01 - 2026.10.17)",
    "deposit": 10000.0,
    "net": -68.46,
    "gross_profit": 14370.21,
    "gross_loss": -14438.67,
    "profit_factor": 1.0,
    "recovery": -0.02,
    "sharpe": -0.11,
    "trades": 452.0,
    "won": "179 (39.60%)",
    "eq_dd_max": "3 321.72 (26.09%)",
    "eq_dd_rel": "26.09% (3 321.72)",
    "bal_dd_max": "3 165.34 (25.03%)",
    "ticks": 47464257.0,
    "history_quality": "99% real ticks",
    "win_rate": 39.6,
    "eq_dd_max_pct": 26.09,
    "bal_dd_max_pct": 25.03,
    "deals": 905,
    "curve": [
     [
      "2024-01-03",
      9985.21
     ],
     [
      "2024-01-04",
      9971.1
     ],
     [
      "2024-01-05",
      9899.93
     ],
     [
      "2024-01-08",
      10214.53
     ],
     [
      "2024-01-10",
      10255.63
     ],
     [
      "2024-01-11",
      10203.61
     ],
     [
      "2024-01-18",
      10250.86
     ],
     [
      "2024-01-19",
      10396.32
     ],
     [
      "2024-01-22",
      10351.41
     ],
     [
      "2024-01-29",
      10371.74
     ],
     [
      "2024-01-31",
      10526.87
     ],
     [
      "2024-02-01",
      10558.13
     ],
     [
      "2024-02-02",
      10743.72
     ],
     [
      "2024-02-05",
      10668.14
     ],
     [
      "2024-02-07",
      10627.67
     ],
     [
      "2024-02-12",
      10605.59
     ],
     [
      "2024-02-13",
      10408.04
     ],
     [
      "2024-02-15",
      10390.77
     ],
     [
      "2024-02-16",
      10326.64
     ],
     [
      "2024-02-20",
      10303.81
     ],
     [
      "2024-02-22",
      10402.33
     ],
     [
      "2024-03-01",
      10527.11
     ],
     [
      "2024-03-05",
      10562.07
     ],
     [
      "2024-03-07",
      10534.16
     ],
     [
      "2024-03-08",
      10337.88
     ],
     [
      "2024-03-12",
      10351.96
     ],
     [
      "2024-03-14",
      10176.78
     ],
     [
      "2024-03-15",
      10091.59
     ],
     [
      "2024-04-01",
      10008.72
     ],
     [
      "2024-04-03",
      9985.51
     ],
     [
      "2024-04-04",
      10175.95
     ],
     [
      "2024-04-05",
      10144.85
     ],
     [
      "2024-04-09",
      9995.71
     ],
     [
      "2024-04-11",
      9945.95
     ],
     [
      "2024-04-12",
      10001.04
     ],
     [
      "2024-04-15",
      10110.93
     ],
     [
      "2024-04-17",
      10037.75
     ],
     [
      "2024-04-19",
      9930.47
     ],
     [
      "2024-04-23",
      10033.4
     ],
     [
      "2024-04-26",
      10041.83
     ],
     [
      "2024-05-03",
      9919.79
     ],
     [
      "2024-05-15",
      9961.36
     ],
     [
      "2024-05-20",
      9971.94
     ],
     [
      "2024-05-22",
      9900.31
     ],
     [
      "2024-05-23",
      9955.59
     ],
     [
      "2024-05-24",
      9919.97
     ],
     [
      "2024-05-31",
      9867.32
     ],
     [
      "2024-06-03",
      9788.2
     ],
     [
      "2024-06-05",
      9836.54
     ],
     [
      "2024-06-11",
      9768.82
     ],
     [
      "2024-06-12",
      9787.98
     ],
     [
      "2024-06-17",
      9829.86
     ],
     [
      "2024-06-24",
      9858.54
     ],
     [
      "2024-06-27",
      9813.31
     ],
     [
      "2024-06-28",
      9766.16
     ],
     [
      "2024-07-02",
      9884.9
     ],
     [
      "2024-07-03",
      9884.9
     ],
     [
      "2024-07-04",
      9866.33
     ],
     [
      "2024-07-05",
      9892.55
     ],
     [
      "2024-07-10",
      10050.19
     ],
     [
      "2024-07-11",
      10281.14
     ],
     [
      "2024-07-12",
      10345.08
     ],
     [
      "2024-07-18",
      10401.94
     ],
     [
      "2024-07-19",
      10294.81
     ],
     [
      "2024-07-23",
      10240.3
     ],
     [
      "2024-07-24",
      10499.85
     ],
     [
      "2024-07-25",
      10410.21
     ],
     [
      "2024-07-26",
      10320.44
     ],
     [
      "2024-07-30",
      10288.35
     ],
     [
      "2024-08-01",
      10300.3
     ],
     [
      "2024-08-02",
      10294.48
     ],
     [
      "2024-08-06",
      10192.21
     ],
     [
      "2024-08-07",
      10124.48
     ],
     [
      "2024-08-08",
      10121.9
     ],
     [
      "2024-08-23",
      10057.83
     ],
     [
      "2024-08-28",
      9889.93
     ],
     [
      "2024-08-29",
      9881.3
     ],
     [
      "2024-09-03",
      10183.45
     ],
     [
      "2024-09-05",
      10071.7
     ],
     [
      "2024-09-06",
      10411.08
     ],
     [
      "2024-09-11",
      10450.11
     ],
     [
      "2024-10-01",
      10471.55
     ],
     [
      "2024-10-07",
      10404.5
     ],
     [
      "2024-10-08",
      10420.96
     ],
     [
      "2024-10-09",
      10490.68
     ],
     [
      "2024-10-11",
      10468.27
     ],
     [
      "2024-10-14",
      10506.74
     ],
     [
      "2024-10-15",
      10553.74
     ],
     [
      "2024-10-21",
      10469.74
     ],
     [
      "2024-10-23",
      10476.44
     ],
     [
      "2024-10-25",
      10478.4
     ],
     [
      "2024-10-31",
      10697.09
     ],
     [
      "2024-11-01",
      10715.25
     ],
     [
      "2024-11-05",
      10855.07
     ],
     [
      "2024-11-12",
      10813.71
     ],
     [
      "2024-11-14",
      10787.57
     ],
     [
      "2024-11-15",
      10765.05
     ],
     [
      "2024-11-20",
      10676.47
     ],
     [
      "2024-11-21",
      10510.59
     ],
     [
      "2024-11-22",
      10425.29
     ],
     [
      "2024-11-29",
      10457.96
     ],
     [
      "2024-12-06",
      10448.41
     ],
     [
      "2024-12-09",
      10432.67
     ],
     [
      "2024-12-11",
      10396.5
     ],
     [
      "2024-12-18",
      11395.27
     ],
     [
      "2024-12-20",
      11563.09
     ],
     [
      "2024-12-23",
      11569.5
     ],
     [
      "2024-12-24",
      11637.47
     ],
     [
      "2024-12-26",
      11673.31
     ],
     [
      "2024-12-27",
      11759.69
     ],
     [
      "2024-12-30",
      11688.78
     ],
     [
      "2025-01-02",
      11633.6
     ],
     [
      "2025-01-06",
      11666.57
     ],
     [
      "2025-01-07",
      11630.93
     ],
     [
      "2025-01-08",
      11654.85
     ],
     [
      "2025-01-10",
      11681.93
     ],
     [
      "2025-01-28",
      11658.03
     ],
     [
      "2025-01-29",
      11536.09
     ],
     [
      "2025-02-04",
      11390.78
     ],
     [
      "2025-02-07",
      11521.53
     ],
     [
      "2025-02-20",
      11452.88
     ],
     [
      "2025-02-21",
      11897.33
     ],
     [
      "2025-02-25",
      11855.77
     ],
     [
      "2025-02-27",
      11912.84
     ],
     [
      "2025-03-03",
      12102.07
     ],
     [
      "2025-03-04",
      12004.62
     ],
     [
      "2025-03-05",
      12005.58
     ],
     [
      "2025-03-07",
      11969.0
     ],
     [
      "2025-03-10",
      12196.26
     ],
     [
      "2025-03-12",
      12077.92
     ],
     [
      "2025-03-13",
      12073.8
     ],
     [
      "2025-03-14",
      12009.06
     ],
     [
      "2025-03-17",
      11973.48
     ],
     [
      "2025-03-18",
      11949.0
     ],
     [
      "2025-03-21",
      11928.97
     ],
     [
      "2025-03-28",
      11993.57
     ],
     [
      "2025-04-01",
      11825.8
     ],
     [
      "2025-04-02",
      11756.85
     ],
     [
      "2025-04-03",
      11855.23
     ],
     [
      "2025-04-04",
      12135.34
     ],
     [
      "2025-04-08",
      12153.6
     ],
     [
      "2025-04-09",
      12540.81
     ],
     [
      "2025-04-10",
      12541.89
     ],
     [
      "2025-04-21",
      12645.82
     ],
     [
      "2025-04-24",
      12647.84
     ],
     [
      "2025-04-30",
      12576.9
     ],
     [
      "2025-05-13",
      12528.29
     ],
     [
      "2025-05-21",
      12573.62
     ],
     [
      "2025-05-27",
      12555.54
     ],
     [
      "2025-05-30",
      12409.61
     ],
     [
      "2025-06-05",
      12311.8
     ],
     [
      "2025-06-16",
      12254.47
     ],
     [
      "2025-06-18",
      12213.08
     ],
     [
      "2025-06-19",
      12093.85
     ],
     [
      "2025-06-23",
      12226.81
     ],
     [
      "2025-06-27",
      12256.95
     ],
     [
      "2025-07-03",
      12256.95
     ],
     [
      "2025-07-04",
      12274.12
     ],
     [
      "2025-07-09",
      12199.0
     ],
     [
      "2025-07-17",
      12264.93
     ],
     [
      "2025-07-21",
      12272.84
     ],
     [
      "2025-07-22",
      12248.11
     ],
     [
      "2025-07-30",
      12052.1
     ],
     [
      "2025-08-01",
      11787.93
     ],
     [
      "2025-08-04",
      11910.93
     ],
     [
      "2025-08-05",
      11843.82
     ],
     [
      "2025-08-06",
      11822.6
     ],
     [
      "2025-08-08",
      11817.68
     ],
     [
      "2025-08-12",
      11822.67
     ],
     [
      "2025-08-15",
      11782.46
     ],
     [
      "2025-08-20",
      11624.1
     ],
     [
      "2025-08-22",
      11687.71
     ],
     [
      "2025-08-29",
      11696.3
     ],
     [
      "2025-09-04",
      11756.38
     ],
     [
      "2025-09-05",
      11584.89
     ],
     [
      "2025-09-11",
      11578.6
     ],
     [
      "2025-09-18",
      11411.7
     ],
     [
      "2025-09-22",
      11435.5
     ],
     [
      "2025-09-23",
      11450.87
     ],
     [
      "2025-09-24",
      11350.73
     ],
     [
      "2025-09-25",
      11146.37
     ],
     [
      "2025-09-26",
      10941.98
     ],
     [
      "2025-10-01",
      10962.32
     ],
     [
      "2025-10-03",
      10919.14
     ],
     [
      "2025-10-07",
      10893.46
     ],
     [
      "2025-10-09",
      10857.12
     ],
     [
      "2025-10-10",
      11899.7
     ],
     [
      "2025-10-13",
      11815.29
     ],
     [
      "2025-10-15",
      11791.19
     ],
     [
      "2025-10-16",
      11638.03
     ],
     [
      "2025-10-20",
      11703.52
     ],
     [
      "2025-10-22",
      11692.33
     ],
     [
      "2025-10-23",
      11668.18
     ],
     [
      "2025-11-03",
      11549.55
     ],
     [
      "2025-11-05",
      11531.58
     ],
     [
      "2025-11-06",
      11468.55
     ],
     [
      "2025-11-07",
      11365.71
     ],
     [
      "2025-11-10",
      11367.86
     ],
     [
      "2025-11-13",
      11555.87
     ],
     [
      "2025-11-17",
      11426.87
     ],
     [
      "2025-11-18",
      11211.43
     ],
     [
      "2025-11-19",
      11095.85
     ],
     [
      "2025-11-20",
      11020.97
     ],
     [
      "2025-11-21",
      11004.28
     ],
     [
      "2025-11-24",
      10991.36
     ],
     [
      "2025-12-11",
      10827.21
     ],
     [
      "2025-12-12",
      10843.02
     ],
     [
      "2025-12-17",
      11032.08
     ],
     [
      "2025-12-19",
      10989.62
     ],
     [
      "2025-12-31",
      11025.73
     ],
     [
      "2026-01-06",
      11049.24
     ],
     [
      "2026-01-09",
      10986.81
     ],
     [
      "2026-01-13",
      10917.86
     ],
     [
      "2026-01-14",
      10683.74
     ],
     [
      "2026-01-20",
      10700.7
     ],
     [
      "2026-01-21",
      10627.76
     ],
     [
      "2026-01-26",
      10611.15
     ],
     [
      "2026-01-29",
      10580.23
     ],
     [
      "2026-02-02",
      10576.16
     ],
     [
      "2026-02-03",
      10632.89
     ],
     [
      "2026-02-04",
      10559.97
     ],
     [
      "2026-02-05",
      10528.79
     ],
     [
      "2026-02-06",
      10692.7
     ],
     [
      "2026-02-09",
      10685.23
     ],
     [
      "2026-02-12",
      10776.11
     ],
     [
      "2026-02-17",
      10751.6
     ],
     [
      "2026-02-23",
      10714.78
     ],
     [
      "2026-02-26",
      10569.17
     ],
     [
      "2026-03-03",
      10468.2
     ],
     [
      "2026-03-10",
      10308.38
     ],
     [
      "2026-03-12",
      10288.9
     ],
     [
      "2026-03-18",
      10198.31
     ],
     [
      "2026-03-20",
      10251.66
     ],
     [
      "2026-03-23",
      10126.01
     ],
     [
      "2026-03-24",
      10086.7
     ],
     [
      "2026-03-26",
      10057.4
     ],
     [
      "2026-03-27",
      10120.96
     ],
     [
      "2026-03-30",
      10043.9
     ],
     [
      "2026-03-31",
      10019.32
     ],
     [
      "2026-04-01",
      10003.2
     ],
     [
      "2026-04-06",
      9978.47
     ],
     [
      "2026-04-09",
      9940.98
     ],
     [
      "2026-04-14",
      9958.04
     ],
     [
      "2026-04-17",
      9939.25
     ],
     [
      "2026-04-30",
      9908.54
     ],
     [
      "2026-05-01",
      9850.1
     ],
     [
      "2026-05-04",
      9760.22
     ],
     [
      "2026-05-06",
      9793.53
     ],
     [
      "2026-05-08",
      9770.01
     ],
     [
      "2026-05-11",
      9753.73
     ],
     [
      "2026-05-12",
      9725.98
     ],
     [
      "2026-05-13",
      9750.56
     ],
     [
      "2026-05-14",
      9814.42
     ],
     [
      "2026-05-15",
      9718.53
     ],
     [
      "2026-05-18",
      9592.0
     ],
     [
      "2026-05-20",
      9645.29
     ],
     [
      "2026-05-28",
      9636.15
     ],
     [
      "2026-05-29",
      9584.53
     ],
     [
      "2026-06-03",
      9506.04
     ],
     [
      "2026-06-05",
      9985.37
     ],
     [
      "2026-06-09",
      9855.96
     ],
     [
      "2026-06-10",
      9913.11
     ],
     [
      "2026-06-11",
      9985.75
     ],
     [
      "2026-06-17",
      10003.0
     ],
     [
      "2026-06-24",
      10000.74
     ],
     [
      "2026-06-25",
      9873.15
     ],
     [
      "2026-06-30",
      9885.52
     ],
     [
      "2026-07-02",
      9824.27
     ],
     [
      "2026-07-07",
      9832.33
     ],
     [
      "2026-07-23",
      9742.66
     ],
     [
      "2026-07-24",
      9683.96
     ],
     [
      "2026-07-28",
      9629.44
     ],
     [
      "2026-07-29",
      9888.28
     ],
     [
      "2026-07-30",
      9965.99
     ],
     [
      "2026-08-03",
      10091.4
     ],
     [
      "2026-08-04",
      10223.87
     ],
     [
      "2026-08-13",
      10178.59
     ],
     [
      "2026-08-27",
      10114.3
     ],
     [
      "2026-08-28",
      9909.68
     ],
     [
      "2026-08-31",
      9822.27
     ],
     [
      "2026-09-02",
      9746.44
     ],
     [
      "2026-09-03",
      9704.78
     ],
     [
      "2026-09-04",
      9702.07
     ],
     [
      "2026-09-08",
      9667.56
     ],
     [
      "2026-09-09",
      9619.02
     ],
     [
      "2026-09-11",
      9587.67
     ],
     [
      "2026-09-15",
      9507.08
     ],
     [
      "2026-09-16",
      9482.5
     ],
     [
      "2026-09-21",
      9647.62
     ],
     [
      "2026-09-23",
      9734.5
     ],
     [
      "2026-09-28",
      9567.18
     ],
     [
      "2026-10-05",
      9630.71
     ],
     [
      "2026-10-14",
      9738.2
     ],
     [
      "2026-10-16",
      9931.54
     ]
    ],
    "by_year": {
     "2024": 1688.78,
     "2025": -663.05,
     "2026": -1094.19
    },
    "by_month": {
     "2024-01": 526.87,
     "2024-02": -124.54,
     "2024-03": -310.74,
     "2024-04": -49.76,
     "2024-05": -174.51,
     "2024-06": -101.16,
     "2024-07": 522.19,
     "2024-08": -407.05,
     "2024-09": 568.81,
     "2024-10": 246.98,
     "2024-11": -239.13,
     "2024-12": 1230.82,
     "2025-01": -152.69,
     "2025-02": 376.75,
     "2025-03": 80.73,
     "2025-04": 583.33,
     "2025-05": -167.29,
     "2025-06": -152.66,
     "2025-07": -204.85,
     "2025-08": -355.8,
     "2025-09": -754.32,
     "2025-10": 726.2,
     "2025-11": -676.82,
     "2025-12": 34.37,
     "2026-01": -445.5,
     "2026-02": -11.06,
     "2026-03": -549.85,
     "2026-04": -110.78,
     "2026-05": -324.01,
     "2026-06": 300.99,
     "2026-07": 80.47,
     "2026-08": -143.72,
     "2026-09": -255.09,
     "2026-10": 364.36
    },
    "by_symbol": {
     "US500.cash": -68.46
    },
    "worst_day": {
     "day": "2025-08-01",
     "pct": -2.19
    },
    "months_positive": 13,
    "months": 34,
    "return_pct": -0.68
   },
   "expected": {
    "symbol": "US500.cash",
    "from": "2024-01-01",
    "to": "2026-10-01",
    "deposit": 10000,
    "trades": 451,
    "return_pct": 1.3,
    "eq_dd_max_pct": 28.6
   }
  },
  {
   "name": "2026-10-17_0118_AurumBreakout_USDJPY",
   "job": {
    "Expert": "AurumBreakout",
    "Symbol": "USDJPY",
    "From": "2024.01.01",
    "To": "2026.10.01",
    "Deposit": 10000,
    "Leverage": 100,
    "Period": "M1",
    "Set": "",
    "Started": "2026-10-17T01:18:27.5146556+02:00"
   },
   "summary": "# AurumBreakout, USDJPY, Strategy Tester (FTMO-Demo)\n\nRun on 2026-10-17 by `tools/run-tester.ps1 -Detach` (pipeline step 15): USDJPY M1, 2024-01-01 to 2026-10-01, every\ntick based on real ticks (99% real-tick history, 90.7 million ticks), 10,000 USD, 1:100, `AurumBreakout_USDJPY.set`\n(risk 0.25% per side, both sides). The first launch at 00:56 died with its shell; this is the detached rerun.\n\nResult: **+996.08 (+9.96%) in 33 months**, 771 trades, 47.7% winners, profit factor 1.16, tester Sharpe 1.79,\nrecovery factor 2.37. Equity drawdown at most 4.02% (balance 3.70%). Worst day -0.91% of the day's starting balance\n(2024-05-23). 20 of 33 months positive, worst month -218 (2024-05), best +445, median +23, mean +30.\nBy year: 2024 +377, 2025 +196, 2026 to 09-30 +423.\n\n| | Expected (Python, measured costs) | Tester | |\n|---|---|---|---|\n| Trades | 777 | 771 | -0.8% |\n| Winners | 47% | 47.7% | |\n| Profit factor | 1.14 | 1.16 | |\n| Return | +8.6% | +9.96% | |\n| Max equity drawdown | 5.0% | 4.02% | |\n\nThe tester matches the model within noise, slightly better on return and drawdown; no gap for the reviewer to\nexplain. Step 15 passed for the standalone EA. Next: step 16, the leg on vs off inside AurumFunded 1.03\n(`InpBreakRiskPct=0.125`).\n",
   "state": "done",
   "result": {
    "expert": "AurumBreakout",
    "symbol": "USDJPY",
    "period": "M1 (2024.01.01 - 2026.10.01)",
    "deposit": 10000.0,
    "net": 996.08,
    "gross_profit": 7065.49,
    "gross_loss": -6069.41,
    "profit_factor": 1.16,
    "recovery": 2.37,
    "sharpe": 1.79,
    "trades": 771.0,
    "won": "368 (47.73%)",
    "eq_dd_max": "419.41 (4.02%)",
    "eq_dd_rel": "4.02% (419.41)",
    "bal_dd_max": "384.45 (3.70%)",
    "ticks": 90728927.0,
    "history_quality": "99% real ticks",
    "win_rate": 47.73,
    "eq_dd_max_pct": 4.02,
    "bal_dd_max_pct": 3.7,
    "deals": 1543,
    "curve": [
     [
      "2024-01-02",
      10006.96
     ],
     [
      "2024-01-03",
      10055.67
     ],
     [
      "2024-01-04",
      10071.42
     ],
     [
      "2024-01-05",
      10061.21
     ],
     [
      "2024-01-08",
      10066.96
     ],
     [
      "2024-01-09",
      10067.4
     ],
     [
      "2024-01-10",
      10080.3
     ],
     [
      "2024-01-11",
      10053.42
     ],
     [
      "2024-01-12",
      10033.69
     ],
     [
      "2024-01-15",
      10047.14
     ],
     [
      "2024-01-16",
      10061.4
     ],
     [
      "2024-01-17",
      10075.75
     ],
     [
      "2024-01-18",
      10049.0
     ],
     [
      "2024-01-19",
      10044.05
     ],
     [
      "2024-01-22",
      10012.44
     ],
     [
      "2024-01-23",
      10011.71
     ],
     [
      "2024-01-24",
      10038.6
     ],
     [
      "2024-01-25",
      10004.22
     ],
     [
      "2024-01-26",
      9954.54
     ],
     [
      "2024-01-29",
      9959.52
     ],
     [
      "2024-01-30",
      9911.37
     ],
     [
      "2024-01-31",
      9921.58
     ],
     [
      "2024-02-01",
      9906.71
     ],
     [
      "2024-02-02",
      10006.4
     ],
     [
      "2024-02-05",
      10008.16
     ],
     [
      "2024-02-06",
      10000.7
     ],
     [
      "2024-02-07",
      9951.49
     ],
     [
      "2024-02-09",
      9914.82
     ],
     [
      "2024-02-12",
      9908.19
     ],
     [
      "2024-02-13",
      9980.46
     ],
     [
      "2024-02-14",
      9966.28
     ],
     [
      "2024-02-15",
      9966.76
     ],
     [
      "2024-02-16",
      9961.43
     ],
     [
      "2024-02-19",
      9961.55
     ],
     [
      "2024-02-20",
      9984.34
     ],
     [
      "2024-02-21",
      9991.49
     ],
     [
      "2024-02-22",
      9969.68
     ],
     [
      "2024-02-23",
      9930.68
     ],
     [
      "2024-02-26",
      9945.37
     ],
     [
      "2024-02-27",
      9938.82
     ],
     [
      "2024-02-28",
      9942.42
     ],
     [
      "2024-02-29",
      9942.5
     ],
     [
      "2024-03-01",
      9926.93
     ],
     [
      "2024-03-04",
      9930.5
     ],
     [
      "2024-03-05",
      9975.52
     ],
     [
      "2024-03-06",
      9981.69
     ],
     [
      "2024-03-07",
      9978.86
     ],
     [
      "2024-03-08",
      9998.19
     ],
     [
      "2024-03-11",
      9979.93
     ],
     [
      "2024-03-12",
      9987.04
     ],
     [
      "2024-03-13",
      9998.65
     ],
     [
      "2024-03-14",
      9948.36
     ],
     [
      "2024-03-15",
      9934.46
     ],
     [
      "2024-03-19",
      9939.18
     ],
     [
      "2024-03-21",
      9941.93
     ],
     [
      "2024-03-22",
      9954.55
     ],
     [
      "2024-03-25",
      9944.45
     ],
     [
      "2024-03-26",
      9915.8
     ],
     [
      "2024-03-27",
      9919.46
     ],
     [
      "2024-03-28",
      9914.68
     ],
     [
      "2024-04-01",
      9945.82
     ],
     [
      "2024-04-02",
      9938.49
     ],
     [
      "2024-04-03",
      9948.5
     ],
     [
      "2024-04-04",
      9903.22
     ],
     [
      "2024-04-05",
      9910.05
     ],
     [
      "2024-04-08",
      9909.46
     ],
     [
      "2024-04-09",
      9927.7
     ],
     [
      "2024-04-10",
      10088.25
     ],
     [
      "2024-04-11",
      10093.72
     ],
     [
      "2024-04-12",
      10070.6
     ],
     [
      "2024-04-15",
      10082.22
     ],
     [
      "2024-04-16",
      10029.35
     ],
     [
      "2024-04-17",
      10011.99
     ],
     [
      "2024-04-18",
      10023.18
     ],
     [
      "2024-04-22",
      10021.55
     ],
     [
      "2024-04-23",
      9962.55
     ],
     [
      "2024-04-24",
      9969.93
     ],
     [
      "2024-04-25",
      9961.79
     ],
     [
      "2024-04-26",
      9921.3
     ],
     [
      "2024-04-30",
      9929.57
     ],
     [
      "2024-05-01",
      9903.38
     ],
     [
      "2024-05-03",
      9897.82
     ],
     [
      "2024-05-09",
      9889.65
     ],
     [
      "2024-05-10",
      9893.69
     ],
     [
      "2024-05-14",
      9885.03
     ],
     [
      "2024-05-15",
      9939.19
     ],
     [
      "2024-05-16",
      9948.4
     ],
     [
      "2024-05-17",
      9927.79
     ],
     [
      "2024-05-20",
      9910.24
     ],
     [
      "2024-05-21",
      9927.53
     ],
     [
      "2024-05-22",
      9939.61
     ],
     [
      "2024-05-23",
      9849.54
     ],
     [
      "2024-05-24",
      9840.99
     ],
     [
      "2024-05-27",
      9821.58
     ],
     [
      "2024-05-28",
      9773.24
     ],
     [
      "2024-05-29",
      9755.22
     ],
     [
      "2024-05-30",
      9758.67
     ],
     [
      "2024-05-31",
      9711.39
     ],
     [
      "2024-06-03",
      9746.03
     ],
     [
      "2024-06-04",
      9793.76
     ],
     [
      "2024-06-05",
      9801.49
     ],
     [
      "2024-06-06",
      9798.51
     ],
     [
      "2024-06-07",
      9816.44
     ],
     [
      "2024-06-11",
      9767.46
     ],
     [
      "2024-06-12",
      9888.68
     ],
     [
      "2024-06-13",
      9840.81
     ],
     [
      "2024-06-14",
      9830.31
     ],
     [
      "2024-06-17",
      9817.5
     ],
     [
      "2024-06-18",
      9817.1
     ],
     [
      "2024-06-19",
      9787.17
     ],
     [
      "2024-06-20",
      9833.66
     ],
     [
      "2024-06-21",
      9842.69
     ],
     [
      "2024-06-24",
      9833.08
     ],
     [
      "2024-06-25",
      9831.67
     ],
     [
      "2024-06-26",
      9888.08
     ],
     [
      "2024-06-27",
      9873.03
     ],
     [
      "2024-06-28",
      9865.12
     ],
     [
      "2024-07-01",
      9887.73
     ],
     [
      "2024-07-02",
      9884.44
     ],
     [
      "2024-07-03",
      9862.42
     ],
     [
      "2024-07-04",
      9864.62
     ],
     [
      "2024-07-05",
      9853.49
     ],
     [
      "2024-07-08",
      9844.78
     ],
     [
      "2024-07-09",
      9857.2
     ],
     [
      "2024-07-10",
      9861.65
     ],
     [
      "2024-07-11",
      10129.31
     ],
     [
      "2024-07-12",
      10129.22
     ],
     [
      "2024-07-15",
      10127.48
     ],
     [
      "2024-07-16",
      10120.88
     ],
     [
      "2024-07-17",
      10154.19
     ],
     [
      "2024-07-18",
      10157.51
     ],
     [
      "2024-07-19",
      10148.07
     ],
     [
      "2024-07-22",
      10139.63
     ],
     [
      "2024-07-23",
      10144.15
     ],
     [
      "2024-07-24",
      10158.09
     ],
     [
      "2024-07-25",
      10130.89
     ],
     [
      "2024-07-26",
      10099.63
     ],
     [
      "2024-07-30",
      10093.63
     ],
     [
      "2024-08-02",
      10152.77
     ],
     [
      "2024-08-08",
      10158.35
     ],
     [
      "2024-08-09",
      10161.69
     ],
     [
      "2024-08-12",
      10191.77
     ],
     [
      "2024-08-13",
      10168.96
     ],
     [
      "2024-08-14",
      10159.99
     ],
     [
      "2024-08-15",
      10216.38
     ],
     [
      "2024-08-16",
      10245.75
     ],
     [
      "2024-08-20",
      10248.93
     ],
     [
      "2024-08-21",
      10242.34
     ],
     [
      "2024-08-22",
      10258.39
     ],
     [
      "2024-08-23",
      10237.98
     ],
     [
      "2024-08-26",
      10232.4
     ],
     [
      "2024-08-27",
      10210.3
     ],
     [
      "2024-08-29",
      10226.14
     ],
     [
      "2024-08-30",
      10254.04
     ],
     [
      "2024-09-02",
      10263.61
     ],
     [
      "2024-09-03",
      10272.58
     ],
     [
      "2024-09-04",
      10298.37
     ],
     [
      "2024-09-05",
      10272.91
     ],
     [
      "2024-09-06",
      10226.6
     ],
     [
      "2024-09-09",
      10219.04
     ],
     [
      "2024-09-10",
      10198.54
     ],
     [
      "2024-09-11",
      10183.65
     ],
     [
      "2024-09-12",
      10152.89
     ],
     [
      "2024-09-13",
      10152.78
     ],
     [
      "2024-09-16",
      10139.87
     ],
     [
      "2024-09-17",
      10149.09
     ],
     [
      "2024-09-20",
      10178.7
     ],
     [
      "2024-09-23",
      10176.05
     ],
     [
      "2024-09-24",
      10159.96
     ],
     [
      "2024-09-25",
      10178.38
     ],
     [
      "2024-09-26",
      10127.66
     ],
     [
      "2024-09-27",
      10129.82
     ],
     [
      "2024-09-30",
      10130.82
     ],
     [
      "2024-10-01",
      10125.58
     ],
     [
      "2024-10-02",
      10180.19
     ],
     [
      "2024-10-04",
      10211.04
     ],
     [
      "2024-10-07",
      10210.73
     ],
     [
      "2024-10-08",
      10191.24
     ],
     [
      "2024-10-09",
      10212.34
     ],
     [
      "2024-10-10",
      10162.26
     ],
     [
      "2024-10-11",
      10189.66
     ],
     [
      "2024-10-14",
      10225.02
     ],
     [
      "2024-10-15",
      10228.13
     ],
     [
      "2024-10-16",
      10239.79
     ],
     [
      "2024-10-17",
      10260.51
     ],
     [
      "2024-10-18",
      10267.31
     ],
     [
      "2024-10-21",
      10290.45
     ],
     [
      "2024-10-23",
      10304.6
     ],
     [
      "2024-10-24",
      10308.29
     ],
     [
      "2024-10-25",
      10305.33
     ],
     [
      "2024-10-28",
      10303.38
     ],
     [
      "2024-10-29",
      10290.09
     ],
     [
      "2024-10-30",
      10240.54
     ],
     [
      "2024-10-31",
      10236.42
     ],
     [
      "2024-11-04",
      10225.51
     ],
     [
      "2024-11-05",
      10227.85
     ],
     [
      "2024-11-07",
      10258.84
     ],
     [
      "2024-11-08",
      10261.71
     ],
     [
      "2024-11-11",
      10265.18
     ],
     [
      "2024-11-12",
      10282.47
     ],
     [
      "2024-11-13",
      10237.89
     ],
     [
      "2024-11-14",
      10232.79
     ],
     [
      "2024-11-15",
      10253.73
     ],
     [
      "2024-11-18",
      10250.69
     ],
     [
      "2024-11-19",
      10249.88
     ],
     [
      "2024-11-20",
      10247.12
     ],
     [
      "2024-11-21",
      10252.91
     ],
     [
      "2024-11-22",
      10251.59
     ],
     [
      "2024-11-25",
      10247.93
     ],
     [
      "2024-11-26",
      10249.63
     ],
     [
      "2024-11-27",
      10266.15
     ],
     [
      "2024-11-28",
      10259.61
     ],
     [
      "2024-12-03",
      10270.58
     ],
     [
      "2024-12-04",
      10270.41
     ],
     [
      "2024-12-05",
      10258.29
     ],
     [
      "2024-12-06",
      10227.94
     ],
     [
      "2024-12-09",
      10249.93
     ],
     [
      "2024-12-10",
      10268.14
     ],
     [
      "2024-12-11",
      10266.46
     ],
     [
      "2024-12-12",
      10257.07
     ],
     [
      "2024-12-13",
      10278.99
     ],
     [
      "2024-12-16",
      10288.96
     ],
     [
      "2024-12-17",
      10301.37
     ],
     [
      "2024-12-18",
      10313.18
     ],
     [
      "2024-12-19",
      10320.89
     ],
     [
      "2024-12-23",
      10337.39
     ],
     [
      "2024-12-26",
      10368.99
     ],
     [
      "2024-12-30",
      10399.16
     ],
     [
      "2024-12-31",
      10377.06
     ],
     [
      "2025-01-02",
      10367.32
     ],
     [
      "2025-01-03",
      10350.91
     ],
     [
      "2025-01-06",
      10312.65
     ],
     [
      "2025-01-07",
      10276.93
     ],
     [
      "2025-01-08",
      10283.52
     ],
     [
      "2025-01-09",
      10274.86
     ],
     [
      "2025-01-10",
      10218.31
     ],
     [
      "2025-01-13",
      10209.13
     ],
     [
      "2025-01-14",
      10207.28
     ],
     [
      "2025-01-15",
      10218.29
     ],
     [
      "2025-01-17",
      10230.07
     ],
     [
      "2025-01-20",
      10230.0
     ],
     [
      "2025-01-22",
      10240.8
     ],
     [
      "2025-01-23",
      10245.83
     ],
     [
      "2025-01-24",
      10236.83
     ],
     [
      "2025-01-27",
      10260.83
     ],
     [
      "2025-01-29",
      10260.02
     ],
     [
      "2025-01-30",
      10263.19
     ],
     [
      "2025-01-31",
      10260.53
     ],
     [
      "2025-02-03",
      10265.09
     ],
     [
      "2025-02-04",
      10243.75
     ],
     [
      "2025-02-05",
      10255.94
     ],
     [
      "2025-02-06",
      10233.35
     ],
     [
      "2025-02-07",
      10221.15
     ],
     [
      "2025-02-10",
      10201.04
     ],
     [
      "2025-02-11",
      10150.53
     ],
     [
      "2025-02-12",
      10159.56
     ],
     [
      "2025-02-13",
      10186.34
     ],
     [
      "2025-02-14",
      10195.38
     ],
     [
      "2025-02-17",
      10197.9
     ],
     [
      "2025-02-19",
      10203.09
     ],
     [
      "2025-02-20",
      10209.16
     ],
     [
      "2025-02-24",
      10200.49
     ],
     [
      "2025-02-25",
      10204.56
     ],
     [
      "2025-02-26",
      10201.49
     ],
     [
      "2025-02-27",
      10218.34
     ],
     [
      "2025-02-28",
      10221.49
     ],
     [
      "2025-03-03",
      10177.75
     ],
     [
      "2025-03-04",
      10182.0
     ],
     [
      "2025-03-05",
      10199.64
     ],
     [
      "2025-03-06",
      10201.91
     ],
     [
      "2025-03-07",
      10197.81
     ],
     [
      "2025-03-10",
      10198.15
     ],
     [
      "2025-03-11",
      10213.36
     ],
     [
      "2025-03-12",
      10227.59
     ],
     [
      "2025-03-13",
      10214.1
     ],
     [
      "2025-03-14",
      10216.73
     ],
     [
      "2025-03-17",
      10168.73
     ],
     [
      "2025-03-18",
      10163.12
     ],
     [
      "2025-03-19",
      10114.15
     ],
     [
      "2025-03-20",
      10093.26
     ],
     [
      "2025-03-21",
      10079.13
     ],
     [
      "2025-03-24",
      10088.39
     ],
     [
      "2025-03-25",
      10118.6
     ],
     [
      "2025-03-26",
      10113.35
     ],
     [
      "2025-03-27",
      10122.6
     ],
     [
      "2025-03-28",
      10133.73
     ],
     [
      "2025-03-31",
      10108.03
     ],
     [
      "2025-04-01",
      10117.13
     ],
     [
      "2025-04-02",
      10110.84
     ],
     [
      "2025-04-03",
      10129.98
     ],
     [
      "2025-04-04",
      10102.25
     ],
     [
      "2025-04-07",
      10107.11
     ],
     [
      "2025-04-08",
      10103.9
     ],
     [
      "2025-04-09",
      10101.58
     ],
     [
      "2025-04-10",
      10126.02
     ],
     [
      "2025-04-11",
      10116.65
     ],
     [
      "2025-04-14",
      10085.76
     ],
     [
      "2025-04-15",
      10091.42
     ],
     [
      "2025-04-16",
      10082.54
     ],
     [
      "2025-04-17",
      10073.23
     ],
     [
      "2025-04-21",
      10068.93
     ],
     [
      "2025-04-23",
      10055.09
     ],
     [
      "2025-04-24",
      10058.17
     ],
     [
      "2025-04-25",
      10061.86
     ],
     [
      "2025-04-28",
      10055.11
     ],
     [
      "2025-04-29",
      10014.91
     ],
     [
      "2025-04-30",
      10016.98
     ],
     [
      "2025-05-01",
      10027.27
     ],
     [
      "2025-05-02",
      10058.29
     ],
     [
      "2025-05-05",
      10061.95
     ],
     [
      "2025-05-06",
      10085.98
     ],
     [
      "2025-05-07",
      10085.25
     ],
     [
      "2025-05-08",
      10097.4
     ],
     [
      "2025-05-09",
      10104.87
     ],
     [
      "2025-05-12",
      10181.98
     ],
     [
      "2025-05-14",
      10196.02
     ],
     [
      "2025-05-15",
      10189.05
     ],
     [
      "2025-05-16",
      10173.55
     ],
     [
      "2025-05-19",
      10169.56
     ],
     [
      "2025-05-20",
      10164.17
     ],
     [
      "2025-05-21",
      10160.92
     ],
     [
      "2025-05-22",
      10151.94
     ],
     [
      "2025-05-23",
      10175.72
     ],
     [
      "2025-05-27",
      10188.36
     ],
     [
      "2025-05-28",
      10189.69
     ],
     [
      "2025-05-29",
      10194.59
     ],
     [
      "2025-05-30",
      10197.9
     ],
     [
      "2025-06-02",
      10212.92
     ],
     [
      "2025-06-03",
      10226.66
     ],
     [
      "2025-06-04",
      10244.63
     ],
     [
      "2025-06-05",
      10251.83
     ],
     [
      "2025-06-06",
      10287.39
     ],
     [
      "2025-06-09",
      10273.02
     ],
     [
      "2025-06-11",
      10222.3
     ],
     [
      "2025-06-12",
      10220.15
     ],
     [
      "2025-06-13",
      10225.21
     ],
     [
      "2025-06-16",
      10222.68
     ],
     [
      "2025-06-17",
      10196.18
     ],
     [
      "2025-06-18",
      10199.53
     ],
     [
      "2025-06-19",
      10217.18
     ],
     [
      "2025-06-20",
      10236.13
     ],
     [
      "2025-06-23",
      10220.95
     ],
     [
      "2025-06-24",
      10230.1
     ],
     [
      "2025-06-25",
      10243.22
     ],
     [
      "2025-06-26",
      10240.73
     ],
     [
      "2025-06-27",
      10217.13
     ],
     [
      "2025-06-30",
      10203.2
     ],
     [
      "2025-07-01",
      10202.36
     ],
     [
      "2025-07-02",
      10209.31
     ],
     [
      "2025-07-03",
      10264.87
     ],
     [
      "2025-07-04",
      10254.61
     ],
     [
      "2025-07-07",
      10274.16
     ],
     [
      "2025-07-08",
      10293.22
     ],
     [
      "2025-07-09",
      10294.39
     ],
     [
      "2025-07-10",
      10297.65
     ],
     [
      "2025-07-11",
      10300.54
     ],
     [
      "2025-07-15",
      10367.54
     ],
     [
      "2025-07-16",
      10375.19
     ],
     [
      "2025-07-17",
      10370.03
     ],
     [
      "2025-07-18",
      10335.47
     ],
     [
      "2025-07-21",
      10352.24
     ],
     [
      "2025-07-22",
      10365.05
     ],
     [
      "2025-07-23",
      10360.3
     ],
     [
      "2025-07-24",
      10368.96
     ],
     [
      "2025-07-25",
      10376.65
     ],
     [
      "2025-07-28",
      10388.09
     ],
     [
      "2025-07-29",
      10376.51
     ],
     [
      "2025-07-30",
      10366.49
     ],
     [
      "2025-07-31",
      10393.24
     ],
     [
      "2025-08-01",
      10501.59
     ],
     [
      "2025-08-04",
      10472.75
     ],
     [
      "2025-08-05",
      10476.32
     ],
     [
      "2025-08-06",
      10445.38
     ],
     [
      "2025-08-07",
      10427.85
     ],
     [
      "2025-08-08",
      10441.19
     ],
     [
      "2025-08-11",
      10432.92
     ],
     [
      "2025-08-12",
      10381.33
     ],
     [
      "2025-08-13",
      10410.61
     ],
     [
      "2025-08-14",
      10391.8
     ],
     [
      "2025-08-15",
      10396.56
     ],
     [
      "2025-08-18",
      10413.33
     ],
     [
      "2025-08-19",
      10406.53
     ],
     [
      "2025-08-20",
      10426.65
     ],
     [
      "2025-08-21",
      10469.52
     ],
     [
      "2025-08-22",
      10536.7
     ],
     [
      "2025-08-25",
      10534.98
     ],
     [
      "2025-08-26",
      10524.26
     ],
     [
      "2025-08-27",
      10519.54
     ],
     [
      "2025-08-28",
      10524.9
     ],
     [
      "2025-08-29",
      10503.54
     ],
     [
      "2025-09-02",
      10506.45
     ],
     [
      "2025-09-03",
      10486.23
     ],
     [
      "2025-09-04",
      10507.24
     ],
     [
      "2025-09-05",
      10567.66
     ],
     [
      "2025-09-08",
      10569.97
     ],
     [
      "2025-09-09",
      10560.7
     ],
     [
      "2025-09-10",
      10527.74
     ],
     [
      "2025-09-11",
      10509.25
     ],
     [
      "2025-09-12",
      10514.86
     ],
     [
      "2025-09-15",
      10508.97
     ],
     [
      "2025-09-16",
      10523.7
     ],
     [
      "2025-09-17",
      10489.31
     ],
     [
      "2025-09-18",
      10509.08
     ],
     [
      "2025-09-19",
      10502.5
     ],
     [
      "2025-09-22",
      10501.05
     ],
     [
      "2025-09-23",
      10465.28
     ],
     [
      "2025-09-24",
      10495.52
     ],
     [
      "2025-09-25",
      10557.15
     ],
     [
      "2025-09-26",
      10538.68
     ],
     [
      "2025-09-29",
      10541.31
     ],
     [
      "2025-09-30",
      10553.95
     ],
     [
      "2025-10-01",
      10561.16
     ],
     [
      "2025-10-02",
      10534.84
     ],
     [
      "2025-10-03",
      10520.88
     ],
     [
      "2025-10-06",
      10514.39
     ],
     [
      "2025-10-07",
      10546.38
     ],
     [
      "2025-10-08",
      10542.69
     ],
     [
      "2025-10-09",
      10492.04
     ],
     [
      "2025-10-10",
      10495.13
     ],
     [
      "2025-10-13",
      10499.46
     ],
     [
      "2025-10-15",
      10488.61
     ],
     [
      "2025-10-16",
      10474.42
     ],
     [
      "2025-10-17",
      10452.1
     ],
     [
      "2025-10-20",
      10445.98
     ],
     [
      "2025-10-21",
      10452.58
     ],
     [
      "2025-10-22",
      10448.28
     ],
     [
      "2025-10-23",
      10447.24
     ],
     [
      "2025-10-24",
      10431.58
     ],
     [
      "2025-10-27",
      10403.3
     ],
     [
      "2025-10-28",
      10396.3
     ],
     [
      "2025-10-29",
      10386.36
     ],
     [
      "2025-10-30",
      10413.68
     ],
     [
      "2025-10-31",
      10409.09
     ],
     [
      "2025-11-03",
      10356.91
     ],
     [
      "2025-11-04",
      10359.37
     ],
     [
      "2025-11-05",
      10377.22
     ],
     [
      "2025-11-06",
      10430.35
     ],
     [
      "2025-11-07",
      10417.36
     ],
     [
      "2025-11-10",
      10414.88
     ],
     [
      "2025-11-11",
      10418.86
     ],
     [
      "2025-11-12",
      10417.05
     ],
     [
      "2025-11-13",
      10443.27
     ],
     [
      "2025-11-14",
      10407.19
     ],
     [
      "2025-11-17",
      10431.37
     ],
     [
      "2025-11-18",
      10426.01
     ],
     [
      "2025-11-19",
      10483.97
     ],
     [
      "2025-11-20",
      10482.17
     ],
     [
      "2025-11-21",
      10488.3
     ],
     [
      "2025-11-24",
      10484.93
     ],
     [
      "2025-11-25",
      10507.52
     ],
     [
      "2025-11-26",
      10508.12
     ],
     [
      "2025-11-28",
      10510.54
     ],
     [
      "2025-12-01",
      10518.56
     ],
     [
      "2025-12-02",
      10520.69
     ],
     [
      "2025-12-03",
      10537.91
     ],
     [
      "2025-12-04",
      10554.25
     ],
     [
      "2025-12-05",
      10554.67
     ],
     [
      "2025-12-08",
      10578.55
     ],
     [
      "2025-12-09",
      10612.06
     ],
     [
      "2025-12-10",
      10616.42
     ],
     [
      "2025-12-11",
      10628.11
     ],
     [
      "2025-12-12",
      10630.82
     ],
     [
      "2025-12-15",
      10625.18
     ],
     [
      "2025-12-16",
      10620.3
     ],
     [
      "2025-12-17",
      10617.24
     ],
     [
      "2025-12-18",
      10581.75
     ],
     [
      "2025-12-19",
      10595.54
     ],
     [
      "2025-12-22",
      10601.2
     ],
     [
      "2025-12-23",
      10591.72
     ],
     [
      "2025-12-26",
      10589.48
     ],
     [
      "2025-12-29",
      10594.52
     ],
     [
      "2025-12-30",
      10567.41
     ],
     [
      "2025-12-31",
      10573.09
     ],
     [
      "2026-01-02",
      10551.74
     ],
     [
      "2026-01-05",
      10557.46
     ],
     [
      "2026-01-06",
      10541.63
     ],
     [
      "2026-01-08",
      10510.73
     ],
     [
      "2026-01-09",
      10524.99
     ],
     [
      "2026-01-13",
      10523.91
     ],
     [
      "2026-01-14",
      10589.58
     ],
     [
      "2026-01-15",
      10582.76
     ],
     [
      "2026-01-16",
      10579.08
     ],
     [
      "2026-01-19",
      10577.83
     ],
     [
      "2026-01-20",
      10573.84
     ],
     [
      "2026-01-21",
      10543.92
     ],
     [
      "2026-01-22",
      10526.0
     ],
     [
      "2026-01-23",
      10533.67
     ],
     [
      "2026-01-26",
      10533.47
     ],
     [
      "2026-01-27",
      10542.05
     ],
     [
      "2026-01-28",
      10551.81
     ],
     [
      "2026-01-29",
      10523.01
     ],
     [
      "2026-01-30",
      10524.5
     ],
     [
      "2026-02-02",
      10528.28
     ],
     [
      "2026-02-03",
      10534.62
     ],
     [
      "2026-02-04",
      10541.41
     ],
     [
      "2026-02-05",
      10505.91
     ],
     [
      "2026-02-06",
      10496.0
     ],
     [
      "2026-02-09",
      10500.49
     ],
     [
      "2026-02-10",
      10517.27
     ],
     [
      "2026-02-11",
      10505.34
     ],
     [
      "2026-02-12",
      10487.41
     ],
     [
      "2026-02-13",
      10478.04
     ],
     [
      "2026-02-16",
      10481.59
     ],
     [
      "2026-02-17",
      10458.58
     ],
     [
      "2026-02-18",
      10480.84
     ],
     [
      "2026-02-19",
      10468.19
     ],
     [
      "2026-02-20",
      10445.83
     ],
     [
      "2026-02-23",
      10432.11
     ],
     [
      "2026-02-24",
      10429.55
     ],
     [
      "2026-02-25",
      10439.65
     ],
     [
      "2026-02-27",
      10437.59
     ],
     [
      "2026-03-02",
      10455.62
     ],
     [
      "2026-03-03",
      10469.13
     ],
     [
      "2026-03-04",
      10470.78
     ],
     [
      "2026-03-05",
      10481.72
     ],
     [
      "2026-03-06",
      10434.33
     ],
     [
      "2026-03-10",
      10402.92
     ],
     [
      "2026-03-11",
      10382.52
     ],
     [
      "2026-03-12",
      10370.14
     ],
     [
      "2026-03-13",
      10366.22
     ],
     [
      "2026-03-16",
      10380.52
     ],
     [
      "2026-03-17",
      10359.89
     ],
     [
      "2026-03-18",
      10356.79
     ],
     [
      "2026-03-19",
      10463.76
     ],
     [
      "2026-03-20",
      10478.23
     ],
     [
      "2026-03-23",
      10475.55
     ],
     [
      "2026-03-24",
      10475.63
     ],
     [
      "2026-03-25",
      10483.48
     ],
     [
      "2026-03-26",
      10453.52
     ],
     [
      "2026-03-27",
      10463.35
     ],
     [
      "2026-03-30",
      10466.73
     ],
     [
      "2026-03-31",
      10485.34
     ],
     [
      "2026-04-01",
      10479.31
     ],
     [
      "2026-04-02",
      10476.25
     ],
     [
      "2026-04-03",
      10459.67
     ],
     [
      "2026-04-06",
      10441.55
     ],
     [
      "2026-04-07",
      10416.57
     ],
     [
      "2026-04-08",
      10414.75
     ],
     [
      "2026-04-09",
      10425.91
     ],
     [
      "2026-04-10",
      10382.27
     ],
     [
      "2026-04-13",
      10329.09
     ],
     [
      "2026-04-14",
      10339.02
     ],
     [
      "2026-04-15",
      10306.44
     ],
     [
      "2026-04-16",
      10318.65
     ],
     [
      "2026-04-17",
      10377.39
     ],
     [
      "2026-04-20",
      10381.24
     ],
     [
      "2026-04-21",
      10414.18
     ],
     [
      "2026-04-23",
      10395.67
     ],
     [
      "2026-04-24",
      10411.86
     ],
     [
      "2026-04-27",
      10407.27
     ],
     [
      "2026-04-28",
      10412.15
     ],
     [
      "2026-04-29",
      10462.25
     ],
     [
      "2026-04-30",
      10613.3
     ],
     [
      "2026-05-01",
      10600.17
     ],
     [
      "2026-05-05",
      10621.96
     ],
     [
      "2026-05-07",
      10609.43
     ],
     [
      "2026-05-08",
      10622.44
     ],
     [
      "2026-05-14",
      10570.32
     ],
     [
      "2026-05-15",
      10566.5
     ],
     [
      "2026-05-18",
      10554.42
     ],
     [
      "2026-05-19",
      10501.12
     ],
     [
      "2026-05-20",
      10468.52
     ],
     [
      "2026-05-21",
      10477.37
     ],
     [
      "2026-05-22",
      10471.04
     ],
     [
      "2026-05-25",
      10464.12
     ],
     [
      "2026-05-26",
      10485.31
     ],
     [
      "2026-05-27",
      10506.07
     ],
     [
      "2026-05-28",
      10540.3
     ],
     [
      "2026-05-29",
      10541.4
     ],
     [
      "2026-06-01",
      10568.2
     ],
     [
      "2026-06-02",
      10587.82
     ],
     [
      "2026-06-03",
      10530.85
     ],
     [
      "2026-06-05",
      10467.49
     ],
     [
      "2026-06-08",
      10481.65
     ],
     [
      "2026-06-10",
      10487.39
     ],
     [
      "2026-06-12",
      10480.86
     ],
     [
      "2026-06-16",
      10483.12
     ],
     [
      "2026-06-18",
      10431.32
     ],
     [
      "2026-06-22",
      10381.22
     ],
     [
      "2026-06-23",
      10373.0
     ],
     [
      "2026-06-24",
      10380.73
     ],
     [
      "2026-06-25",
      10364.47
     ],
     [
      "2026-06-26",
      10348.14
     ],
     [
      "2026-06-29",
      10360.54
     ],
     [
      "2026-06-30",
      10366.15
     ],
     [
      "2026-07-01",
      10375.1
     ],
     [
      "2026-07-02",
      10399.06
     ],
     [
      "2026-07-03",
      10382.88
     ],
     [
      "2026-07-06",
      10385.07
     ],
     [
      "2026-07-07",
      10372.47
     ],
     [
      "2026-07-08",
      10381.65
     ],
     [
      "2026-07-09",
      10375.15
     ],
     [
      "2026-07-13",
      10374.96
     ],
     [
      "2026-07-14",
      10400.02
     ],
     [
      "2026-07-15",
      10388.38
     ],
     [
      "2026-07-16",
      10403.74
     ],
     [
      "2026-07-17",
      10384.39
     ],
     [
      "2026-07-20",
      10348.93
     ],
     [
      "2026-07-21",
      10462.52
     ],
     [
      "2026-07-22",
      10447.56
     ],
     [
      "2026-07-23",
      10572.87
     ],
     [
      "2026-07-24",
      10566.98
     ],
     [
      "2026-07-27",
      10538.47
     ],
     [
      "2026-07-28",
      10540.87
     ],
     [
      "2026-07-29",
      10540.64
     ],
     [
      "2026-07-30",
      10811.55
     ],
     [
      "2026-08-04",
      10802.93
     ],
     [
      "2026-08-05",
      10786.12
     ],
     [
      "2026-08-06",
      10820.92
     ],
     [
      "2026-08-07",
      10832.2
     ],
     [
      "2026-08-11",
      10826.25
     ],
     [
      "2026-08-12",
      10824.24
     ],
     [
      "2026-08-13",
      10824.07
     ],
     [
      "2026-08-14",
      10831.26
     ],
     [
      "2026-08-17",
      10811.48
     ],
     [
      "2026-08-18",
      10799.85
     ],
     [
      "2026-08-19",
      10847.87
     ],
     [
      "2026-08-20",
      10847.23
     ],
     [
      "2026-08-21",
      10834.22
     ],
     [
      "2026-08-24",
      10845.61
     ],
     [
      "2026-08-25",
      10832.73
     ],
     [
      "2026-08-26",
      10841.55
     ],
     [
      "2026-08-27",
      10834.2
     ],
     [
      "2026-08-28",
      10864.63
     ],
     [
      "2026-08-31",
      10864.79
     ],
     [
      "2026-09-01",
      10873.96
     ],
     [
      "2026-09-02",
      10900.47
     ],
     [
      "2026-09-04",
      10894.06
     ],
     [
      "2026-09-07",
      10971.02
     ],
     [
      "2026-09-09",
      10971.31
     ],
     [
      "2026-09-10",
      10979.45
     ],
     [
      "2026-09-11",
      11003.13
     ],
     [
      "2026-09-14",
      11014.23
     ],
     [
      "2026-09-15",
      11019.39
     ],
     [
      "2026-09-16",
      11013.06
     ],
     [
      "2026-09-17",
      11008.79
     ],
     [
      "2026-09-18",
      11010.19
     ],
     [
      "2026-09-21",
      11024.15
     ],
     [
      "2026-09-22",
      10992.76
     ],
     [
      "2026-09-23",
      11025.16
     ],
     [
      "2026-09-24",
      11042.0
     ],
     [
      "2026-09-25",
      11070.25
     ],
     [
      "2026-09-28",
      11056.34
     ],
     [
      "2026-09-29",
      10996.08
     ]
    ],
    "by_year": {
     "2024": 377.06,
     "2025": 196.03,
     "2026": 422.99
    },
    "by_month": {
     "2024-01": -78.42,
     "2024-02": 20.92,
     "2024-03": -27.82,
     "2024-04": 14.89,
     "2024-05": -218.18,
     "2024-06": 153.73,
     "2024-07": 228.51,
     "2024-08": 160.41,
     "2024-09": -123.22,
     "2024-10": 105.6,
     "2024-11": 23.19,
     "2024-12": 117.45,
     "2025-01": -116.53,
     "2025-02": -39.04,
     "2025-03": -113.46,
     "2025-04": -91.05,
     "2025-05": 180.92,
     "2025-06": 5.3,
     "2025-07": 190.04,
     "2025-08": 110.3,
     "2025-09": 50.41,
     "2025-10": -144.86,
     "2025-11": 101.45,
     "2025-12": 62.55,
     "2026-01": -48.59,
     "2026-02": -86.91,
     "2026-03": 47.75,
     "2026-04": 127.96,
     "2026-05": -71.9,
     "2026-06": -175.25,
     "2026-07": 445.4,
     "2026-08": 53.24,
     "2026-09": 131.29
    },
    "by_symbol": {
     "USDJPY": 996.08
    },
    "worst_day": {
     "day": "2024-05-23",
     "pct": -0.91
    },
    "months_positive": 20,
    "months": 33,
    "return_pct": 9.96
   },
   "expected": {
    "symbol": "USDJPY",
    "from": "2024-01-01",
    "to": "2026-10-01",
    "deposit": 10000,
    "trades": 777,
    "win_rate": 47,
    "profit_factor": 1.14,
    "return_pct": 8.6,
    "eq_dd_max_pct": 5.0
   }
  },
  {
   "name": "2026-10-17_0056_AurumBreakout_USDJPY",
   "state": "no report (run killed or still going)"
  },
  {
   "name": "2026-10-15_funded_phase2",
   "job": {},
   "summary": "# AurumFunded, FTMO phase 2 preset, Strategy Tester (FTMO-Demo)\n\nRun by the owner on 2026-10-15: XAUUSD M15, 2024-01-01 to 2026-10-14, real ticks, 10,000 USD, 1:33, inputs of\n`AurumFunded_FTMO_phase2.set` (target 5%, round 2, size 0.5). Same start date as the phase 1 run, so it overlaps\nthat run's first weeks rather than following on from 2024-10-25.\n\nResult: **phase passed on 2024-02-20**, +500.85 (5.0%) after 36 trading days with a deal, 77 trades. Equity drawdown\nat most 1.89%, worst day -0.83% (2024-01-19). Profit factor 2.15.\n\n| Leg | Trades | Net USD |\n|---|---|---|\n| after holiday | 10 | +266.4 |\n| bell | 5 | +89.4 |\n| after fix | 5 | +55.2 |\n| midday | 35 | +55.1 |\n| Tokyo | 10 | +35.5 |\n| dip | 1 | +14.1 |\n| morning | 3 | +6.8 |\n| fix | 8 | -21.8 |\n\nOver the shared weeks it trades as the phase 1 run did (January 2024 +379 against +381). A run started at\n2024-10-25, where phase 1 ended, is still to do.\n",
   "state": "done"
  },
  {
   "name": "2026-10-15_funded_phase1",
   "job": {},
   "summary": "# AurumFunded, FTMO phase 1 preset, Strategy Tester (FTMO-Demo, build 6230)\n\nRun by the owner on 2026-10-15: XAUUSD M15, 2024-01-01 to 2026-10-14, every tick based on real ticks (99% real\nticks), random delay, 10,000 USD, 1:33, inputs of `AurumFunded_FTMO_phase1.set` (size 0.5, target 10%, day stop 3%,\nfinal stop 8.5%). The phase preset stops the test at the target.\n\nResult: **phase passed on 2024-10-25**, +1,000.17 (10.0%) after 199 trading days with a deal, 534 trades.\nEquity drawdown at most 4.70% (balance 4.37%); worst day -1.6% (2024-07-25); the 3% day stop was never hit.\nCommission 489 USD (FTMO charges 2.50 USD a lot a side on currencies, 0.46 bp a round trip on EUR/USD; 1.61 a lot\na side on gold), no swap (nothing held overnight).\n\nBy leg, % of the starting balance, against the Python model (`marketdata/hydra_legs_daily.csv.gz` x 0.5) on the\nsame dates, 2024-01-01 to 2024-10-25:\n\n| Leg | Trades | Tester | Model |\n|---|---|---|---|\n| dip | 10 | +2.53 | quartet +10.23 (dip, bell, Tokyo, midday) |\n| bell | 43 | +0.72 | |\n| Tokyo | 54 | -0.05 | |\n| midday | 198 | +1.30 | |\n| fix + after fix (incl. yen crosses) | 104 | +2.70 | fix +3.10, cross -0.16 |\n| stock fall | 40 | -1.05 | -0.80 |\n| morning | 45 | +0.42 | +0.13 |\n| after holiday | 40 | +3.44 | +3.41 |\n| total | 534 | +10.00 | +15.92 (model reached 10% on 2024-06-28) |\n\nThe dip entries fall on the model's minutes (2024-01-29 01:45, 04-05 04:30, 04-23 04:45, 04-25 06:15, 05-24 05:30),\nso the server clock and the gold leg agree with the model. The month-end, holiday, fall and morning legs agree too.\nThe bell, Tokyo and midday legs together earned +2.0% against a model share of about 7%; commission explains under\n1% of that (FTMO's is below the 0.85 bp the model charges). Open: test those three legs alone, once with zero\nlatency and once with random delay, to see whether the gap is delay, spread at the entry minute or the period.\n",
   "state": "done"
  },
  {
   "name": "2026-10-15_funded_account",
   "job": {},
   "summary": "# AurumFunded, FTMO funded-account preset, Strategy Tester (FTMO-Demo)\n\nRun by the owner on 2026-10-15: XAUUSD M15, 2024-01-01 to 2026-10-14, real ticks, 10,000 USD, 1:33, inputs of\n`AurumFunded_FTMO_funded.set` (no target, size 0.5, day stop 3%, final stop 8.5%). Sizes follow the balance, so the\nresult compounds.\n\nResult: **+11,053.77 (+110%) in 34 months**, 1,760 trades on 667 days, profit factor 1.63. Equity drawdown at most\n4.08% (balance 3.05%). Worst day -1.64% of the day's starting balance (2026-01-20); no day below -2%, so the 3% day\nstop and FTMO's 5% were never near. 23 of 34 months positive, worst month -2.09%, median +2.14%, mean +2.25%.\nBy year: 2024 +2,018, 2025 +6,698, 2026 to 10-13 +2,338.\n\n| Leg | Trades | Net USD | Commission |\n|---|---|---|---|\n| fix | 224 | +2,290.2 | -99.5 |\n| dip | 50 | +2,229.2 | -12.2 |\n| Tokyo | 179 | +1,859.8 | -466.5 |\n| after holiday | 150 | +1,287.5 | -138.4 |\n| midday | 664 | +1,098.4 | -954.1 |\n| bell | 99 | +807.2 | -122.5 |\n| stock fall | 95 | +770.6 | -50.0 |\n| morning | 156 | +652.0 | -87.5 |\n| after fix | 143 | +58.7 | -110.2 |\n\nAgainst the Python model of the same legs at size 0.5 on the same dates (`marketdata/hydra_legs_daily.csv.gz`):\n+189% compounded (simple sum +108%). The tester keeps about 70% of the model's log growth (ln 2.10 against ln 2.89).\nOn an FTMO 100k funded account at the 80% split, the average month here would pay about 1,800 USD before the\nscaling plan, with the worst month at -2.1%.\n",
   "state": "done"
  }
 ],
 "agents": [
  {
   "name": "orchestrator",
   "model": "opus",
   "tools": "all",
   "steps": "1, 3, 18 and every hand-off",
   "description": "The main Claude Code session: picks ideas, hands each step to a role agent, reads the gates' verdicts and keeps the ledger. Asks the owner before anything live."
  },
  {
   "name": "monitor",
   "model": "haiku",
   "tools": "Read, Grep, Glob, Bash, PowerShell, Write",
   "description": "Daily check-in on the FTMO demo forward test and, later, live monitoring. Pipeline steps 17 and 20. Use on a schedule to compare demo trades with the tester and flag any rule hit.",
   "steps": "17 and 20"
  },
  {
   "name": "quant-coder",
   "model": "sonnet",
   "tools": "Read, Grep, Glob, Bash, Edit, Write",
   "description": "Writes Python backtests in research/ and MQL5 EAs in mql5/. Pipeline steps 5, 6, 7, 11, 12, 13, 14. Use for data checks, prototyping a rule, cost stress runs, goal simulations, and building or merging an EA leg.",
   "steps": "5, 6, 7, 11, 12, 13, 14"
  },
  {
   "name": "researcher",
   "model": "haiku",
   "tools": "Read, Grep, Glob, Bash, WebSearch, WebFetch",
   "description": "Finds candidate edges (papers, market structure) and fetches market data. Pipeline steps 2 and 4. Use when the orchestrator needs a list of new ideas checked against the rejected list, or a data set downloaded.",
   "steps": "2 and 4"
  },
  {
   "name": "reviewer",
   "model": "opus",
   "tools": "Read, Grep, Glob, Bash",
   "description": "Independent read-only review of a candidate at gates 8-11 and of every EA change before it is merged. Use with a fresh context; it must not be the agent that built the work.",
   "steps": ""
  },
  {
   "name": "tester-operator",
   "model": "sonnet",
   "tools": "Read, Grep, Glob, Bash, PowerShell, Write",
   "description": "Runs MT5 Strategy Tester jobs on Terminal 16 (FTMO demo) and parses the reports. Pipeline steps 15 and 16. Use to launch one tester run, collect its report, and compare it with the expected figures.",
   "steps": "15 and 16"
  }
 ],
 "book": {
  "legs": [
   "quartet",
   "grid",
   "hold",
   "fix",
   "cross",
   "fall",
   "morning",
   "after"
  ],
  "weights": {
   "breakout": 1.0,
   "noise": 0.6088017801888469
  },
  "since": "2018-01-01",
  "sharpe": {
   "Hydra book": 3.371,
   "+ breakout": 3.428,
   "+ noise": 3.558,
   "+ breakout + noise": 3.614
  }
 },
 "demo": {
  "today": {
   "day": "2026-10-17",
   "alert": false,
   "experts_lines": 1,
   "orders_by_leg": {},
   "journal_trade_lines": 0,
   "day_stop": [],
   "final_stop": [],
   "failed": [],
   "phase": [
    "AurumFunded: phase 1 started, initial balance 10000.00, target 11000.00, day stop 300.00, final stop at 9150.00"
   ],
   "skipped": [],
   "clock": [],
   "last_lines": [
    "AurumFunded: phase 1 started, initial balance 10000.00, target 11000.00, day stop 300.00, final stop at 9150.00"
   ],
   "logs_found": [
    "20261017.log",
    "20261017.log"
   ]
  },
  "log": "# Demo log\n\n## 2026-10-17 (Saturday)\n\n- Trades per leg: not logged (0 EA lines, 0 orders, 0 journal trade lines).\n- P/L of the day: not logged.\n- Slippage on fills: not logged (no fills).\n- Day stop / final stop / margin error / trades without broker stop: none in the log.\n- Odd: no trades logged; EA not attached? Saturday, so the forex market is closed and zero activity is expected; the log file 20261017.log exists. Tester window open until 2026-10-18 18:00, Terminal 16 reported running.\n\n\n"
 }
};
