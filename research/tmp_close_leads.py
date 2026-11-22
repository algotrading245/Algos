import json
drop = {
 "bl_conformal_trade_filter": "dropped: meta-labeling the breakout leg already tested, no skill (ml_metalabel_breakout_size AUC 0.51-0.53, book 3.34->3.32); conformal filter is the same signal with a different wrapper",
 "bl_bogousslavsky_rebalancing_autocorr": "dropped: half-hour/day-of-week autocorrelation is the intraday-momentum family already in the book (noise leg) and rejected as new; no post-2018 index CFD result",
 "bl_andersen_micro_macro_announce": "dropped: 2003 paper on 1992-1998 data, no post-publication result; EURUSD announcement reaction already covered in earlier finder runs",
 "bl_avellaneda_lee_index_pairs": "dropped: read abstract/summaries: paper is stock-level PCA/ETF residuals 1997-2007 (Sharpe 1.44 PCA, 1.51 ETF), no result after 2018 and no index-pair version; 4 index CFDs are too few for an OU residual set. No post-publication evidence",
 "bl_treasury_auction_cycle": "dropped: Treasury auction price pressure is a bond-yield result 1980-2008; logged several times as no FX/gold/index test (decisions 2026-10-23/24)",
 "bl_fomc_cycle_even_week_indices": "dropped: paper_fomc_cycle_even_weeks rejected 2026-10-25, S&P even-week Sharpe 0.98 to 2017 and 0.06 from 2018 (research/fomc_cycle.py)",
}
rows = [json.loads(l) for l in open("docs/ideas/backlog.jsonl", encoding="utf-8") if l.strip()]
keep, done = [], []
for r in rows:
    if r["id"] in drop:
        r["status"] = "dropped"; r["result"] = drop[r["id"]]; done.append(r)
    else:
        keep.append(r)
open("docs/ideas/backlog.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in keep))
open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in done))
src = {"date": "2026-10-29", "kind": "paper", "title": "Avellaneda and Lee 2010 Statistical arbitrage in the US equities market (stock-level, 1997-2007, no post-2018 result)", "link": "https://doi.org/10.1080/14697680903124632", "read": "unverified", "specs": []}
open("docs/ideas/sources.jsonl", "a", encoding="utf-8").write(json.dumps(src) + "\n")
print(len(keep), len(done))
