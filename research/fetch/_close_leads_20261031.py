import json
R = {
"sc3_nystrup_jump_model_hold": "link arXiv 2005.07657 is a differential-geometry paper (Lopez, Krust theorem), read pp1-12, wrong paper; JM family just rejected (ml_jump_model_regime_long_indices: filter below own buy-and-hold)",
"sc3_bouman_halloween_indices": "Halloween/seasonal calendar family rejected 2026-10-23 (backlog_done line 130); no new post-2018 table found",
"sc3_turn_of_year_small_vs_large": "seasonal calendar family rejected; 2 markets, ~8 trades a decade, too few for DSR",
"sc3_opex_week_us500": "expiry-week index drift dropped 2026-10-19 (candidates.md calendar row, 64 events too few for DSR)",
"sc3_cieslak_fomc_even_weeks": "tested: research/fomc_cycle.py even-week S&P Sharpe 0.98 to 2017, 0.06 from 2018 (decisions 2026-10-25)",
"sc3_ranaldo_soderlind_safehaven": "already closed as ranaldo_soderlind_safe_haven (backlog_done line 204)",
"sc3_lunar_moon_indices": "queued/closed before as paper_lunar_new_moon_indices (queue line 74) and lunar_cycle_returns",
"sc3_gold_real_yield_residual": "Erb-Harvey DFII10 closed before (backlog_done lines 42, 186); gold real-yield macro timing fails after costs (decisions 2026-10-24)",
"sc3_gold_indian_wedding_seasonal": "gold festival windows queued 2026-10-25 as prebuilt_gold_holiday_drift; seasonal family rejected",
"sc3_zarattini_orb_5min_ndx": "ORB dropped before (backlog_done 55, 290; concretum QQQ 2018-2023 in-sample only, no OOS); opening-range breakout is the rejected channel-breakout family and overlaps breakout leg",
"sc3_heston_halfhour_periodicity": "queued and closed before (queue line 48, backlog_done 40, 205)",
"sc3_bogousslavsky_infrequent_rebal": "closed before as bl_bogousslavsky_rebalancing_autocorr (backlog_done 296)",
"sc3_hartzmark_solomon_dividend": "closed before (backlog_done 249)",
"sc3_conformal_skip_breakout": "entry-skip meta-labels on legs rejected; conformal abstain is the same target with a different threshold, no new evidence",
"sc3_eiie_leg_allocator": "duplicates drl_leg_sizing_ppo (decisions 2026-10-26)",
"sc3_isolation_forest_day_filter": "AUDCAD grid regime filters already queued twice (ml_regime_grid_audcad, variance-ratio gate); a third filter on the same leg adds trials and no new reason",
"sc3_euro_stoxx_lead_eurusd_open": "searched 2026-10-31: no paper found for index-to-EURUSD intraday lead (Albuquerque et al. is order flow, not tradable data); EURUSD intraday rules (Breedon-Ranaldo tod_eurusd) rejected as decayed",
"sc3_nikkei_open_usdjpy": "link is a statistics page, no published rule or post-publication evidence; not queued",
"sc3_eurusd_us_cash_open_reversal": "link is a JFE DOI placeholder with no matching paper; no rule source, EURUSD intraday daily rules all failed halves (results.md)",
"sc3_aqr_value_momentum_everywhere_idx": "AMP 2013 sample ends 2011, no post-publication table; index CFD data from 2010 gives ~15 monthly signals per market, too thin for DSR",
"sc3_quantpedia_fx_value_ppp_exit": "FX value/PPP and real-exchange-rate macro rules rejected; 5y reversal is the same signal",
}
p = "docs/ideas/backlog.jsonl"
rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
out = open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8")
keep = []
for r in rows:
    if r["id"] in R:
        r["status"] = "dropped"
        r["result"] = R[r["id"]]
        r["closed"] = "2026-10-31"
        out.write(json.dumps(r) + "\n")
    else:
        keep.append(r)
out.close()
with open(p, "w", encoding="utf-8") as f:
    for r in keep:
        f.write(json.dumps(r) + "\n")
print(len(rows), len(keep))
