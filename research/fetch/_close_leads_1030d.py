import json
reasons = {
 "sc_eurgbp_range_meanrev": "dropped: read MQL5 CodeBase 78687 (FxCraft Bollinger 20/2 reversion): educational demo-only EA, no results page, Bollinger reversion on FX/AUDCAD already rejected many times",
 "sc_hurst_switch_breakout_grid": "dropped: Hurst filter searched 2026-10-22 (practitioner only) and the same-type regime gate variance_ratio_grid_gate was rejected 2026-10-30 (book 2018+ 3.40->3.27)",
 "sc_mql5_codebase_experts_p5": "dropped: read page 5; items are Awesome Oscillator pullback (no code page found), FxCraft Bollinger/range breakout (educational, no results), Monday Dip (rejected 0.18/0.05), GER40 coil and NR7 ORB (tested), rest utilities",
 "sc_ssrn_alt_arxiv_vol_clustering_fx": "dropped: search for EURUSD squeeze breakout found only TradingView/MQL5 indicator pages and one blog (1h entropy, not daily, unverifiable); squeeze/NR7 already rejected",
}
keep = []
done = []
for line in open("docs/ideas/backlog.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    if d["id"] in reasons:
        d["status"] = "dropped"
        d["result"] = reasons[d["id"]]
        done.append(d)
    else:
        keep.append(line)
open("docs/ideas/backlog.jsonl", "w", encoding="utf-8").write("\n".join(keep) + "\n")
with open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8") as f:
    for d in done:
        f.write(json.dumps(d) + "\n")
with open("docs/ideas/sources.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"date": "2026-10-30", "kind": "prebuilt", "title": "FxCraft Example EA - Bollinger Bands mean reversion (MQL5 CodeBase 78687)", "link": "https://www.mql5.com/en/code/78687", "read": "in full", "specs": []}) + "\n")
print(len(keep), len(done))
