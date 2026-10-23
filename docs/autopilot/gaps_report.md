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
2. FIXED 2026-10-23 (owner approved in chat, a5): tools/gates.py trials_logged counts spec-factory specs once per
   rule family (6 families). N 27129 -> 26710; the luck bar stays 1.00. Found on the way: the factory was not the
   cause. Its 135 lines were only 438 of N; edge_scan's two searches are 25960 of it. And factory specs fail at the
   halves gate (143 of 146), not at dsr; the book's DSR is 1.000. Counting edge_scan per search would be a separate
   gate change (owner).
3. FIXED 2026-10-23 01:45: T16 restarted with AurumFunded 1.10 (trades as 1.09) and phase1_legs.set; a4 applied.
4. Breakout leg skips on the demo only on wide-range days (checked 2026-10-23). With the demo preset (size 0.5,
   0.125% per side) the 01:00-09:00 range in 2023 to 2025-10-12 needs EUR 3.9k at the median day, 8.2k at p90,
   9.9k at p95 and 18.8k at the widest. So 10k trades on about 95% of days and a 25k account trades on every day.
   The one skip in the T16 log was a 1.181 JPY stop (it needs about 10.6k). Open, small: the EA logs a placed
   breakout order as "failed, retcode 10009", but 10009 means done (EA log fix - reviewer).
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
