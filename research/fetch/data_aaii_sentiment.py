"""Fetch the AAII weekly sentiment survey history (public xls, no login) to marketdata/aaii/sentiment.xls."""
import os
import sys
import urllib.request

URL = "https://www.aaii.com/files/surveys/sentiment.xls"
OUT_DIR = os.path.join("marketdata", "aaii")
os.makedirs(OUT_DIR, exist_ok=True)
out = os.path.join(OUT_DIR, "sentiment.xls")
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 research-client"})
try:
    data = urllib.request.urlopen(req, timeout=120).read()
except Exception as e:
    print("fetch failed:", e)
    sys.exit(1)
if len(data) < 100000:
    print("file too small:", len(data))
    sys.exit(1)
with open(out, "wb") as f:
    f.write(data)
print("bytes", len(data), "->", out)
try:
    import pandas as pd
    x = pd.read_excel(out, sheet_name=None, header=None)
    for k, v in x.items():
        print(k, v.shape)
except Exception as e:
    print("parse note (needs xlrd):", e)
