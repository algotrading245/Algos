"""j18: profit by symbol, legs off against on (judge check of the Dual Thrust leg, AurumFunded v1.18).

Reads the deal tables of the two tester reports and sums profit + commission + swap of every closing deal per symbol,
plus the closing deals of the four Dual Thrust symbols by exit hour (22:00 flat against early closes, lesson 21).
"""
import collections
from html.parser import HTMLParser

RUNS = {
    "off": "backtests/2026-10-28_1213_AurumFunded_dual1_off/AurumFunded_dual1_off.htm",
    "on": "backtests/2026-10-28_1245_AurumFunded_dual1_on/AurumFunded_dual1_on.htm",
}
DUAL = ("US500.cash", "US100.cash", "GER40.cash", "JP225.cash")


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = ""

    def handle_endtag(self, tag):
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def num(x):
    return float(x.replace(" ", "")) if x else 0.0


def deals(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    p = Rows()
    p.feed(text)
    # Deals table: Time, Deal, Symbol, Type, Direction, Volume, Price, Order, Commission, Swap, Profit, Balance, Comment
    return [r for r in p.rows if len(r) == 13 and r[4] in ("out", "in/out", "in")]


res = {}
for name, path in RUNS.items():
    by = collections.defaultdict(lambda: [0, 0.0])
    hours = collections.Counter()
    ins = collections.Counter()
    for r in deals(path):
        sym = r[2]
        if r[4] == "in":
            ins[sym] += 1
            # an opening deal can carry commission
            by[sym][1] += num(r[8])
            continue
        by[sym][0] += 1
        by[sym][1] += num(r[8]) + num(r[9]) + num(r[10])
        if sym in DUAL:
            hours[(r[0][11:13], r[12] or "-")] += 1
    res[name] = by
    print(name)
    for s, (n, v) in sorted(by.items()):
        print(f"  {s:12s} closes {n:5d}  net {v:10.2f}  opens {ins[s]}")
    print("  total", round(sum(v for _, v in by.values()), 2))
    if name == "on":
        print("  index closes by hour/comment:", sorted(hours.items()))

# The leg sizes from equity, which grew from 10k to about 25k: sum each index close as a share of the balance before
# it, to compare with the Python's simple-return sum (+10.9% at size 1 to 2025-09-30, so about +5.45% at size 0.5).
# The off run's US index closes are the noise leg; on minus off is the Dual Thrust leg.
for name in RUNS:
    share = collections.defaultdict(float)
    for r in deals(RUNS[name]):
        if r[4] != "in" and r[2] in DUAL:
            pnl = num(r[8]) + num(r[9]) + num(r[10])
            share[r[2]] += pnl / (num(r[11]) - pnl)
    print("index pnl as share of balance,", name, {k: round(100 * v, 2) for k, v in share.items()},
          "sum %.2f%%" % (100 * sum(share.values())))

print("on - off by symbol")
for s in sorted(set(res["off"]) | set(res["on"])):
    d = res["on"][s][1] - res["off"][s][1]
    print(f"  {s:12s} {d:10.2f}  closes {res['on'][s][0] - res['off'][s][0]}")
