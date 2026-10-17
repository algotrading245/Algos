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
