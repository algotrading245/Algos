"""Baltussen, Da, Lammers, Martens (2021): r_ROD (cash-close-30min price / previous cash close - 1) predicts the last 30 min.
Long if r_ROD>0 else short, enter at close-30, exit at the minute before the cash close. Cash close taken per day from the
exchange calendar clock (NY 16:00, Berlin 17:30, Tokyo 15:00) converted to the server clock (Europe/Athens, file clock),
so US/EU DST mismatch weeks are handled. Variants (trials): A base, B |r_ROD| > past 60d median. Cost bp per side, round trip doubled.
Size = 10% annual vol target / past EWM daily vol, cap 3. Choose on <=2017, judge 2018 on.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_baltussen_last30_index_mom"
COST = {"SPXUSD": 1.0, "NSXUSD": 1.5, "GRXEUR": 1.5, "JPXJPY": 3.0}
CAL = {"SPXUSD": ("America/New_York", 16, 0), "NSXUSD": ("America/New_York", 16, 0),
       "GRXEUR": ("Europe/Berlin", 17, 30), "JPXJPY": ("Asia/Tokyo", 15, 0)}
TARGET = 0.10


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def run(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "close"]])
    tz, hh, mm = CAL[sym]
    days = pd.DatetimeIndex(h.index.normalize().unique())
    rows = []
    prev_close = None
    cl = h.close
    for d in days:
        if d.weekday() >= 5:
            continue
        loc = pd.Timestamp(d.year, d.month, d.day, hh, mm).tz_localize(tz, nonexistent="shift_forward", ambiguous=True)
        srv = loc.tz_convert("Europe/Athens").tz_localize(None)
        t_in, t_last = srv - pd.Timedelta(minutes=30), srv - pd.Timedelta(minutes=1)
        seg = h.loc[t_in - pd.Timedelta(minutes=3):t_last]
        a = seg.loc[t_in - pd.Timedelta(minutes=3):t_in]
        b = seg.loc[t_last - pd.Timedelta(minutes=3):t_last]
        if len(a) == 0 or len(b) == 0 or a.index[-1] < t_in - pd.Timedelta(minutes=2) or b.index[-1] < t_last - pd.Timedelta(minutes=2):
            prev_close = float(b.close.iloc[-1]) if len(b) and b.index[-1] >= t_last - pd.Timedelta(minutes=2) else prev_close
            continue
        p_in = float(a.open.iloc[-1]) if a.index[-1] == t_in else float(a.close.iloc[-1])
        p_out = float(b.close.iloc[-1])
        if prev_close is not None:
            rows.append((d, p_in / prev_close - 1, np.log(p_out / p_in)))
        prev_close = p_out
    return pd.DataFrame(rows, columns=["day", "rod", "last"]).set_index("day")


def daily(df, cm, filt):
    sig = np.sign(df.rod)
    if filt:
        med = df.rod.abs().rolling(60).median().shift(1)
        sig = sig.where(df.rod.abs() > med, 0)
    gross = sig * df["last"]
    cost = (sig != 0) * 2 * COST_BP * cm / 1e4
    return gross - cost, sig


def sized(r_unit, df_ret):
    vol = df_ret.ewm(span=60).std().shift(1)
    # vol of the trade-return series is tiny; scale on close-to-close would need full day: use last-30 trade vol scaled to 10% target
    size = (TARGET / np.sqrt(252) / vol).clip(upper=3)
    return size


def main():
    global COST_BP
    res, mk, best = {}, {}, {}
    for sym in COST:
        df = run(sym)
        res[sym] = df
        print(sym, len(df), df.index[0].date(), df.index[-1].date(), "mean last-30 bp", round(df["last"].mean() * 1e4, 2))
        print("  corr(rod,last)", round(df.rod.corr(df["last"]), 3))
        for filt in (False, True):
            for cm in (1.0, 1.5, 2.0):
                COST_BP = COST[sym]
                r, _ = daily(df, cm, filt)
                a, b = r[r.index < "2018"], r[r.index >= "2018"]
                gro, _ = daily(df, 0.0, filt)
                if cm == 1.0 and not False:
                    pass
                print(f"  filt={filt} cost x{cm}: sharpe all {sh(r):.2f} <=2017 {sh(a):.2f} 2018+ {sh(b):.2f} | gross all {sh(gro):.2f}")
    # portfolio on SPX+NSX (+GRX) for chosen variant is decided after looking at <=2017 output; see run2
    return res


COST_BP = 1.0

if __name__ == "__main__":
    main()
