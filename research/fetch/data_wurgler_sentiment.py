"""Fetch Baker-Wurgler sentiment proxies (monthly) from Wurgler's free page.
Writes marketdata/sentiment/wurgler_proxies.csv. Run from repo root."""
import io, os, sys, urllib.request
import pandas as pd

URLS = [
    "https://pages.stern.nyu.edu/~jwurgler/data/Investor_Sentiment_Data_v23_POST.xlsx",
    "https://pages.stern.nyu.edu/~jwurgler/data/Investor_Sentiment_Data_v22_POST.xlsx",
    "https://pages.stern.nyu.edu/~jwurgler/data/Investor_Sentiment_Data_20190327_POST.xlsx",
    "https://people.stern.nyu.edu/jwurgler/data/Investor_Sentiment_Data_v23_POST.xlsx",
]
raw = None
for u in URLS:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=60).read()
        if raw[:2] == b"PK":
            print("got", u, len(raw))
            break
        raw = None
    except Exception as e:
        print("fail", u, e)
if raw is None:
    sys.exit("no Wurgler file reachable")

xl = pd.ExcelFile(io.BytesIO(raw))
print("sheets", xl.sheet_names)
best = None
for sh in xl.sheet_names:
    df = xl.parse(sh, header=None)
    # find header row containing yearmo
    for i in range(min(10, len(df))):
        row = [str(x).lower() for x in df.iloc[i].tolist()]
        if any("yearmo" in x for x in row):
            d = xl.parse(sh, header=i)
            d.columns = [str(c).strip() for c in d.columns]
            if best is None or len(d) > len(best):
                best = d
            break
if best is None:
    sys.exit("no yearmo header found")
best = best.dropna(subset=[best.columns[0]])
os.makedirs("marketdata/sentiment", exist_ok=True)
best.to_csv("marketdata/sentiment/wurgler_proxies.csv", index=False)
print(list(best.columns))
print("rows", len(best), "first", best.iloc[0, 0], "last", best.iloc[-1, 0])
