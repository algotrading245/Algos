# j21: AurumFunded bko0 on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-11-02 13:08: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_grz.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set ['InpRefuseBackoffSec=0'], compare_set ['InpRefuseBackoffSec=60'].

## legs off (`2026-11-02_1156_AurumFunded_bko0_off`)

| Measure | Value |
|---|---|
| Net profit | +13,339.78 (+133.4%) |
| Trades / win rate | 2289.0 / 52.34% |
| Profit factor | 1.65 |
| Max equity drawdown (relative) | 7.06% |
| Worst day | 2024-07-25 -2.59% |
| Return per unit of drawdown | 18.9 |
| By year | 2024 +4,191, 2025 +9,149 |
| History quality | 99% real ticks |

## legs on (`2026-11-02_1233_AurumFunded_bko0_on`)

| Measure | Value |
|---|---|
| Net profit | +13,339.78 (+133.4%) |
| Trades / win rate | 2289.0 / 52.34% |
| Profit factor | 1.65 |
| Max equity drawdown (relative) | 7.06% |
| Worst day | 2024-07-25 -2.59% |
| Return per unit of drawdown | 18.9 |
| By year | 2024 +4,191, 2025 +9,149 |
| History quality | 99% real ticks |

## On against off

Return per unit of equity drawdown: off 18.9, on 18.9 (not higher with the legs on).

## Expected (from the job)

Check for fix_refused_retry2 on AurumFunded v1.25 (build 04006be + input InpRefuseBackoffSec). Off run = back-off 0 = the v1.23 behaviour, on run = 60 s back-off (v1.24 behaviour); the month-reversal leg stays off (InpGrzMult=0), so the book is the j19 off run (about 2298 trades, +137%, equity DD 7.75%). Expect the two trade lists to match: same count, same open times and prices. Any difference is a retry the tester made after a 10018/10027 refusal at a session edge that the 60 s back-off delayed; list those (compare deal times and the 'server refused an order' log lines). Do not tune on this window.

## Log lines worth a look

- None matched (not found, cannot, failed, margin, invalid, error).
