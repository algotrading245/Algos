# Mission (owner-only)

What every agent works toward. Only the owner changes this file; agent runs are refused edits to it
(`tools/autopilot/settings.json`). An agent that thinks it is wrong writes a decision with kind `question` and a note
in `docs/HANDOFF.md`.

## The two products

1. **AurumHydra** (`mql5/Experts/AurumHydra/`): turn $100 into $500 within one calendar month with the highest
   probability. Its measure is the share of fresh-deposit months that reach the goal (`InpTarget` 3, 4 or 5),
   with P(ruin) next to it.
2. **AurumFunded** (`mql5/Experts/AurumFunded/`): pass a prop-firm challenge and keep the funded account. Its measures
   are the chance to pass, the months to the first payout, and the chance of losing the account.
   Routes: FTMO 2-Step (now in the demo), FundedNext Stellar Instant, Instant Funding PRO.

Both share one leg library, `mql5/Include/Aurum/`. Instruments on FTMO: XAUUSD, USDJPY, EURUSD, AUDCAD, the yen
crosses, US500.cash, US100.cash.

## The pipeline

Idea (2) -> scan (3) -> paper or source read in full (4) -> data, prototype at real costs (5-7) -> gates 8-11
(halves, DSR, correlation, goal effect; reviewer) -> EA code, leg off by default (12-14) -> Strategy Tester on FTMO
data (15) -> judged against the Python expectation (16) -> demo (17) -> fidelity checks (16-17) -> live (19, owner
only) -> monitoring (20).

## Fixed rules

- Nothing goes into an EA unless it survives realistic costs in both halves of the data (to 2017, 2018 on).
- **Holdout:** every day from 2025-10-13 on belongs to the owner. Tester jobs end by 2025-09-30, research data goes
  through `tools/holdout.py`, and `tools/holdout_check.py` is never run by an agent. Never tune on j8b, j8c or j9.
  The clean out-of-sample test is the FTMO demo from 2026-10-19 on.
- Never live trading or real money, never step 19, never buy anything, never change an account, a terminal setting
  or a terminal's EA. Terminal 16 keeps the demo EA; the tester has its own install.
- Act on `docs/autopilot/approvals.json` only when an item is "approved". The owner says yes to every live or
  real-money step.
- Never record an account number, login, password or key, in any file, commit or log.
- Agents do not edit `tools/`, `.claude/` or `.gitignore`; they describe the change in the handoff.
- Never fit settings to the tester window. A result that disagrees with the model is written down, not tuned away.
- Every claim needs a file behind it. "Done" means the evidence is committed.

## Memory

- `docs/memory/decisions.jsonl`: every decision of every run, append-only, written with
  `python tools/memory.py decide ...`. Never edit or delete a past line; a reversal is a new line that names the old one.
- `docs/memory/lessons.md`: at most 40 lessons that change how we work, each with its evidence and date. Only the
  orchestrator edits it, and a new or changed lesson goes past the reviewer first. Lessons never override this file.
- `python tools/memory.py search <words>` finds past decisions, lessons, runs, ideas, trials and (with `--events`)
  every command an agent ran.
