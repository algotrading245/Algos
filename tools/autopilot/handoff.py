# Agent hand-over helper (owner 2026-10-18). Two jobs:
#
#   python tools/autopilot/handoff.py --next judge --reason "j16 collected" [--provisional]
#       Writes logs/autopilot/relay.json so the relay knows which agent comes next. Agents run it early in the run
#       with their best guess and --provisional, and again at the end without it; the final "HANDOFF: <role>" line
#       of the answer still wins (run-agent.ps1 rewrites the file after the run). A run that is cut off at the time
#       limit still hands over this way, so the chain never stalls.
#
#   python tools/autopilot/handoff.py --judged j16 [j17 ...]
#       Removes collected jobs from logs/autopilot/to-judge.json once the judge has judged them.
#
#   python tools/autopilot/handoff.py --tester-done
#       Removes logs/autopilot/tester-help.json once the tester agent has fixed what the script asked for, so
#       tester_step.py can go on.
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOGDIR = Path(__file__).resolve().parents[2] / "logs" / "autopilot"
RELAY = LOGDIR / "relay.json"
TO_JUDGE = LOGDIR / "to-judge.json"
TESTER_HELP = LOGDIR / "tester-help.json"
ROLES = ("judge", "finder", "builder", "tester", "monitor", "none")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--next", choices=ROLES, help="the agent the relay should start next")
    ap.add_argument("--reason", default="", help="one line for the relay log")
    ap.add_argument("--provisional", action="store_true", help="mark it as this run's early guess")
    ap.add_argument("--judged", nargs="+", metavar="JOB", help="job ids to remove from to-judge.json")
    ap.add_argument("--tester-done", action="store_true", help="remove tester-help.json")
    a = ap.parse_args()

    if a.next:
        old = {}
        try:
            old = json.loads(RELAY.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
        state = {
            "from": old.get("from") or "agent",
            "next": a.next,
            "due": datetime.now().isoformat(timespec="seconds"),
            "reason": a.reason,
        }
        if a.provisional:
            state["provisional"] = True
        if old.get("backoff_until"):
            state["backoff_until"] = old["backoff_until"]  # never write a limit away
        RELAY.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"relay.json: next {a.next} ({a.reason}){' provisional' if a.provisional else ''}")

    if a.judged:
        try:
            entries = json.loads(TO_JUDGE.read_text(encoding="utf-8-sig"))
        except Exception:
            entries = []
        entries = [e for e in entries if (e if isinstance(e, dict) else {"id": e}).get("id") not in a.judged]
        if entries:
            TO_JUDGE.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        else:
            TO_JUDGE.unlink(missing_ok=True)
        print(f"to-judge.json: removed {', '.join(a.judged)}")

    if a.tester_done:
        TESTER_HELP.unlink(missing_ok=True)
        print("tester-help.json removed")

    if not (a.next or a.judged or a.tester_done):
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
