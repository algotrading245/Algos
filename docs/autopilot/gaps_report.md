# Gaps report - 2026-10-23 (first report, written by the owner's Opus session; the doctor replaces it daily from 07:00)

Health: **amber** - the loop runs (keeper and relay logging, builder working), but the finder produces nothing usable
and the demo runs an old EA build.

## Fixed this run
- Relay data loop: a data item that never resolved was picked again every 5 min. Now capped at 3 tries
  (`logs/autopilot/data-tries.json`, `$DataTryCap` in tools/autopilot/common.ps1); stuck items are logged and skipped.
- Finder prompt: step 2 now requires `python tools/gaps.py` and docs/ideas/steer.md first; "nothing new found" is
  allowed only after 3 new gap-aimed sources, each logged in sources.jsonl (tools/autopilot/prompts/finder.md).
- No gap-finding agent existed: created the doctor (.claude/agents/doctor.md, Opus, daily 07:00), wired in
  router.json, run-agent.ps1 and install.ps1.

## Open, for Opus
1. FIXED 2026-10-23: Aurum Doctor registered (install.ps1 run at the owner's request), daily 07:00.
2. Idea-engine spec factory inflates the multiple-testing N (~27k), so the luck bar is 1.00 and every factory spec
   fails. Fix: count factory variants per family, not per spec, in the N the gate uses (gate change - owner approval).
3. FIXED 2026-10-23 01:45: T16 restarted with AurumFunded 1.10 (trades as 1.09) and phase1_legs.set; a4 applied.
4. Breakout leg skips on the demo: the 0.01-lot floor needs a bigger balance. Fix: scale the leg's risk to the
   balance or switch it off on small accounts (EA change - reviewer).
5. demo_check counts noise-leg orders as "other". Fix: add the noise leg's magic number to the demo_check map.
6. Fidelity check due 2026-10-23 cannot run: firm-day lines, P/L and slippage are not logged. Fix: have the monitor
   write them in docs/demo_log.md each check-in.
7. `memory.py decide` refused on 2026-10-19 (long command lines, probably a deny-pattern match). Fix: check
   tools/autopilot/settings.json patterns against the decide call; the doctor prompt now asks for short arguments.
8. Old role names (orchestrator) still appear in the logs and some docs. Fix: rename in the log writers.

## Watching
- Finder empty_streak: 66 (owner's choice: no brake). Now gap-aimed; check whether it drops after the prompt change.
- Budget: $148 of $100 this week (information only; weekly limit hit on 2026-10-20).
- Portfolio manager has never run; first run Saturday 2026-10-24 writes steer.md.
