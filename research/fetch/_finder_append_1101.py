import json
done = [
 {"id": "arxiv_trd_2505", "gap": "days horizon", "kind": "paper", "title": "arXiv q-fin.TR listing May 2025", "link": "https://arxiv.org/list/q-fin.TR/2505", "note": "WebFetch HTTP 404 on listing URL", "status": "dropped", "added": "2026-11-01", "result": "listing URL returns 404 (also 429 earlier); no paper read"},
 {"id": "yang_gold_oil_ratio", "gap": "weeks+ horizon", "kind": "paper", "title": "Yang (2024) Gold is a Hedging Asset, PHBS WP 20240605", "link": "https://english.phbs.pku.edu.cn/uploadfile/2024/0530/20240530100231471.pdf", "note": "log(gold/oil) predicts US stock excess returns, 1 SD = 7.3%/yr at 1 week, 1975-2022 sample", "status": "dropped", "added": "2026-11-01", "result": "read pp.1-12: in-sample regressions 1975-2022, only a one-line OOS claim, no post-2018 table or trading rule; predictive size ~7%/yr per SD is below cost-bearing Sharpe; fails evidence check"},
]
with open("docs/ideas/backlog_done.jsonl", "a", encoding="utf-8") as f:
    for d in done:
        f.write(json.dumps(d) + "\n")
src = {"date": "2026-11-01", "kind": "paper", "title": "Yang (2024) Gold is a Hedging Asset (gold-oil ratio predicts stock returns)", "link": "https://english.phbs.pku.edu.cn/uploadfile/2024/0530/20240530100231471.pdf", "read": "unverified", "specs": []}
with open("docs/ideas/sources.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(src) + "\n")
