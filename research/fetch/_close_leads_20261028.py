import json
drops = {
 "jp225_overnight_intraday_split": "dropped: read Knuteson arXiv 2010.01727 (figure only, to 2020, no table/Sharpe); Boyarchenko overnight family already rejected (negative after spreads); CFD index trades near 24h so no close-open gap; no JP225 data",
 "us500_fomc_week_weeks": "dropped: read Hu-Pan-Wang-Zhu JFE 2022 (NBER 25817): sample 1994-May 2018, no post-publication result; Kurov-Wolfe-Gilbert find pre-FOMC drift gone since 2016; effect is overnight, ~44 days/yr, 10 bps, below index CFD costs+swap",
 "etf_flow_month_end_us500": "dropped: duplicate, Harvey-Mazzoleni-Melone already in queue.jsonl line 12",
}
p = "docs/ideas/backlog.jsonl"
rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
keep, done = [], []
for r in rows:
    if r["id"] in drops:
        r["status"] = "dropped"; r["result"] = drops[r["id"]]; done.append(r)
    else:
        keep.append(r)
open(p, "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in keep))
with open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8") as f:
    for r in done:
        f.write(json.dumps(r) + "\n")
with open("docs/ideas/sources.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"date": "2026-10-28", "kind": "paper", "title": "Hu, Pan, Wang, Zhu: Premium for heightened uncertainty (JFE 2022), pre-announcement returns", "link": "https://www.mit.edu/~zhuh/HuPanWangZhu_preannouncement.pdf", "read": "in full", "specs": []}) + "\n")
    f.write(json.dumps({"date": "2026-10-28", "kind": "paper", "title": "Knuteson: Strikingly suspicious overnight and intraday returns", "link": "https://arxiv.org/pdf/2010.01727.pdf", "read": "in full", "specs": []}) + "\n")
print(len(keep), len(done))
