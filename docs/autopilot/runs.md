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
