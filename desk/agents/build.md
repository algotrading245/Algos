
## This run: the weekend build (owner 2026-11-02)

This is not a brief. The market is shut or quiet; this run has its own budget, apart from your daily slice, and one
job: **build or tune ONE edge for the markets you trade, test it, and post the result.** No tickets, no forecasts, no
market notes and no model edits are needed in this run.

1. Read the board first (`board read 50`) and the edge list (`edge list`): do not build what another pod built or is
   building. Pick one idea and say which in your first board post, `board post "building: keltner_break on XAUUSD H4"`.
2. Pick the idea. The best start is usually a reference edge (`edge list` marks them `reference`; `edge describe NAME`
   shows its card and its defaults): run it on your markets as it is, then tune its defaults with key=value. A new
   rule goes in `desk/edges/new/<name>.py` with `pod="<your pod>"` (see the Edges section above).
3. Test it on the whole history: `edge sandbox NAME MARKET key=value`. Try a few settings at most (3 to 5), not a grid:
   every extra setting you try makes the best one look better than it is. The card shows total R in each half of
   the history (`halves`); a setting that wins in only one half is fitted to the past.
4. Arm it only if the card has **30+ trades, PF 1.1+ after costs and positive total R in both halves**:
   `edge arm NAME MARKET key=value risk=0.25`. The arm refuses anything short of that. Otherwise leave it for
   judgment tickets (cite it in the `edge` field) or drop it.
5. Post the result on the board, armed or not, with the numbers:
   `board post "built keltner_break XAUUSD H4 n=20 k=2: 64 trades PF 1.24 halves +5.1/+3.8 R; armed 0.25" instrument=XAUUSD`.
   A failed idea is worth a post too, so no pod tests it again.
6. Finish with one paragraph: what you built, its card, armed or not, and what to try next weekend.
