# Demo log

## 2026-10-17 (Saturday)

- Trades per leg: not logged (0 EA lines, 0 orders, 0 journal trade lines).
- P/L of the day: not logged.
- Slippage on fills: not logged (no fills).
- Day stop / final stop / margin error / trades without broker stop: none in the log.
- Odd: no trades logged; EA not attached? Saturday, so the forex market is closed and zero activity is expected; the log file 20261017.log exists. Tester window open until 2026-10-18 18:00, Terminal 16 reported running.

## 2026-10-19 (Monday) — ALERT: demo EA not attached

- Found by the orchestrator at 07:36 local. AurumFunded is on no chart of Terminal 16 and has not been since
  2026-10-17 04:57:06 (journal: "expert AurumFunded (XAUUSD,M15) removed"). It had loaded at 04:33:55 that day.
- After that the terminal ran tester configs until 2026-10-18 01:20:43. The keeper then restarted it plain at 01:24:53
  ("Terminal 16: started", not "started, AurumFunded attached"). The journal has no Experts line after that start.
  It logged in to the demo with 0 positions and 0 orders, and it showed 0 positions again on the 23:01 reconnect.
- The saved charts (Profiles/Charts/Default chart01-04.chr, written 2026-10-18 01:20:40) contain no `<expert>`
  block. The EA log (MQL5/Logs) exists only for 20261017. demo_check for 2026-10-19 reports "ok" with 0 EA lines.
- Result: no demo trading since Saturday. The clean out-of-sample demo test due to start today has not started.
  Agents may not attach an EA, so the owner has to re-attach it (HANDOFF "Waiting on the owner", approvals a4).
- Likely cause: the keeper copy that ran at 01:24 had been started on 10-17, before the attach branch was added to
  keeper.ps1, so it ran the old code. The attach check also runs only while Terminal 16 is closed, so a terminal
  that stays open without the EA is never caught.


