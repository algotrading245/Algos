import json
reasons = {
 "bis_qr_fx_dealers": "BIS QR latest page timed out twice (2026-10-25); no article read",
 "boe_swp_2025": "BoE staff WP page returns 0 results (listing empty, last updated 2024-04); nothing to read",
 "aqr_library_vol_managed": None,
 "mql5_codebase_session_ea": None,
 "quantconnect_strategy_library": "QC strategy library page loads via JS ('Loading strategies'); nothing readable, no FX/index rule extracted",
 "github_backtrader_forex": "awesome-systematic-trading README read to char 200000: tables list titles/Sharpe only; FX/gold candidates are gold-silver mean reversion (Gatev family rejected 2026-10-25), commodity long-run reversal (monthly, centuries), FX evolution review; none a costed readable rule",
 "arxiv_qfin_tr_2025_10": "arxiv list q-fin.TR/2510 returns 404 again",
 "opex_week_index": "opex_week_indices already tested and rejected (docs/gates/opex_week_indices.json, queue prebuilt_opex_week_indices)",
 "pre_holiday_index": "holidays listed in candidates.md calendar-drift row as no edge after 2017 / below cost",
 "sp500_tom_ftse": "turn of month rejected (docs/gates/totm_us.json, candidates.md calendar row)",
 "weekend_gap_fx": "weekend gap: gold weekend gaps rejected (candidates.md); FX version already queued as paper_dao_weekend_gap_reversal_fx",
 "gold_pm_fix_drift": "fix leg exists and Krohn fixing returns rejected family; would repeat fix leg (corr gate)",
}
rows = [json.loads(l) for l in open("docs/ideas/backlog.jsonl", encoding="utf-8") if l.strip()]
keep, done = [], []
for r in rows:
    why = reasons.get(r["id"])
    if why:
        r["status"] = "dropped"; r["result"] = why
        done.append(r)
    else:
        keep.append(r)
open("docs/ideas/backlog.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in keep))
open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in done))
print(len(keep), len(done))
