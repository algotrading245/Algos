"""Fetch Michigan consumer sentiment (FRED UMCSENT, monthly) to marketdata/fred/UMCSENT.csv."""
import os
import sys
import urllib.request

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT"
OUT = "marketdata/fred/UMCSENT.csv"


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read().decode("utf-8")
    lines = [l for l in data.splitlines() if l.strip()]
    if len(lines) < 100:
        print("too few rows", len(lines))
        sys.exit(1)
    with open(OUT, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
    rows = lines[1:]
    print("rows", len(rows), "range", rows[0].split(",")[0], rows[-1].split(",")[0])


if __name__ == "__main__":
    main()
