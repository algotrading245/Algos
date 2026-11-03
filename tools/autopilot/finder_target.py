# Finder target (owner 2026-11-02): each finder run aims at one named gap of the book, in turn, so runs stop drifting
# to the crowded markets. The relay calls this just before it starts the finder and passes the line it prints in the
# finder's "Started by the relay because" note.
#
#   python tools/autopilot/finder_target.py [--peek]      (--peek: print the next target, do not advance)
#
# Targets come from docs/gaps.json (tools/gaps.py): each market without a leg, each style without a leg, and the thin
# horizons as one target. The turn is kept in logs/autopilot/finder-target.json.
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GAPS = REPO / "docs" / "gaps.json"
STATE = REPO / "logs" / "autopilot" / "finder-target.json"


def targets():
    try:
        g = json.loads(GAPS.read_text(encoding="utf-8")).get("gaps", {})
    except Exception:
        return []
    out = [f"market {m} (no leg)" for m in g.get("markets_without_leg", [])]
    out += [f"style {s} (no leg)" for s in g.get("styles_without_leg", [])]
    if g.get("thin_horizons"):
        out.append(f"horizon {'/'.join(g['thin_horizons'])} (thin)")
    return out


def main():
    t = targets()
    if not t:
        return
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    # continue after the last target used; a target list that changed starts from its first item
    last = st.get("last")
    i = (t.index(last) + 1) % len(t) if last in t else 0
    print(f"target gap: {t[i]}")
    if "--peek" not in sys.argv:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"last": t[i], "at": dt.datetime.now().isoformat(timespec="seconds"),
                                     "all": t}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
