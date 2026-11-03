"""Fetch Ken French 48 industry portfolios (daily, value weighted) and write marketdata/french_48ind_daily.csv."""
import io
import sys
import urllib.request
import zipfile
import os

URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/48_Industry_Portfolios_daily_CSV.zip"
OUT = "marketdata/french_48ind_daily.csv"


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    txt = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    rows = []
    header = None
    for ln in txt:
        parts = [p.strip() for p in ln.split(",")]
        if header is None:
            if len(parts) > 40 and parts[1] == "Agric":
                header = ["date"] + parts[1:]
            continue
        if not parts[0].isdigit() or len(parts[0]) != 8:
            if rows:
                break  # end of first (value weighted) block
            continue
        rows.append(parts)
    if not rows:
        print("no rows parsed")
        sys.exit(1)
    os.makedirs("marketdata", exist_ok=True)
    with open(OUT, "w") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    print(len(rows), "rows", rows[0][0], "to", rows[-1][0])


if __name__ == "__main__":
    main()
