"""Writes the daily VIX closes (FRED VIXCLS) the AurumFunded VRP leg reads when the broker has no VIX symbol:
<Common>/Files/vixcls.csv, lines 'yyyy-mm-dd,close', no header, blanks dropped, ascending. Through tools/holdout.py, so the
file holds no day from 2025-10-13 on. On a demo / live terminal the owner refreshes it each day (the last day must be at
most 3 weekdays older than the last closed D1 bar of the index, or the leg gives no signal)."""
import os
import sys
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

d = pd.read_csv('marketdata/fred/VIXCLS.csv')
d.columns = ['day', 'v']
d['v'] = pd.to_numeric(d.v, errors='coerce')
d = d.dropna()
s = pd.Series(d.v.values, index=pd.to_datetime(d.day))
s = holdout.drop(s)
s = s[s.index >= '2005-01-01']
out = os.path.expandvars(r'%APPDATA%\MetaQuotes\Terminal\Common\Files\vixcls.csv')
with open(out, 'w', newline='') as f:
    for t, v in s.items():
        f.write(f'{t:%Y-%m-%d},{v:.2f}\n')
print(len(s), s.index[0].date(), s.index[-1].date(), 'written to the common Files folder')
