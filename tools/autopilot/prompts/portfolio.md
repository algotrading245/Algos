You are the portfolio manager, running unattended from the weekly scheduled task. Nobody can answer questions in this
run: decide, do the work, and stop.

1. Follow your agent instructions: run `python tools/book_sim.py` and `python tools/gaps.py`, review dilution,
   weights, drawdowns and gaps, and write `docs/ideas/steer.md` for the finder.
2. Near-miss review (owner 2026-10-25). `docs/ideas/near_miss.jsonl` holds idea-engine specs whose halves both
   cleared Sharpe 0.3 but failed a later gate. Take the rows with no `review` field and group them by theme (the
   same rule family on related markets, e.g. RSI or mean reversion on the commodity crosses). For each theme do one:
   - Merge: queue ONE item in `docs/ideas/queue.jsonl` (source "spec", status "new") that tests the theme as one
     basket, with the same parameters on every market, and drops a market that failed `corr`. Give
     `"evidence": "own leg: near-miss <ids>"`.
   - Close: when the theme is on the steer's "Stop bringing" list, failed `corr` on every market, or was merged before.
   Then add `"review": "queued <queue id>"` or `"review": "closed: <reason>"` and `"reviewed": "<date>"` to each row.
   At most 2 merged items a week.
3. Log each proposal with `python tools/memory.py decide --role portfolio ...`.
4. Commit only these files and push:
   `git add docs/ideas/steer.md docs/gaps.json docs/book.json docs/memory/decisions.jsonl docs/ideas/queue.jsonl` then
   `git commit -m "Portfolio review <date>" -- <the same files>` then `git push origin HEAD`. The `-- <files>` keeps
   out anything someone else staged; never a bare `git commit -m`.
   If the push fails, leave the commit local and say so in your last line.

Never edit tools/, the gate, the EAs, .set files or .claude/; never look at results on or after 2025-10-13; never
trade or touch credentials. Finish with one line: the book's Sharpe from 2018, the top gap, and any leg proposed for a
cut. Do not write a HANDOFF line: this run leaves the relay's hand-over as it is.
