"""Fetch Michigan consumer sentiment (FRED UMCSENT, monthly) to marketdata/fred/UMCSENT.csv.
v2: v1 timed out on the read; retries, longer timeout, two URLs, a plain-text fallback."""
import os
import sys
import time
import urllib.request

URLS = [
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT&cosd=1990-01-01&coed=2025-10-01",
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT",
    "https://fred.stlouisfed.org/data/UMCSENT.txt",
]
OUT = "marketdata/fred/UMCSENT.csv"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("utf-8", "replace")


def parse_txt(data):
    rows = []
    for l in data.splitlines():
        p = l.split()
        if len(p) == 2 and len(p[0]) == 10 and p[0][4] == "-":
            rows.append(p[0] + "," + p[1])
    return ["observation_date,UMCSENT"] + rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lines = []
    for attempt in range(3):
        for u in URLS:
            try:
                data = get(u)
                ls = [l for l in data.splitlines() if l.strip()]
                if u.endswith(".txt"):
                    ls = parse_txt(data)
                if len(ls) >= 100:
                    lines = ls
                    break
            except Exception as e:
                print("fail", u, repr(e))
        if lines:
            break
        time.sleep(10)
    if not lines:
        print("no data")
        sys.exit(1)
    with open(OUT, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
    rows = lines[1:]
    print("rows", len(rows), "range", rows[0].split(",")[0], rows[-1].split(",")[0])


if __name__ == "__main__":
    main()
