# Aurum Desk: a 24/7 AI trading desk (design, 2026-10-26)

A new, separate team that trades live markets on its own judgment and with the edges we already have. The current
system stays as it is: AurumHydra (5x), AurumFunded (funded account), the research pipeline, the T16 FTMO demo and
their agents and tasks. The desk only reads from it.

## 1. Boundary
- Own account, own MT5 terminal (one the current system does not use), own folder `desk/`, logs in `logs/desk/`,
  mutex `Local\AurumDesk`, scheduled tasks named `Aurum Desk *`, own token budget.
- Read-only access to `marketdata/`, `research/`, `docs/memory/` and the gate (`tools/gates.py`).
- Nothing in the desk may touch T16, the EAs, the `.set` files or the research queue, except one path: a pattern the
  desk proves can be proposed to the research queue as an idea (section 8).

## 2. Rules nobody on the desk can change
1. Agents decide, code executes. An agent writes a trade ticket; it never sends an order.
2. Every order goes through the risk gate (code) and carries a server-side stop from the moment it is placed.
3. Hard limits live in `desk/risk.json`. Only the owner edits that file.
4. Demo first. Live money only after the live gate (section 9) and the owner's yes in chat.
5. A control pod that runs only tested edges, with no AI judgment per trade, is the benchmark. Every other pod is scored
   against it.
6. Every ticket states a thesis and an invalidation, so each trade can be scored after it closes.

## 3. The team
| Role | What it is | Model | Wakes | Job |
|---|---|---|---|---|
| Control pod | code | none (Haiku for the daily note) | on bar close | runs the gated legs and edges from `research/` on the desk account |
| FX macro pod | agent | Sonnet | briefs, own triggers | G10 majors and crosses, days to weeks: rates, central banks, the calendar |
| Metals and energy pod | agent | Sonnet | briefs, own triggers | gold, silver, oil: real yields, USD, positioning (COT), term structure |
| Indices pod | agent | Sonnet | briefs, own triggers | US500, US100, GER40, JP225: sessions, macro data, earnings season |
| Event pod | agent | Sonnet | calendar triggers | scheduled releases and surprises, minutes to hours, flat by its time stop |
| Crypto pod | agent | Sonnet | briefs, weekends | BTC, ETH CFDs, only if the desk broker lists them; the weekend desk |
| Head trader | agent | Opus | each brief, weekly | approves or rejects tickets, nets pods that clash, checks the book, sets pod budgets weekly |
| Risk gate | code | none | every ticket, every minute | applies `risk.json`, can reject or close, owns the kill switch |
| Executor | code | none | every minute | places orders through the MT5 Python API (MetaTrader5 5.0.6090 is installed), manages stops, targets, trails and time stops, reconciles |
| Desk monitor | agent | Haiku | hourly | terminal up, positions match tickets, limits, P&L; raises ALERT |
| Scorekeeper | code + Haiku note | Haiku | daily | P&L, R-multiples and hit rate per pod, against the control pod |
| Debrief | agent | Sonnet | after the NY close | scores each closed trade's thesis, writes lessons, proposes proven patterns to research |

Markets: everything the desk broker lists that passes the liquidity rule (spread under its 20-day median times 2,
enough history). Each pod owns its group. An instrument no pod owns can be traded by any pod through the head trader.

## 4. How the pods work together
- **Desk board** (`desk/board.jsonl`): at each brief every pod posts its view (bias, key levels, conviction, what would
  change its mind). A pod reads the board before it writes a ticket. Example: FX macro reads the indices view before
  trading JPY.
- **Cross-pod tickets**: a ticket can cite another pod's view. The P&L credit is then split between the two pods.
- **Netting**: the desk never holds opposite positions on one instrument. When two pods clash, the head trader
  keeps the ticket with the better thesis, or neither.
- **Shared memory**: `desk/memory/lessons.jsonl` holds lessons per pod and per market, which every pod reads at its
  first brief of the day.

## 5. How they compete
Each pod has two budgets: risk (percent of equity it may have at risk) and tokens (per day). Every Saturday the
scorekeeper ranks the pods and the head trader moves both budgets:
- Score: net P&L per unit of risk over the last 4 weeks, after costs. Below 20 trades a pod keeps its base budget.
- Floor 10% and cap 30% of the desk's budget per pod; at most 10 points moved a week.
- A pod below the control pod for 6 weeks in a row is paused, and its brief is rewritten before it restarts.
- The pipeline roles (head trader, risk gate, executor, monitor, scorekeeper, debrief) have fixed budgets. They
  do not compete.

## 6. The 24-hour cycle (server time; crypto also on weekends)
- **Desk clock** (code, every minute): prices, triggers the pods set (price levels, calendar events, stop or target
  hit, spread spikes), reconciliation with the terminal.
- **Briefs**: Asia open, London open, NY open, and the debrief after the NY close. At a brief each pod reads the
  board, the calendar, the news and its positions, then writes views and tickets. The head trader then approves or
  rejects them.
- **Between wakes** the executor manages every position by its ticket (stop, targets, trail, time stop). Agents never
  need to be fast, and the token budget stays bounded.
- A pod wakes outside its briefs only on a trigger it set itself, at most 6 times a day.

## 7. The trade ticket (`desk/tickets.jsonl`)
`id, pod, instrument, side, entry (market | limit | stop, price), stop, targets [price, share], risk_pct,
time_stop, thesis, invalidation, evidence (sources, other pods' views), playbook (a named edge, if any),
confidence (1-5), status, head_trader (approved | rejected, why), result (filled, R, P&L, closed by)`

## 8. Research bridge
The debrief tags a pattern that won repeatedly, for example "London breakout after an Asia range under 0.4 ATR".
Once it has 30 or more closed trades, the debrief writes it to `docs/ideas/queue.jsonl` with source "desk". From
there the existing builder and gate test it on all the data before the holdout. A pattern that passes can become an
edge for the control pod or a leg in the EAs.

## 9. Hard limits (`desk/risk.json`, owner-only) and the live gate
- Per trade at most 0.5% of equity at risk; per pod at most its budget (2% cap); the desk at most 5% open risk.
- Correlated groups (USD, JPY, gold, US indices) at most 2.5% open risk each; at most 3 positions per instrument.
- Desk daily loss 3%: flatten and stop until the next day. Weekly loss 6%: stop until the owner reviews. Drawdown of
  12% from the peak: kill switch.
- No entry with the spread above 2x normal, and none from 2 minutes before to 2 minutes after a tier-1 release, except
  for the event pod under its own limits. No averaging down; adding to a position only after its stop is at breakeven.
- Kill switch: the file `logs/desk/KILL` or a word in chat. It closes everything and turns the executor off.

Live gate, all of these on the demo: 8 weeks, at least 100 desk trades, net profit factor 1.2 or more after costs,
maximum drawdown 8% or less, no limit breach from a code fault, and the AI pods together beating the control pod on
P&L per unit of risk. Then live on capital the owner sets, at half risk for the first month.

## 10. Build plan
- **Phase 0, week 1: the plumbing.** The `desk/` folder, a demo account on the desk terminal, the executor, the risk
  gate, the desk clock, the kill switch and the logs. Tested with hand-written tickets, including every limit.
- **Phase 1, weeks 2-3.** The control pod, FX macro, the head trader, the monitor and the scorekeeper, on the demo at
  quarter risk.
- **Phase 2, weeks 4-5.** Metals, indices and event pods; the board; the debrief and the research bridge; the weekly
  reallocation. Crypto if the broker lists it.
- **Phase 3, weeks 6-13.** The full desk on the demo, toward the live gate.
- **Phase 4.** Live, on the owner's yes.

## 11. Infrastructure
The executor, the risk gate and the clock must run 24/7. This PC hung entering hibernate on 2026-10-24, so the
recommendation is a Windows VPS near the broker's server for those three (and the desk terminal). The agents can run
on this PC or on the VPS. Until a VPS exists, the demo runs here under a keeper-style watchdog.

## 12. What only the owner can do
1. Open a demo account for the desk, separate from the FTMO demo. Recommended: a raw-spread MT5 broker with a wide CFD
   list (FX, metals, energy, indices, crypto), e.g. IC Markets Raw or Pepperstone Razor. Then log the desk terminal in.
2. Decide on the VPS.
3. Later: the live account and its capital.

## 13. The honest risk
AI judgment trading is unproven, and most discretionary traders lose after costs. The control pod and the 8-week live
gate exist to find that out on the demo, cheaply, before real money is at risk. If the AI pods do not beat the control
pod, the desk falls back to the control pod plus the research bridge.
