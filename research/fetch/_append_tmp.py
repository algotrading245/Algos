import json
done = [
 ("bl_vwap_holy_grail_indices", "dropped", "Read concretum page: QQQ only 2018-2023-09 full-sample Sharpe 2.1, no out-of-sample; VWAP trend is in rejected intraday-momentum family (candidates.json)"),
 ("bl_dm_momentum_crash_dynamic", "dropped", "Read NBER w20439 pp1-12 of 52: equity cross-section WML crash timing, data ends 2013, no post-2018 result; not a gold-trend filter rule"),
 ("bl_quantpedia_fx_intraday_cat_p2", "dropped", "Category page 404; screener lists only 4 currency strategies (carry, momentum, PPP value, dollar carry), all failed styles"),
 ("bl_london_ny_session_continuation_eurusd", "dropped", "No published post-2018 FX result (only RUB-USD Elaut 2018, 2005-2014); same family as rejected intraday momentum"),
]
with open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8") as f:
    for i, s, r in done:
        f.write(json.dumps({"id": i, "status": s, "added": "2026-10-29", "closed": "2026-10-29", "result": r}) + "\n")
src = [
 ("paper", "Zarattini-Aziz VWAP the Holy Grail (concretum page)", "https://concretumgroup.com/volume-weighted-average-price-vwap-the-holy-grail-for-day-trading-systems/", "unverified"),
 ("paper", "Daniel-Moskowitz Momentum Crashes NBER w20439", "https://www.nber.org/papers/w20439", "unverified"),
 ("prebuilt", "Quantpedia currencies screener (4 strategies, all carry/momentum/value)", "https://quantpedia.com/screener/?category=currencies", "in full"),
]
with open("docs/ideas/sources.jsonl", "a", encoding="utf-8") as f:
    for k, t, l, r in src:
        f.write(json.dumps({"date": "2026-10-29", "kind": k, "title": t, "link": l, "read": r, "specs": []}) + "\n")
