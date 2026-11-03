"""Scheduled FOMC announcement dates 2009-2025 -> marketdata/fomc/fomc_dates.csv (date = last day of meeting).
2009-2020 scraped from federalreserve.gov historical pages (headings 'Month d-d Meeting - yyyy'; unscheduled skipped);
2021-2025 hard-coded from the published calendars. Run from repo root."""
import re, sys, os, csv, urllib.request

MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                           "September", "October", "November", "December"])}
rows = []
pat = re.compile(r"([A-Z][a-z]+)(?:/([A-Z][a-z]+))? (\d{1,2})(?:-(\d{1,2}))? Meeting - (\d{4})")
for y in range(2009, 2021):
    url = f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm"
    try:
        html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf8", "ignore")
    except Exception as e:
        print("fail", y, e); sys.exit(1)
    seen = set()
    for m in pat.finditer(html):
        m1, m2, d1, d2, yy = m.groups()
        if int(yy) != y:
            continue
        mon = MONTHS.get(m2 or m1)
        if not mon:
            continue
        day = int(d2 or d1)
        if m2:  # 'January/February 31-1' style: end in second month
            mon = MONTHS[m2]
        key = (y, mon, day)
        if key not in seen:
            seen.add(key); rows.append(f"{y}-{mon:02d}-{day:02d}")
    print(y, len([r for r in rows if r.startswith(str(y))]))
hard = """2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17""".split()
rows += hard
rows = sorted(set(rows))
os.makedirs("marketdata/fomc", exist_ok=True)
with open("marketdata/fomc/fomc_dates.csv", "w", newline="") as f:
    f.write("date\n" + "\n".join(rows) + "\n")
print(len(rows), "dates", rows[0], rows[-1])
if len(rows) < 120:
    sys.exit(1)
