"""Fetch Michigan consumer sentiment (monthly) to marketdata/fred/UMCSENT.csv.
v3: FRED closed the connection on v1/v2 (RemoteDisconnected, timeouts). Adds the FRED download-data URL, the
University of Michigan's own table (sca.isr.umich.edu tbmics.csv: Month, Year, Index) and a wait of 60 s between rounds."""
import csv
import io
import os
import sys
import time
import urllib.request

OUT = "marketdata/fred/UMCSENT.csv"
HEAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.8",
}
FRED = [
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT",
    "https://fred.stlouisfed.org/series/UMCSENT/downloaddata/UMCSENT.csv",
    "https://fred.stlouisfed.org/data/UMCSENT.txt",
]
UMICH = ["https://www.sca.isr.umich.edu/files/tbmics.csv", "http://www.sca.isr.umich.edu/files/tbmics.csv"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def get(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def parse_txt(data):
    rows = []
    for l in data.splitlines():
        p = l.split()
        if len(p) == 2 and len(p[0]) == 10 and p[0][4] == "-":
            rows.append(p[0] + "," + p[1])
    return ["observation_date,UMCSENT"] + rows


def parse_umich(data):
    rows = []
    for rec in csv.reader(io.StringIO(data)):
        if len(rec) >= 3 and rec[0].strip() in MONTHS:
            try:
                m = MONTHS.index(rec[0].strip()) + 1
                rows.append("%04d-%02d-01,%s" % (int(rec[1]), m, float(rec[2])))
            except ValueError:
                pass
    return ["observation_date,UMCSENT"] + rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lines = []
    for attempt in range(3):
        for u in FRED + UMICH:
            try:
                data = get(u)
                if "umich" in u:
                    ls = parse_umich(data)
                elif u.endswith(".txt"):
                    ls = parse_txt(data)
                else:
                    ls = [l for l in data.splitlines() if l.strip()]
                if len(ls) >= 300:
                    lines = ls
                    print("ok", u)
                    break
                print("short", u, len(ls))
            except Exception as e:
                print("fail", u, repr(e))
        if lines:
            break
        time.sleep(60)
    if not lines:
        print("no data")
        sys.exit(1)
    with open(OUT, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
    rows = lines[1:]
    print("rows", len(rows), "range", rows[0].split(",")[0], rows[-1].split(",")[0])


if __name__ == "__main__":
    main()
