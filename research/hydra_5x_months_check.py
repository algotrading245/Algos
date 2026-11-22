"""j8a-c (AurumHydra 5x month series on Terminal 16, 2025-01 to 2026-09): what each month traded.

Prints each month's multiple, equity drawdown and profit by symbol from the month folders' result.json, and the
gold hold's trend signal in each month (the tester log is shared by every run of the day, so it is not used).

    python research/hydra_5x_months_check.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARTS = ["2026-10-17_1625_AurumHydra_5xA_months", "2026-10-17_2144_AurumHydra_5xB_months",
         "2026-10-17_2231_AurumHydra_5xC_months"]


def month_folders():
    for p in PARTS:
        state = json.loads((ROOT / "backtests" / p / "months.json").read_text(encoding="utf-8-sig"))
        done = state["Done"] if isinstance(state["Done"], list) else [state["Done"]]
        for m in done:
            if m.get("Folder"):
                yield m["Month"], ROOT / m["Folder"]


def main():
    syms = set()
    rows = []
    for ym, f in month_folders():
        r = json.loads((f / "result.json").read_text())
        rows.append((ym, r))
        syms.update(r["by_symbol"])
    syms = sorted(syms, key=lambda s: (s != "XAUUSD", s))
    print("month    mult  eqDD  " + " ".join(f"{s[:7]:>7}" for s in syms))
    for ym, r in rows:
        mult = 1 + r["net"] / r["deposit"]
        cells = " ".join(f"{r['by_symbol'].get(s, 0):7.0f}" if s in r["by_symbol"] else "      -" for s in syms)
        print(f"{ym}  {mult:4.2f}  {r['eq_dd_max_pct']:4.1f}  {cells}")
    gold = sum(1 for _, r in rows if "XAUUSD" in r["by_symbol"])
    print(f"months with XAUUSD trades: {gold} of {len(rows)}")

    # The gold hold (AurumHydra.mq5 Hold()) is long 0.25 for each of the 20/60/120/250-day returns that is positive,
    # floored at 0. Its signal on each weekday of the month, from the other broker's daily closes (close enough to
    # FTMO's for a sign): mean signal and the share of days it is 0, so no hold position at all.
    d = pd.read_csv(ROOT / "marketdata" / "XAUUSD.pc_D1.csv.gz")
    c = pd.Series(d["close"].values, index=pd.to_datetime(d["time"], unit="s")).sort_index()
    print(f"gold closes {c.index[0].date()} to {c.index[-1].date()}")
    sig = sum(((c > c.shift(k)).astype(float) - (c < c.shift(k)).astype(float)) * 0.25 for k in (20, 60, 120, 250))
    sig = sig.clip(lower=0).shift(1)        # the EA reads yesterday's close
    print("month    hold signal  days at 0  gold month %")
    for ym, r in rows:
        m = sig[ym.replace(".", "-")]
        g = c[ym.replace(".", "-")]
        move = (g.iloc[-1] / c[c.index < g.index[0]].iloc[-1] - 1) * 100 if len(g) else float("nan")
        print(f"{ym}  {m.mean():11.2f}  {(m == 0).mean():9.0%}  {move:12.1f}"
              f"  {'gold traded' if 'XAUUSD' in r['by_symbol'] else 'no gold'}")


if __name__ == "__main__":
    main()
