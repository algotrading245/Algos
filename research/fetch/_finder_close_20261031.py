import json
closed = {
 "etula_dash_for_cash_short": ("dropped", "read in full (RFS 2020, acris.aalto.fi PDF, Tables 1-2): window T-8..T-4 US S&P -0.04%/day (-0.2% total, 5 days), sample ends 2013 and the paper has no post-2013 trading result; effect is below cost and pairs with the rejected long totm_us. No post-publication evidence"),
 "noise_rule_ger40_jpn225": ("dropped", "already run in research/noise_area_index.py docstring: DAX VM1.5 0.38 at 0.75bp (0.32|0.43), Nikkei 0.77 (0.98|0.56, 0.20 since 2022, JP225 spread nearer 2bp); Hydra 3.55 -> 3.57 with DAX, so no book gain"),
 "gao_intraday_momentum_etf": ("dropped", "already closed as sc3_gao_last_halfhour_gold / paper_baltussen_last30_index_mom and sources.jsonl line 175; market intraday momentum family rejected"),
 "heston_korajczyk_sadka_intraday_periodicity": ("dropped", "duplicate of heston_half_hour_continuation dropped 2026-10-26 (cross-sectional stocks, sample to 2005)"),
 "lucca_moench_pre_fomc": ("dropped", "on the stop list (pre-FOMC drift)"),
 "fed_feds_equity_overnight_day": ("dropped", "Lou-Polk-Skouras tug of war already closed in backlog_done line 249 (overnight_intraday family, swap cost)"),
 "quantpedia_asset_class_seasonality": ("dropped", "Halloween / sell in May already closed in backlog_done lines 130, 280, 322, 363"),
 "silver_gold_ratio_reversion": ("dropped", "gold-silver ratio already closed in backlog_done lines 196, 255"),
 "ml_meta_label_noise_leg": ("dropped", "ML overlays on existing legs on the steer stop list (12+ rejected)"),
 "leveraged_etf_rebalance_close": ("dropped", "leveraged-ETF rebalance already closed in backlog_done lines 86, 91, 172"),
}
keep = []
done = []
for l in open("docs/ideas/backlog.jsonl", encoding="utf8").read().splitlines():
    if not l.strip():
        continue
    d = json.loads(l)
    if d["id"] in closed:
        st, res = closed[d["id"]]
        d["status"] = st
        d["result"] = res
        done.append(d)
    else:
        keep.append(l)
open("docs/ideas/backlog.jsonl", "w", encoding="utf8").write("\n".join(keep) + "\n")
with open("docs/ideas/backlog_done.jsonl", "a", encoding="utf8") as f:
    for d in done:
        f.write(json.dumps(d) + "\n")
print(len(keep), len(done))
