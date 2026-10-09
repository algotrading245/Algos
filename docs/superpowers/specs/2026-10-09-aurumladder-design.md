# AurumLadder — design

Date: 2026-10-09
Status: approved; implemented in `mql5/` (not yet compiled or backtested)

## Purpose

AurumLadder is an MQL5 Expert Advisor that trades gold on a Vantage cent account in MetaTrader 5. It opens one trade in the direction of the measured trend with a small profit target. If price moves against it by a set distance, it opens a larger trade in the opposite direction, sized so the whole basket closes in profit at the next target. This repeats, alternating direction, until a target is hit or a step cap is reached.

The ladder does not create an edge. It converts a directional edge into many small wins and an occasional capped loss. The design therefore has two jobs: size the ladder exactly, and prove by backtest that the direction signal beats break-even.

## Decisions already made

| Item | Decision |
|---|---|
| Instrument | `XAUUSD.pc` (Vantage cent gold: contract 1, digits 2, tick 0.01, lot 0.01–500 step 0.01, stops level 20 points) |
| Platform | MQL5 Expert Advisor, MT5 Strategy Tester on real ticks |
| Recovery trade direction | Opposite to the previous trade |
| Loss cap per failed ladder | 5% of account balance |
| Development terminal | `C:\Program Files\MetaTrader 5 - 14` (data folder `C0E230B8F9C8C2A16D1EE5E91A38A7CF`), VantageMarkets-Live 21, USC, leverage 500 |
| Account mode | Hedging (confirmed on Terminal 14); the EA refuses to start on a netting account |

## Symbols used in the maths

| Symbol | Meaning |
|---|---|
| d | Zone width: adverse move that triggers the next trade (price units) |
| t | Target distance beyond a zone edge (price units) |
| s | Spread allowance, equal to the spread filter limit (price units) |
| c | Round-trip commission per lot, expressed in price units (0 if none) |
| V | Account-currency profit per 1.00 lot per 1.00 price move (tick value ÷ tick size) |
| N | Step cap: the maximum number of trades in one ladder |
| L_n | Lot size of trade n |

All broker values (V, minimum lot, lot step, stops level, margin per lot) are read from the terminal at run time. None are hard-coded.

## 1. Direction signal

Evaluated once per closed M15 bar, only when no ladder is open.

- Fit a least-squares line to ln(close) over the last 64 bars. Compute the slope's t-statistic (slope ÷ standard error of slope).
- Compute the efficiency ratio: |last close − first close| ÷ sum of |bar-to-bar close changes| over the same window.
- Signal fires when |t-statistic| ≥ 3.0 and efficiency ratio ≥ 0.25. Direction is the sign of the slope: positive is buy, negative is sell.
- Otherwise no trade.

Lookback, t-statistic threshold and efficiency threshold are inputs to be tuned by backtest. Price series are autocorrelated, so the t-statistic is a ranking measure with an empirically tuned threshold, not a formal significance test.

## 2. Zone and targets

Fixed when the first trade opens and frozen for the life of the ladder.

- d = 1.5 × ATR(14, M15) and t = 1.5 × ATR(14, M15). Both multiples are inputs.
- Floors: t ≥ 5 × s; d and t > broker stop distance + s (so every stop order and SL/TP is valid even at the widest allowed spread); t > c. If a floor fails, no ladder starts.
- First trade a buy filled at U: upper edge = U, lower edge = U − d. A sell filled at W: lower edge = W, upper edge = W + d.
- Upper target = upper edge + t. Lower target = lower edge − t.

Lot growth per step is about 1 + d/t, so the defaults give a roughly doubling ladder.

## 3. Orders

- Buys enter at the upper edge; sells enter at the lower edge.
- Each buy: take-profit at the upper target, stop-loss at lower target − s.
- Each sell: take-profit at the lower target, stop-loss at upper target + s.
- The spread offset makes losers and winners trigger together, since buys close on bid and sells close on ask.
- After each fill, the next reversal trade is placed as a pending stop order at the opposite edge with its lot already calculated, so the ladder continues if the terminal is offline. If price is already through that edge, it is placed at market instead.
- When any position closes by take-profit or stop-loss, the EA closes every remaining position and deletes the pending order. This is the backstop if slippage splits the basket.

Per lot, a winning trade gains t and a losing trade loses at most d + t + s.

## 4. Sizing

**Target profit.** π = L_1 × (t − c): the profit the first trade alone would have made.

**Reversal lot.** Before trade n, let W be the lots already open on trade n's side and X the lots on the opposite side:

    t × (W + L_n) − (d + t + s) × X − c × (W + X + L_n) ≥ π
    L_n = ( π + (d + t + s) × X + c × (W + X) − t × W ) ÷ ( t − c )

rounded up to the lot step. With d = t, s = c = 0, L_1 = 0.01 the ladder is 0.01, 0.03, 0.06, 0.12, 0.24, 0.48.

**Failed-ladder loss.** If trade N is stopped out, with W_N the lots on its side (itself included) and X_N the rest:

    Loss = V × ( (d + t + s) × W_N − t × X_N + c × (W_N + X_N) )

**First lot.** L_1 is the largest lot-step multiple for which the failed N-step loss ≤ 5% of balance and the total margin of all N lots ≤ 50% of free margin. If the minimum lot fails, N is reduced by one and the check repeats. Below N = 3, no ladder starts and the EA logs the balance it would need.

Swap is ignored in sizing because ladders are intended to complete intraday.

## 5. Ladder lifecycle

States: **Flat → Laddering → Closing → (Cooldown) → Flat**.

- **Flat:** wait for the direction signal and the risk guard.
- **Laddering:** trades filled so far are tracked; the next reversal order is kept at the broker until the step cap N (default 6, tune 4–8).
- **Closing:** any TP/SL exit, a missing zone, or the weekend rule moves here; the EA closes everything, retrying each tick until the basket is empty, then books the realised result from deal history.
- **Cooldown:** after a ladder that closed at a loss, 4 hours (input).

**Restart recovery.** Zone, lots, step cap and fill count are saved in terminal global variables under `AL_<magic>_`. On start the EA resumes from them. If positions exist with no saved zone, it closes them and logs an error rather than guess. If the saved ladder has no positions left, it books the result and returns to Flat.

## 6. Risk guard

- **Spread filter:** no new ladder when spread exceeds s (default 0.40). Applies to starting only; a pending reversal can fill at a wider spread.
- **Weekend:** no new ladder within 3 hours of the Friday close (read from the symbol's session table, fallback input 23:55 server time). Any open ladder is closed 15 minutes before the close.
- **Daily stop:** after 2 losing ladders in one server day, no new ladder until the next day.
- **Account mode:** hedging required, checked at start.

Accepted residual risks: a gap or heavy slippage can jump past a target and lose more than 5%; a reversal order can fill during a spread spike.

## 7. Feasibility on Terminal 14 (measured 2026-10-09)

Balance 677.31 USC, so the 5% cap is 33.87 USC. Median M15 ATR(14) over 3,000 bars is 7.70 (p10 5.40, p90 11.79); median spread 0.10; V = 100 USC per lot per 1.00.

With the defaults (d = t = 11.55, s = 0.40) at the minimum lot:

| N | Lots | Win per ladder | Failed-ladder loss | Balance needed at 5% |
|---|---|---|---|---|
| 3 | 0.01, 0.04, 0.09 | 11.5 USC | 189 USC | 3,775 USC ($38) |
| 4 | … 0.18 | 11.5 USC | 401 USC | 8,028 USC ($80) |
| 5 | … 0.36 | 11.5 USC | 827 USC | 16,534 USC ($165) |
| 6 | … 0.73 | 11.5 USC | 1,701 USC | 34,016 USC ($340) |

**At the current balance the EA will not trade with default settings**; it logs the balance needed instead. One of these must change before live or forward testing: deposit to at least the balance for the chosen N, raise the loss cap, or shrink the zone (smaller ATR multiples, which pushes the target closer to the spread). This is a decision for the account owner, not a code change.

## 8. Files

| Path | Responsibility |
|---|---|
| `mql5/Experts/AurumLadder/AurumLadder.mq5` | Inputs and event wiring |
| `mql5/Include/AurumLadder/Broker.mqh` | Symbol and account specifications |
| `mql5/Include/AurumLadder/Signal.mqh` | Regression t-statistic, efficiency ratio, direction |
| `mql5/Include/AurumLadder/Ladder.mqh` | Pure maths: lots, basket profit, failed-ladder loss, first lot |
| `mql5/Include/AurumLadder/Cycle.mqh` | State machine, orders, basket close, restart recovery |
| `mql5/Include/AurumLadder/RiskGuard.mqh` | Spread, weekend, daily stop |
| `mql5/Scripts/AurumLadder/LadderTest.mq5` | In-terminal tests for Ladder and Signal |
| `tools/ladder_model.py`, `tools/test_ladder_model.py` | Python reference model of the same maths plus a tick-path simulation of the order geometry |
| `tools/link-terminal.ps1` | Junctions the three `AurumLadder` folders into Terminal 14's data folder |

## 9. Testing and acceptance

**Unit tests** (`LadderTest.mq5` in the terminal; `python3 -m unittest` in `tools/`):

- The reference ladder 0.01, 0.03, 0.06, 0.12, 0.24, 0.48 and the Terminal 14 numbers above.
- For random d, t, s, c and lot steps: every step's basket profit at its target is ≥ π, and the failed-ladder loss never exceeds the cap.
- Signal maths against hand-computed and synthetic series (uptrend, downtrend, flat noise).
- Python only: random tick paths through the exact SL/TP and stop-order prices end either in a win of about π or, only at step N, in a loss within the formula.

**Backtest.** Strategy Tester, "Every tick based on real ticks", `XAUUSD.pc`, the most recent 3 years. Tune on the first 2 years only; run the final year once.

**Acceptance on the held-out year:**

- Net profit after spread and commission is positive.
- First-trade win rate exceeds d ÷ (d + t), the no-edge break-even.
- No single ladder loses more than 6% of balance.
- Maximum equity drawdown ≤ 30%.

If these are not met, the signal is revised; the ladder is not loosened to compensate.

**Forward test.** Two weeks on the cent account at the minimum first lot before any size increase.

## Out of scope

Other algorithms, other symbols, news filters, trailing stops, partial closes, a Python trading component, and any dashboard.
