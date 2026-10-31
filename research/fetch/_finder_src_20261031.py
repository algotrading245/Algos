import json
d = {"date": "2026-10-31", "kind": "paper", "title": "Etula, Rinne, Suominen, Vaittinen: Dash for Cash (RFS 2020), Tables 1-2 and settlement discussion",
     "link": "https://acris.aalto.fi/ws/portalfiles/portal/40965155/hhz054.pdf", "read": "in full", "specs": [],
     "note": "Sample to 2013, US T-8..T-4 return -0.04%/day, no post-publication result; dropped"}
open("docs/ideas/sources.jsonl", "a", encoding="utf8").write(json.dumps(d) + "\n")
