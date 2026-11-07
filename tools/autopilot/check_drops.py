# Drop check (owner 2026-11-02): the finder kept dropping leads for reasons the owner ruled out ("behind a paywall",
# "no post-2018 number") and pasted one reason onto two different papers. A prompt rule alone did not hold, so the
# relay runs this after every finder run and reopens a drop that breaks the rules.
#
#   python tools/autopilot/check_drops.py [--dry-run] [--from-line N]
#
# A drop in docs/ideas/backlog_done.jsonl (status "dropped") is refused when its reason
#   - is copied: the same text as another lead's drop (each paper needs its own reason), or
#   - rests on access: paywall / no free full text, naming fewer than 3 places tried, or
#   - rests on "no post-2018 / out-of-sample number" without a later study (author and year) that shows a failure.
# A refused drop is marked "drop_refused" and the lead goes back to docs/ideas/backlog.jsonl as open, with the
# reason, so the finder runs its own test or names the study. After 3 refusals of one lead the drop stands and is
# listed for the doctor (logs/autopilot/check-drops.json, "stands").
import argparse
import datetime as dt
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IDEAS = REPO / "docs" / "ideas"
DONE = IDEAS / "backlog_done.jsonl"
OPEN = IDEAS / "backlog.jsonl"
STATE = REPO / "logs" / "autopilot" / "check-drops.json"
MAX_REFUSALS = 3

ACCESS = re.compile(r"paywall|no free (full )?text|cannot be read|could not (be )?read|not read in full|"
                    r"full text (is )?(not|un)available|behind (a |the )?(login|paywall)", re.I)
NO_OOS = re.compile(r"no (post-?20\d\d|oos|out-of-sample|recent)( \w+)? (number|evidence|result|test)|"
                    r"no (oos|out-of-sample) (number|evidence)", re.I)
PLACES = re.compile(r"nber|ssrn|repec|ideas\b|econpapers|scholar|author|university|repository|researchgate|"
                    r"semantic ?scholar|sciencedirect|jstor|arxiv|course|syllabus|econbiz|core\.ac|google|"
                    r"wiley|springer|personal page|homepage|working paper", re.I)
LATER = re.compile(r"\b[A-Z][A-Za-z&.\-]+(?: (?:and|&|et al\.?) ?[A-Z]?[A-Za-z.\-]*)? \(?(?:19|20)\d\d\)?")
FAILED = re.compile(r"fail|weak|obsolete|insignificant|no longer|disappear|gone|negative|did not|does not|"
                    r"not significant|reversed|decay|vanish|no (out-of-sample|oos) (power|gain|predictab)", re.I)


def read(p):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write(p, rows):
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"\(?(third|second|fourth)? ?reopen\)?", "", text.lower())).strip()


def verdict(r, same_text_ids):
    """None when the drop stands, else why it is refused."""
    why = str(r.get("result", ""))
    # a short note on a source scan ("listing URL 404", "nothing queueable") may repeat; a paper's reasoning may not
    if len(same_text_ids) > 1 and len(why) > 80:
        return f"copied reason: the same text closed {', '.join(sorted(same_text_ids))}; each lead needs its own"
    if LATER.search(why) and FAILED.search(why) and not re.search(r"says such|such predictors|in general", why, re.I):
        return None                  # a later study that shows a failure is the valid drop reason
    places = {m.group(0).lower() for m in PLACES.finditer(why)}
    if ACCESS.search(why) and len(places) < 3:
        return f"paywall drop naming {len(places)} place(s) tried; try NBER, the authors' pages, RePEc/IDEAS, Scholar versions"
    if NO_OOS.search(why) and not (LATER.search(why) and FAILED.search(why)):
        return "'no post-2018 number' is not a drop reason: run our own 2018+ test, or name a later study that shows it failed"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-line", type=int, default=None, help="check from this line of backlog_done.jsonl (0-based)")
    a = ap.parse_args()

    done = read(DONE)
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    start = a.from_line if a.from_line is not None else int(st.get("checked", len(done)))
    start = max(0, min(start, len(done)))
    new = list(range(start, len(done)))

    # copies: the same reason text on different ids, among the new drops and the day's earlier ones
    by_text = {}
    for i, r in enumerate(done):
        if r.get("status") == "dropped" and r.get("result"):
            by_text.setdefault(norm(r["result"]), set()).add(r["id"])

    first = {}                       # earliest record of an id carries gap/kind/title/link
    for r in done:
        first.setdefault(r["id"], r)
    refusals = {}
    for r in done:
        if r.get("status") == "drop_refused":
            refusals[r["id"]] = refusals.get(r["id"], 0) + 1
    open_ids = {r["id"] for r in read(OPEN) if r.get("status") == "open"}

    reopened, stands = [], list(st.get("stands", []))
    for i in new:
        r = done[i]
        if r.get("status") != "dropped" or r["id"] in open_ids:
            continue
        v = verdict(r, by_text.get(norm(str(r.get("result", ""))), {r["id"]}))
        if not v:
            continue
        n = refusals.get(r["id"], 0)
        if n >= MAX_REFUSALS:
            stands.append({"id": r["id"], "at": dt.datetime.now().isoformat(timespec="seconds"), "why": v})
            print(f"stands after {n} refusals (for the doctor): {r['id']}: {v}")
            continue
        done[i] = dict(r, status="drop_refused", refused=v)
        f = first[r["id"]]
        reopened.append(dict(id=r["id"], gap=f.get("gap", ""), kind=f.get("kind", ""), title=f.get("title", ""),
                             link=f.get("link", ""), status="open", added=dt.date.today().isoformat(), result="",
                             note=(f"Drop refused by check_drops.py ({dt.date.today()}): {v}. The refused drop said: "
                                   f"{r.get('result', '')} | Earlier note: {f.get('note', '')}")[:3000]))
        refusals[r["id"]] = n + 1
        print(f"refused: {r['id']}: {v}")

    if a.dry_run:
        print(f"dry run: {len(reopened)} would reopen, lines {start}-{len(done)} checked")
        return
    if reopened:
        write(DONE, done)
        with OPEN.open("a", encoding="utf-8") as fh:
            for r in reopened:
                fh.write(json.dumps(r) + "\n")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"checked": len(done), "at": dt.datetime.now().isoformat(timespec="seconds"),
                                 "stands": stands[-50:]}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
