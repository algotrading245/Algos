# Autopilot runs

One line per unattended agent run (tools/autopilot). Full output is in the local `logs/autopilot/` folder (not
committed).

| When | Agent | Task | Result |
|---|---|---|---|
| 2026-10-17 04:50 | owner session | Attached AurumFunded (phase 1 preset) to the FTMO demo in Terminal 16; backed up and linked its AurumFunded folder; approved a1, queued j3; set the j4 release rule | done |
| 2026-10-17 04:53 | owner session | Replaced the fixed Orchestrator/Tester/Researcher tasks with the agent relay (hand-over 15 min after each run, daily caps) | installed |
| 2026-10-17 04:57 | tester | Held Terminal 16 closed; started j1 (AurumNoise US500.cash M1) detached, pid 1584 | running |
| 2026-10-17 05:00 | tester | Collected j1 (US500: -0.68%, 26.09% eq DD, PF 1.00, 452 trades); wrote summary.md; started j2 (AurumNoise US100.cash M1) detached, pid 10092 | j1 done, j2 running |
| 2026-10-17 05:08 | tester | Collected j2 (US100: +39.93%, 16.41% eq DD, PF 1.18, 697 trades); wrote summary.md; started j3 base run (AurumFunded XAUUSD M15, legs off, tag funded_off) detached, pid 2620 | j2 done, j3 running |
| 2026-10-17 05:25 | orchestrator | Judged j1 (US500 -0.68%/26.1% vs +1.3%/28.6%) and j2 (US100 +39.9%/16.4% vs +44.7%/18.5%); noise to step 16; released j4 (AurumHydra) | j4 queued |
| 2026-10-17 05:36 | tester | Collected j3 base (funded_off: +167.68%, 6.67% eq DD, PF 1.60, 1737 trades, day stop hit 17 times); wrote summary.md; started j3 legs-on run (tag funded_on) detached, pid 2736 | j3 off done, j3 on running |
| 2026-10-17 05:58 | orchestrator | Judged j3 base (+167.7%/6.67%/17 day stops vs stale v1.00 expectation +110%/4.1%): gap is the 1.4 cushion cap of 1.01 (model +331%/7.2%, tester keeps 67% of log growth); set the legs-on expectation to ~+185-190%, 7.5-8% DD (research/funded_tester_gap.py) | matches, j3 on still running |
| 2026-10-17 06:18 | tester | Collected j3 legs-on (funded_on: +221.48%, 8.28% eq DD, PF 1.50, 21 day stops vs 17 off); wrote summary.md; started j4 base run (tag 5x_off) detached, pid 7928 | j3 done, j4 off running |
| 2026-10-17 06:27 | tester | Collected j4 base (5x_off: +9.47%, 14.98% eq DD, PF 1.58, 32 trades, round ended 2024-02-01); wrote summary.md; started j4 legs-on run (tag 5x_on) detached, pid 15008 | j4 off done, j4 on running |
| 2026-10-17 06:36 | tester | Collected j4 legs-on (5x_on: +14.79%, 25.84% eq DD, PF 1.32, 49 trades, worst day -8.5% vs off +9.47% / 14.98%); wrote summary.md; queue empty, released Terminal 16 | j4 done, needs judging |
| 2026-10-17 07:10 | orchestrator | Judged j3 legs-on (+221.5%/8.28% vs ~+185-190%/7.5-8%, return per DD 25.1 -> 26.7: both legs pass step 16 in AurumFunded) and j4 (set-up fault: 12 of 16 symbols on another broker's names, one goal round at 100); new preset AurumHydra_FTMO_size1.set, queued j5 (research/hydra_tester_expect.py), added a3 (owner: legs on in the demo?) | j5 queued |
| 2026-10-17 07:06 | tester | Held Terminal 16; started j5 base run (size1_off, legs off) detached, pid 15288 | j5 off running |
| 2026-10-17 08:27 | tester | Collected j5 base (size1_off: +1460.44%, 13.11% eq DD, PF 1.53, 4174 trades, 14 symbols traded); wrote summary.md; started j5 legs-on run (size1_on) detached, pid 14548 | j5 on running |
| 2026-10-17 09:46 | tester | Collected j5 legs-on (size1_on): identical to the off run to the cent (+1460.44%, 13.11% eq DD, 4174 trades); both reports list InpBreakRiskPct=0.5, so the off run likely inherited j4's leg values; wrote summary.md, j5 done; queue empty, terminal released | j5 done, no valid off/on pair, needs judging |
| 2026-10-17 10:05 | orchestrator | Judged j5: both runs inherited j4's inputs the preset left out (legs 0.5/0.275, month-end boost 2, no 35% halt), so +1460.4%/13.11% twice is legs on + boost, no valid pair; pinned those inputs at the EA defaults in AurumHydra_FTMO_size1.set; checked j3's inputs clean; queued j6; proposed run-tester.ps1 fill all EA defaults (HANDOFF) | j6 queued |
| 2026-10-17 10:11 | tester | Closed Terminal 16 (hold), started j6 base run (size1b_off, legs off) detached, pid 13948 | j6 off running |
| 2026-10-17 11:16 | tester | Collected j6 off run (inputs 0/0/1.0/35 verified): +725.13%, 12.48% eq DD, PF 1.70, 2262 trades, return per DD 58.1, no US100/US500 trades; wrote summary.md; held terminal, started legs-on run (size1b_on, 0.5/0.275) detached, pid 1292 | j6 on running |
| 2026-10-17 12:35 | tester | Collected j6 on run (inputs 0.5/0.275/1.0/35 verified): +1076.18%, 15.54% eq DD, PF 1.49, 4173 trades, return per DD 69.2 vs 58.1 off; wrote summary.md; queue empty, released Terminal 16 | j6 done, needs judging |
| 2026-10-17 13:10 | orchestrator | Judged j6 (AurumHydra size 1: off +725.1%/12.48% -> on +1076.2%/15.54%, return per DD 58.1 -> 69.2, 83%/87% of the model's log growth): both legs pass step 16 in Hydra; legs-on deepest month 2026-01 (noise -3.9, breakout -1.0 pts), legs offset 2024-07; j5's +1460% was the month-end boost (re-weighting, not adopted); research/hydra_j6_compare.py; both candidates to step 17, a3 updated | step 16 passed, step 17 waits on owner (a3), queue empty |
| 2026-10-17 13:40 | orchestrator | No alert, no unjudged run, no candidate at steps 5-14, no docs/ideas/: refreshed stale HANDOFF parts (current state, EA 2 tester status, "uncompiled" wording on the legs) and noted why a 5x series on FTMO data is not queued (1:500-broker result exists, no `to` in jobs, FTMO margins) | handoff refreshed, researcher next |
| 2026-10-17 15:45 | tester | Held Terminal 16 (hold shown until 2026-10-18T01:45), started j7 months series 2025.01-2026.09 (21 runs, 10,000 at 1:500, 5x preset) in backtests/2026-10-17_1545_AurumHydra_5x_months | j7 running |
| 2026-10-17 15:50 | tester | Held Terminal 16, restarted j7 months series 2025.01-2026.09 (21 runs) in backtests/2026-10-17_1550_AurumHydra_5x_months (after the run-months fix) | j7 running |
| 2026-10-17 15:55 | tester | Collected j7 months series (backtests/2026-10-17_1550_AurumHydra_5x_months) | running: 8 of 21 months done |
| 2026-10-17 16:00 | tester | Collected j7 months series: tags chain across months (run-months.ps1 line 88 overwrites $Tag), paths too long from 2025.12, months_summary.py crashes (deposit 0). No new job started | j7 failed, needs script fix and requeue |
| 2026-10-17 16:20 | orchestrator | Judged j7: besides the tag chain, the 5x preset kept the .pc symbol names, so every month stopped at OnInit (XAUUSD.pc not available) and the reports are empty; new preset AurumHydra_5x_month_FTMO.set (16 FTMO names), queued j8a-c (2025.01-2026.09 in three 7-month parts, tags 5xA/B/C to stay under the path limit); run-months.ps1 fix described in HANDOFF | j8a-c queued |
| 2026-10-17 16:25 | tester | Held Terminal 16, started j8a (5x months 2025.01-2025.07, tag 5xA) detached | running, folder backtests/2026-10-17_1625_AurumHydra_5xA_months |
| 2026-10-17 16:30 | tester | Collected j8a: running, 1 of 7 months done | still running, nothing committed |
| 2026-10-17 16:35 | tester | Collected j8a: running, 2 of 7 months done | still running, nothing committed |
| 2026-10-17 16:40 | tester | Collected j8a: running, 4 of 7 months done | still running, nothing committed |
| 2026-10-17 16:45 | tester | Collected j8a: running, 5 of 7 months done | still running, nothing committed |
| 2026-10-17 21:45 | tester (by hand) | Collected j8a (0/7 months at 5x, median 0.75x); started j8b, 7 months | j8b running |
| 2026-10-17 21:51 | owner session | Removed the relay's daily run caps (owner's request); one agent at a time, the hand-over gap and the usage back-off still apply | relay updated |
