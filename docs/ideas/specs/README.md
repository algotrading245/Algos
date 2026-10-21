# Idea specs

The miner writes one JSON file per idea in this folder. `tools/spec_factory.py` adds the rest with no LLM: when fewer
than 10 specs are pending it writes the next 10 from a fixed grid (each standard rule family × every symbol × no filter,
high/low vol, up/down trend, at the engine's default parameters; ids `f_<rule>_<symbol>[_vh|_vl|_tu|_td]`,
`"made_by": "spec_factory"`), at most 120 a day, 732 in all. `tools/idea_engine.py` (started by the keeper every
minute, one run per 3 minutes at most) tests every spec whose `status` is `pending`. While a Claude agent runs it still
tests, but a PASS waits (stays pending) and nothing is committed until the agent ends. No LLM is
involved. For each spec the engine:

1. builds every variant: symbols × entries × holds × sides × event offsets, at most 200;
2. picks the variant with the best Sharpe on the days before 2018 only;
3. hands that variant to the fixed gates (`tools/gates.py`), with the DSR trial count raised by every variant it looked at;
4. writes the result to `docs/ideas/results.jsonl` and `results.md`, and sets the spec's `status` to `done`.

A PASS goes into `docs/candidates.json` and wakes the orchestrator. The holdout (`tools/holdout.py`) is never used.

## Format

```json
{
  "id": "fomc_xau_preannounce",
  "title": "Gold drifts up in the hours before the FOMC statement",
  "source": "Lucca & Moench (2015), The Pre-FOMC Announcement Drift, Journal of Finance 70(1)",
  "link": "https://doi.org/10.1111/jofi.12196",
  "read": "in full",
  "why": "The paper finds equities rise in the 24h before FOMC; gold is a dollar hedge, so the same risk premium may show up there",
  "symbols": ["XAUUSD", "SPXUSD"],
  "entry": ["event-8", "event-4"],
  "hold": [4, 8],
  "side": "both",
  "when": {"event": "fomc"},
  "status": "pending"
}
```

| field | meaning |
|---|---|
| `id` | a file-name-safe id, unique, the same as the file name without `.json` |
| `read` | `"in full"` when the whole paper was read; `"n/a"` for a market-structure idea with no paper; else `"unverified"`. Owner's rule: the engine tests only `"in full"` and `"n/a"`; an `"unverified"` spec is set to `"unread"` and waits until someone reads the source and sets it back to `pending` |
| `symbols` | from: AUDCAD AUDJPY AUDNZD AUDUSD CADJPY EURAUD EURCHF EURGBP EURJPY EURUSD GBPCHF GBPJPY GBPUSD GRXEUR JPXJPY NZDCAD NZDUSD SPXUSD USDCAD USDCHF USDJPY WTIUSD XAGUSD XAUUSD |
| `entry` | list of: `"HH:MM"` New York time; `"event"` (just before the release) and `"event-4"` / `"event+1"` (half-hours before / after it); or a raw grid column (int) |
| `hold` | list of holds in half-hours (default `[2, 4, 8]`) |
| `side` | `long`, `short`, `both` (both tried), `follow` or `fade` (the sign of `own_move`, `driver` or `trend: "sign"`) |
| `when` | all conditions must hold (AND); leave it out to trade every day |

`when` keys:

| key | values |
|---|---|
| `weekday` | `["mon", "fri"]` |
| `month_day` | trading day of the month: `[1, 2]` first two, `[-1]` last |
| `event` | `fomc` (14:00), `nfp` (08:30), `gdp` (US advance, 08:30), `ism` (first business day, 10:00), `china_cpi`, `china_activity`, `china_gdp` (02:00 UTC, from 2015), `opex` (third Friday), `quarter_end` (last business day of the quarter). `opex` and `quarter_end` have no release time: use `"HH:MM"` entries |
| `event_offset` | trade that many business days after the event day (negative = before); a list is tried as variants |
| `own_move` | `big` (the day after a top-15% daily move of the symbol; the sign drives follow/fade), `big_up`, `big_down` |
| `driver` | `{"symbol": "SPXUSD", "move": "big"}`: the same on another symbol; `DOLLAR` is the dollar basket |
| `vol` | `high` / `low`: 20-day volatility in the top / bottom third of its last year |
| `trend` | `up` / `down` (20-day return as of yesterday), or `sign` for follow/fade |

## Rule specs (daily strategies from papers and open code)

A spec with `"rule"` instead of `"entry"` is a daily strategy: the position is set from closes up to yesterday
and earns today's close-to-close return. Cost: half the round-trip cost per unit of position change, plus 0.5 bp
swap per day held.

```json
{"id": "tsmom_jpy_gold", "title": "...", "source": "Moskowitz, Ooi, Pedersen 2012", "link": "...",
 "read": "in full", "why": "...", "rule": "tsmom", "symbols": ["XAUUSD", "USDJPY"],
 "params": {"lookback": [60, 120], "hold": [1]}, "side": "both", "when": {"vol": "high"}, "status": "pending"}
```

| rule | params (defaults when left out) | position |
|---|---|---|
| `tsmom` | `lookback` [20, 60, 120] | sign of the lookback return |
| `reversal` | `lookback` [1, 5] | minus the sign of the lookback return |
| `donchian` | `lookback` [20, 55] | long after a close above the prior N-day high, short below the low, held until the opposite |
| `meanrev` | `lookback` [10, 20], `z` [1.5, 2.0] | short above mean + z std, long below mean - z std, flat between |
| `ma_cross` | `fast` [10, 20], `slow` [50, 100] | sign of fast MA minus slow MA |
| `rsi` | `period` [2, 14], `level` [10, 30] | long when Wilder RSI < level, short when > 100 - level |
| `xsmom` | `lookback` [20, 60, 120], `top` [1] | across the listed symbols: long the top `top`, short the bottom `top` (one basket) |

Every rule also takes `hold` (keep a signal that many days, default [1]) and `flip` ([true] inverts it). `side` is
`both`, `long`, `short` or a list. `when` takes only `weekday`, `month_day`, `vol` and `trend`. Name the paper's
own parameters; leave a parameter out only when the source gives none (each default value is another variant).
A spec whose rule, symbols, params, side and `when` match a spec already tested is marked `DUPLICATE of <id>` and
not tested again.

## Timing

The grid holds the bid at the end of every half-hour of the server day (New York 17:00 to 17:00). `"08:30"` is the price
at 08:30 New York, so an entry at `"event"` on NFP days is just before the release and a hold of 1 takes the release
half-hour. Windows must start at 18:30 or later and end by 16:30 (the bid-only spread around the 17:00 rollover).

Trades need at least 20 days before 2018 and 20 from 2018. The China calendar starts in 2015, so China specs often fail
this; that is a data limit, not a verdict.

## Caveats

- In 2011-12 the FOMC statement on press-conference days came at 12:30, not 14:00; `fomc` uses 14:00 throughout.
- Every variant is a trial: a spec with 200 variants raises the DSR bar for every later candidate. Keep specs narrow:
  one mechanism, the symbols it names, two or three entries and holds.
- A PASS is a candidate, not an edge. The reviewer, the tester and the demo forward test still come before any EA.
