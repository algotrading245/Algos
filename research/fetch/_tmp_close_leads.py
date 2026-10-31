import json
res = {
 "bis_wp_fx_hedging_flows": ("done", "queued paper_melvin_prins_eom_equity_hedge (BIS list has no month-end paper; Melvin-Prins read pp.1-22)"),
 "ecb_wp_euro_announce": ("dropped", "ECB announcement drift: event studies only, no tradeable rule; steer.md says stop bringing pre-ECB/FOMC drift"),
 "fed_feds_intraday_fx": ("dropped", "Read IFDP list page 2026-10-25: only IFDP 2026-1446 (Japanese multinationals) and 2026-1445 (dollar and global cycle), neither has an intraday FX rule"),
 "ml_metalabel_breakout": ("dropped", "meta-labeling tested twice with no skill (ml_metalabel_breakout_size AUC 0.51-0.53; meta_label_hydra); same recipe not retried"),
 "ml_metalabel_fix": ("dropped", "same recipe as the two rejected meta-label tests (no skill); fix/cross corr 0.61 makes a filter on fix a low-gain leg"),
}
b = [json.loads(l) for l in open("docs/ideas/backlog.jsonl", encoding="utf-8") if l.strip()]
keep, done = [], []
for r in b:
    if r["id"] in res:
        r["status"], r["result"] = res[r["id"]]
        done.append(r)
    else:
        keep.append(r)
open("docs/ideas/backlog.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in keep))
open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in done))
s = {"date": "2026-10-25", "kind": "paper", "title": "Melvin-Prins equity hedging and exchange rates at the London 4pm fix (read pp.1-22 in full)", "link": "https://ecb.eu/events/pdf/conferences/131216/Third_FX_Workshop_MELVIN_PRINS_Equity%20hedging%20and%20exchange%20rates%20Nov%202013.pdf", "read": "in full", "specs": []}
s2 = {"date": "2026-10-25", "kind": "paper", "title": "Fed IFDP list page (no intraday FX rule)", "link": "https://www.federalreserve.gov/econres/ifdp/", "read": "in full", "specs": []}
open("docs/ideas/sources.jsonl", "a", encoding="utf-8").write(json.dumps(s) + "\n" + json.dumps(s2) + "\n")
print(len(keep), len(done))
