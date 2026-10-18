# Lessons

What the project learned the hard way, so no run repeats it. At most 40. Rules:

- Each lesson is one rule plus `Evidence:` (a file, job or commit) and the date it was learned.
- Only the orchestrator adds, changes or removes a lesson, and only after the reviewer subagent agreed that the
  evidence supports it. Other agents propose one with `python tools/memory.py decide --kind lesson ...`.
- At 40, merge or drop the weakest before adding. A lesson that later evidence contradicts is removed, with a
  decision line saying why.
- A lesson never overrides `docs/memory/mission.md`.

## Strategy Tester

1. **Every input must be written, or the tester reuses the last run's value.** j5's off and on runs came out identical
   to the cent because the preset left the legs, boost and halt inputs out. Check the input list in the report before
   judging any run. Evidence: j5/j6 in `docs/HANDOFF.md`; `tools/run-tester.ps1` now writes source defaults first.
   (2026-10-17)
2. **Presets must use the broker's own symbol names.** j4 traded only 3 of 16 symbols and j7's months all stopped at
   OnInit because the presets kept another broker's `.pc` / `.r` names. Evidence: j4, j7. (2026-10-17)
3. **The tester install needs one owner login before any job starts.** j10/j11 failed without it; the relay now
   waits for the login instead. Evidence: j10/j11 notes in `docs/autopilot/queue.json`. (2026-10-18)
4. **The tester keeps about 67-87% of the Python model's log growth.** Judge a run against that range, not against
   the raw model figure: Funded runs 67-74% (j3), Hydra at size 1 83-87% (j6). Evidence: j3, j6. (2026-10-17)
5. **One goal round says little about the 5x EA; it needs separate fresh-deposit months.** j4's 5x preset stopped
   after January 2024. Evidence: j4, then j8a-c via `tools/run-months.ps1`. (2026-10-17)
6. **Keep each month series short enough for the chained tags.** j7 broke at an 86-character tag; 52 works. Evidence: j7, j8. (2026-10-17)
19. **The goal model has no margin; the tester has the broker's stop-out.** At goal sizes 30-50, the gold hold
    (`Legs.mqh:957`) and the AUDCAD grid (`Legs.mqh:797`), both scaled by `SizeMult()`, carry nearly all of the loss
    when an intraday move takes the margin level below 50% (deal comment `so 4x.xx%`). The tester closes everything at
    that price and ends the test. That ended 7 / 10 / 9 of the 21 single-month runs at 3x / 4x / 5x, at a median 0.5x;
    2 / 4 / 3 of them were months the model reaches. Tester "ruin 0" hides these stop-outs; judge goal odds against a
    model with margin. Evidence: `research/hydra_goal_202410_compare.py`, `research/hydra_stopout_scan.py`.
    (2026-10-18)

## Strategy and data

7. **The 5x goal mode reaches 5x in 1-2 of 21 tester months; judge it against 11-25%, not ~40-47%.** j8 gave 1/21
   (2025.01-2026.09), j10b 2/21 (2024.01-2025.09). `tools/target_odds.py` gives P(5x) 17% at edge 0.7 and 25% at
   edge 1.0 (5x target, scale 2.5, every weekday a round); month-start rounds give 11% / 20%. The old 40% matched P(3x)
   at the 3x target and 47% the goal-mode preset. On j10b's own months the model with target_odds' settings gave 5-9
   of 21 at 5x with 14-24% ruin; the tester gave 2 with no ruin (lowest 0.36x). On the preset-settings model, broker
   stop-outs account for 3 of its 11 months at 5x (lesson 19); the rest of the gap is not measured. 2024 also gave only 1 of 12, so 2025-26 gold volatility is not the whole cause, though j9's gold-hold
   evidence stands. A fix is a new idea through the gates on data from 2010, never a setting picked on tester months.
   Evidence: j8a-c, j9, j10b, `research/hydra_t5b_months_model.py`. (2026-10-18)
8. **The gold spread cap (`InpGoldMaxSpread` 0.30) works as an unplanned volatility filter; lifting it made the months
   worse.** Evidence: j9 (0.34x / 0.49x / 0.57x against 1.33x / 0.91x / 0.72x). (2026-10-18)
9. **Leave the rollover (server 23:00-01:00) out of intraday tests.** Histdata's bid quotes spike and snap back there,
   which looks like a reversal that cannot be traded. Evidence: AUD/NZD relative-move test. (2026-10-15)
10. **Simple rule scans on these instruments are used up.** The cal/vol scan made 21,240 trials and one survivor, which
    failed its halves; every rerun raises the DSR bar for all later candidates. New edges need a reason (a flow, a
    paper) or new data. Evidence: `docs/trials.jsonl`, `docs/gates/`. (2026-10-17)
11. **Round-number levels do not work on USDJPY/EURUSD** (Osler): no variant reaches net Sharpe 0.5 in both halves,
    and round levels do no better than arbitrary ones. Evidence: `research/osler_round.py`. (2026-10-18)
12. **The S&P half of the noise leg has been flat or negative on 2024-26 three times; the Nasdaq half carries it.**
    It is not refitted on the tester window. Evidence: j1, j3, j6. (2026-10-17)
13. **A day stop set as a share of the *initial* balance fires more as the account compounds.** It is 1.1-1.2% of
    equity at 2.5-2.7x, so late day stops in long runs overstate the risk on a funded account that pays out. Evidence: j3. (2026-10-17)

## Process

14. **SSRN refuses downloads (403).** Find the paper on the authors' pages or in a working-paper series, and say when
    a source is "not readable" instead of filling in numbers. Evidence: researcher runs. (2026-10-17)
15. **Read the full paper before testing it.** Abstract-only ideas wait for a full read
    (`python tools/pdf_text.py`). Evidence: the owner's rule. (2026-10-14)
16. **The quant-coder subagent has no Bash in the relay.** It writes the script; the orchestrator runs it with
    `python research/<name>.py`. Evidence: Osler run, 2026-10-18.
17. **Run `git diff --cached --name-only` before committing.** Commit 031f5b6 carried 18 renames that were already
    staged, `.ex5` files among them. Evidence: commit 031f5b6. (2026-10-18)
18. **Count how often a month series reaches the goal from the month multiples, with 0.3% tolerance, or from the
    month's own "goal round of <month> ended" line. Never count from the `round` field, and never with a strict
    `>= level`.**
    - The own line is the one whose goal matches the run's (for example "goal 3.0x") and whose clock time falls inside
      the run.
    - The `round` field comes from the first "goal round of <month> ended" line for that month in the day-wide
      summary.txt, and that line can belong to an earlier run that day. The p_3x/p_5x figures are built on
      max(multiple, round) (`tools/months_summary.py:44-55`). j11b's 5x count of 2 came from j10b's lines, and j15's
      p_3x of 43% compares with a true 6 of 21.
    - The multiple is the balance after the last fill, so a round that stopped at the goal shows 2.999x or 3.992x. A
      strict `>= 3.0` counted j11b as 3 of 21, where its own lines give 9.
    - A 4x-goal run logs no 3x line, so its 3x count comes from the multiples only.

    Evidence: j11b, j15 `months_result.json`; t3b_202502 summary.txt line 351145; t4b_202412 summary.txt lines 1198,
    350303, 699411. (2026-10-18)
