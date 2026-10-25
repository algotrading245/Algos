"""Book gain of the random-long controls against the book WITHOUT the VRP leg (gates.py compares the control with a book
that already holds the VRP leg, so its book line is not the right one). Same B.risk_layer / 2018 split as gates.py."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import book_sim as B

M = 'marketdata/candidates/'


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


def load(c):
    d = pd.read_csv(M + c + '.csv')
    return pd.Series(d.r.values, index=pd.to_datetime(d.day))


base_legs = B.legs(without=['vrp_gap_equity_indices'])
base, _ = B.combine(base_legs)
mb = B.risk_layer(base)
s0 = sharpe(mb[mb.index >= '2018-01-01'])
print(f'book without VRP, 2018+ Sharpe {s0:.2f}')
for cid in ['vrp_gap_equity_indices', 'vrp_ctrl_s0', 'vrp_ctrl_s1', 'vrp_ctrl_s2']:
    new, _ = B.combine(B.legs(without=['vrp_gap_equity_indices', cid], extra={cid: load(cid)}))
    mn = B.risk_layer(new)
    s1 = sharpe(mn[mn.index >= '2018-01-01'])
    print(f'{cid:26s} book 2018+ {s0:.2f} -> {s1:.2f}  gain {s1 - s0:+.3f}')
