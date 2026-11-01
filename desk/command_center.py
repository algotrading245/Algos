"""The Aurum Command Center page (desk/dashboard/command_center.html) with the desk's live data patched in.

The file is a bundle: an outer page whose manifest holds one gzipped inner page per screen (Main, Pods, EAs,
Processes, Research, Controls, Agents). Each inner page carries its HTML as a JSON string in a template script.
build() decodes each screen, patches it, and packs it back, so the design stays exactly as uploaded.

Live on every screen: the "Live Snapshot" label and chip, and the sample simulation is stopped (the clock still ticks).
Live on Main: role runs, tokens, last run and task (this budget week), the agent talk feed from the relay log, the
desk's open positions, and the kill button, which POSTs /api/kill. With extra = {"state": /api/state, "queue": queue
rows}: the desk card (equity, balance, P/L, margin, last tick), drawdown and daily loss, the live-gate checks, the pod
rows, the needs-you alerts and the idea queue. The alerts card also lists every desk/inbox/ALERT.md section (dated) and
the doctor's open items from docs/autopilot/gaps_report.md, with text-hashed ids so an ack holds. From the usage log and docs/: the token chart (today, per role), the
recent runs, the Tokens/Runs Today KPIs, the funnel (log-scale bars) and the first failing gate per gate file. From
the machine itself (psutil): the process list (MT5 terminals, desk servers, Hermes, Claude) and the RAM and commit
lines. The activity feed: today's agent runs, journal rows and git commits, newest first. The funded card and Funded
Equity KPI from the T16 AurumFunded EA log (read only; private lines dropped). Live on Pods (from the same state): each pod's allocation, work and
talk counts, and its scorekeeper record in place of the old XP, level and IQ (P&L, hit rate, trades, R, profit factor,
drawdown and score, last 8 weeks, from logs/desk/state/scores.json), the board posts, the tickets, the KPI row, each
pod's brief line (markets owned, state, P&L and hit rate), its wakes from the config schedule and what it knows (its own
knowledge entries, most endorsed first); the rules are still design text. Live on EAs: equity, balance, the kill floor,
the daily-loss and kill guards (red when halted), open positions, each EA's version from its .mq5 file, the archive
list from mql5/Experts/_archive, and the Hydra legs from the armed edges (risk per leg); trade counts, today's
P/L per leg, the diff rows and the other guards are still design text. Live on Processes: each scheduled job's last run
and state (Late past its window, Failed if its newest runner job failed), the recent runs and the run and failure KPIs
from the desk runner, and the MT5, relay, scheduler and feed heartbeats; Doctor, Watchdog, the finder loop, the tester
queue and beat, and the demo beat are still design text. Live on Research: the funnel counts, the candidates, the
gaps, the rejected list and the KPI row from docs/. Live on Controls: the pod, pipeline and demo-leg switches (paused,
halted, last run), the locks (risk file, halt, live trading, pending approvals), the funded risk block from
desk/risk.json and the desk limits, and the change log from the journal; the 5x EA risk block, the MT5 lock and the
trades-per-day limit are still design text. Live on Agents: each role's tier, model, turn and minute caps from the
router, its runs, tokens and last run this week, its last reason, the finder back-off, runs today, the provider and
fallback, the next role in the hand-over, the last limit hit and the relay log; the weekly charts, seats, steps, retry
ladder and empty-run list are still design text. The rest is still the design's sample content.
"""
import base64
import collections
import datetime as dt
import gzip
import html
import json
import pathlib
import re
import time

_MANIFEST = re.compile(r'(<script type="__bundler/manifest">\s*)(.*?)(\s*</script>)', re.S)
_ORDER = re.compile(r'<script type="__bundler/page_order">\s*(.*?)\s*</script>', re.S)
_TEMPLATE = re.compile(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)', re.S)
ROLES = ["finder", "builder", "tester", "judge", "reviewer", "monitor", "doctor", "portfolio"]
_CACHE = {"t": 0.0, "body": None}
TTL = 15


def _js(s):
    # Text going into single-quoted JS strings in the template.
    return s.replace("\\", "/").replace("'", "’").replace("\n", " ")


def _weeks_tokens(usage, now=None, n=4):
    """Tokens per role (millions) for the last n ISO weeks, oldest first, from usage.jsonl rows. Returns
    (week numbers, [(role, [m1..mn])]) with roles that used any tokens, most tokens this week first."""
    now = now or dt.datetime.now()
    mon = (now - dt.timedelta(days=now.weekday())).date()
    starts = [mon - dt.timedelta(weeks=n - 1 - i) for i in range(n)]
    tok = collections.defaultdict(lambda: [0] * n)
    for r in usage or []:
        try:
            d = dt.date.fromisoformat(str(r.get("ts") or "")[:10])
        except ValueError:
            continue
        i = (d - starts[0]).days // 7
        if 0 <= i < n:
            tok[r.get("role") or "?"][i] += sum(int(r.get(k) or 0) for k in ("input", "output", "cache_read", "cache_create"))
    rows = [(role, [round(x / 1e6, 2) for x in v]) for role, v in tok.items() if any(v)]
    rows.sort(key=lambda x: (-x[1][-1], -sum(x[1])))
    return [s.isocalendar()[1] for s in starts], rows


def _patch_weeks(src, usage, now=None):
    weeks, rows = _weeks_tokens(usage, now)
    if not rows:
        return src
    arr = "const WEEKS = " + json.dumps([[_title(r), v] for r, v in rows], ensure_ascii=False) + ";"
    src = re.sub(r"const WEEKS = \[\n.*?\n\];", lambda _: arr, src, count=1, flags=re.S)
    return src.replace("Weeks 41 To 44, Millions Of Tokens", f"Weeks {weeks[0]} To {weeks[-1]}, Millions Of Tokens", 1)


def _week_agg(live, usage):
    week0 = (live.get("budget") or {}).get("week_start") or ""
    agg = collections.defaultdict(lambda: {"runs": 0, "tok": 0, "last": ""})
    for r in usage or []:
        ts = str(r.get("ts") or "")
        if not ts or ts < week0:
            continue
        a = agg[r.get("role") or "?"]
        a["runs"] += 1
        a["tok"] += sum(int(r.get(k) or 0) for k in ("input", "output", "cache_read", "cache_create"))
        a["last"] = max(a["last"], ts)
    return agg


def _patch_roles(src, live, agg):
    roles = live.get("roles") or {}

    def one(m):
        rid, body = m.group(1), m.group(0)
        a = agg.get(rid)
        st = (roles.get(rid) or {}).get("state") or {}
        runs = a["runs"] if a else 0
        tok = a["tok"] / 1e6 if a else 0.0
        last = a["last"][11:16] if a and a["last"] else "—"
        body = re.sub(r"runs: [\d.]+", f"runs: {runs}", body, count=1)
        body = re.sub(r"tokens: [\d.]+", f"tokens: {tok:.2f}", body, count=1)
        body = re.sub(r"last: '[^']*'", lambda _: f"last: '{last}'", body, count=1)
        if st.get("reason"):
            reason = _js(str(st["reason"]))[:60].title()
            body = re.sub(r"task: '[^']*'", lambda _: f"task: 'Last Run: {reason}'", body, count=1)
            note = f"Last Run: {reason}"
        else:
            note = "No Note From The Last Run"
        # The design's perf triples, scores and thoughts are invented; these are the measured ones.
        body = re.sub(r"thought: '[^']*'", lambda _: f"thought: '{note}'", body, count=1)
        perf = [[str(runs), "Runs This Week"], [f"{tok:.2f}M", "Tokens This Week"], [last, "Last Run"]]
        body = re.sub(r"perf: \[\[.*?\]\]", lambda _: "perf: " + json.dumps(perf, ensure_ascii=False).replace('"', "'"),
                      body, count=1, flags=re.S)
        body = re.sub(r"score: \d+ \}$", f"score: {runs} }}", body)
        return body

    return re.sub(r"\{ id: '(\w+)'.*?score: \d+ \}", one, src, flags=re.S)


def _patch_talk(src, live):
    steps = live.get("steps") if isinstance(live.get("steps"), dict) else {}
    talk, seen = [], set()
    for line in reversed(steps.get("relay") or []):
        m = re.match(r"\S+ (\d\d:\d\d):\d\d\s+(.*)", str(line))
        if not m:
            continue
        t, text = m.groups()
        frm = next((r for r in ROLES if r in text.split()[:3]), None)
        if not frm:
            continue
        nxt = re.search(r"next (\w+)", text)
        to = nxt.group(1) if nxt and nxt.group(1) in ROLES else "owner"
        why = _js(re.sub(r"\s+", " ", text))[:80]
        key = re.sub(r"\d", "", why)
        if key in seen:
            continue
        seen.add(key)
        talk.append([t, frm, to, why[:1].upper() + why[1:]])
    if not talk:
        return src
    js = json.dumps(talk[:6], ensure_ascii=False)
    return re.sub(r"const BASE_TALK = \[.*?\];", lambda _: f"const BASE_TALK = {js};", src, count=1, flags=re.S)


def _num(x, nd):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if v == 0 else f"{v:,.{nd}f}"


def _patch_positions(src, positions):
    rows = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        price = p.get("price_open")
        nd = 3 if isinstance(price, (int, float)) and price < 1000 else 2
        pl = float(p.get("profit") or 0)
        side = str(p.get("side") or ("buy" if p.get("type") == 0 else "sell")).title()
        rows.append({"acct": "Desk", "leg": _js(str(p.get("comment") or "Desk"))[:28], "sym": _js(str(p.get("symbol") or "?")),
                     "side": side, "lots": f"{float(p.get('volume') or 0):.2f}", "entry": _num(price, nd),
                     "sl": _num(p.get("sl"), nd), "tp": _num(p.get("tp"), nd),
                     "pl": ("+" if pl >= 0 else "−") + f"{abs(pl):,.2f}", "t": "Live"})
    js = json.dumps(rows, ensure_ascii=False)
    return re.sub(r"const posAll = \[.*?\n    \];", lambda _: f"const posAll = {js};", src, count=1, flags=re.S)


_KILL_OLD = "confirmKill: () => this.setState({ killArmed: false, killed: true, "
_KILL_END = ".concat(s.events) })"
_KILL_NEW = ("confirmKill: () => (fetch(location.origin + '/api/kill', { method: 'POST', headers: { 'X-Desk': 'kill', "
             "'Content-Type': 'application/json' }, body: JSON.stringify({ why: 'kill switch on the dashboard' }) })"
             ".catch(() => null), this.setState({ killArmed: false, killed: true, ")


def _wire_kill(src):
    if _KILL_OLD not in src:
        return src
    head, tail = src.split(_KILL_OLD, 1)
    end = tail.index(_KILL_END) + len(_KILL_END)
    return head + _KILL_NEW + tail[:end] + ")" + tail[end:]


def _stop_sim(src):
    return src.replace("componentDidMount() { this.timer = setInterval(() => this.advance(), 1000); }",
                       "componentDidMount() { this.timer = setInterval(() => this.setState({ now: new Date() }), 1000); }", 1)


def _safe(fn, src, *a):
    # A patch that fails leaves that part of the page as designed.
    try:
        return fn(src, *a)
    except Exception:
        return src


def _sgn(v):
    return ("+" if v >= 0 else "−") + f"{abs(v):,.2f}"


def _patch_desk(src, state, positions):
    lim = state["limits"]
    eq = float(lim["equity"])
    bal = float(lim.get("balance") or eq)
    peak = float(lim.get("peak") or eq)
    day = eq - float(lim.get("day_equity") or eq)
    dd = max(0.0, peak - eq)
    live = state.get("live") or {}
    margin = float((live.get("account") or {}).get("margin") or 0)
    ml = f"{eq / margin * 100:,.0f}%" if margin else "—"
    try:
        tick = dt.datetime.fromisoformat(str(live.get("t"))[:19]).strftime("%a %H:%M")
    except ValueError:
        tick = "—"
    today = "Flat Today" if abs(day) < 0.005 else _sgn(day) + " Today"
    n = len(positions or [])
    src = re.sub(r"equity: money\([\d.]+\), change: '[^']*'",
                 lambda _: f"equity: money({eq:.2f}), change: '−{dd:,.2f} From Peak · {today}'", src, count=1)
    src = re.sub(r"stats: \[st\('Balance'.*?'#6E6E73'\)\]", lambda _: (
        f"stats: [st('Balance', money({bal:.2f})), st('Floating P/L', '{_sgn(eq - bal)}'), st('Day P/L', '{_sgn(day)}'), "
        f"st('Positions', '{n}'), st('Margin Level', '{ml}'), st('Last Tick', '{tick}', '#6E6E73')]"), src, count=1)
    src = re.sub(r"const deskDD = [\d.]+ / [\d.]+ \* 100;", lambda _: f"const deskDD = {dd:.2f} / {peak:.2f} * 100;", src, count=1)
    loss = max(0.0, -day) / (eq - day) * 100 if eq - day else 0.0
    src = re.sub(r"gv\('Daily Loss', '[^']*', [\d.]+,",
                 lambda _: f"gv('Daily Loss', '{loss:.2f}% Of 4%', {min(100.0, loss / 4 * 100):.1f},", src, count=1)
    floor = float(((lim.get("floors") or {}).get("day")) or 0)
    src = re.sub(r"label: 'Desk Equity', value: '[^']*', sub: '[^']*'", lambda _: (
        f"label: 'Desk Equity', value: '{eq:,.2f}', sub: 'To Day Floor {eq - floor:,.2f}'"), src, count=1)
    return re.sub(r"label: 'Open Positions', value: '[^']*', sub: '[^']*'",
                  lambda _: f"label: 'Open Positions', value: '{n}', sub: 'Desk Account'", src, count=1)


# T16 (the FTMO demo running AurumFunded) is never touched: only its log files are read, with the privacy rules of
# tools/demo_check.py (private lines dropped, long digit runs masked).
T16_DATA = pathlib.Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "66FB7F5B174F9C3B2A690C49FF012FEB"
_T16_PRIVATE = re.compile(r"login|authoriz|account", re.I)
_T16_DIGITS = re.compile(r"(?<![.\d])\d{6,}(?![.\d])")
_T16_DAY = re.compile(r"firm day (\S+), day start (-?[\d.]+)")
_T16_CLOSED = re.compile(r"closed \S+ magic \S+ [\d.]+ at \S+, P/L (-?[\d.]+)")
_T16_OPEN = re.compile(r"\b(?:bought|sold) \d[\d.]*(?:\s|$)")
_T16_FINAL = re.compile(r"final stop at (-?[\d.]+)")
# The open line each AurumFunded leg prints (mql5/Include/Aurum/Legs.mqh) and its tile on the Main page.
_T16_LEGS = (("day after a US holiday", "After Holiday"), ("bell leg ", "Bell"), ("after the fix ", "After Fix"),
             ("midday leg ", "Midday"), ("Tokyo leg ", "Tokyo"), ("dip unit", "Dip"),
             ("for the Tokyo morning", "Morning"), ("before the fix ", "Fix"), ("broke its range", "Breakout"),
             (", bands ", "Noise Area"), ("variance-premium gap", "VRP"), ("Dual Thrust ", "Dual Thrust"))


def _t16_log(data_dir=None, days=14):
    """The AurumFunded account as its EA log tells it: the balance curve (each firm-day start, then each close),
    the firm day, its day start and closed P/L, open positions and the time of the last line. None without a log."""
    logs = sorted((pathlib.Path(data_dir or T16_DATA) / "MQL5" / "Logs").glob("2*.log"))[-days:]
    curve, firm, start, day, opens, closes, last, final, traded = [], None, None, 0.0, 0, 0, None, None, set()
    legs = {}
    for p in logs:
        raw = p.read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
        for line in text.splitlines():
            if "AurumFunded" not in line or _T16_PRIVATE.search(line):
                continue
            line = _T16_DIGITS.sub("<num>", line)
            m = re.search(r"\t(\d\d:\d\d):\d\d", line)
            if m:
                last = (p.stem, m.group(1))
            m = _T16_DAY.search(line)
            if m:
                firm, start, day, legs = m.group(1), float(m.group(2)), 0.0, {}
                curve.append(start)
                m = _T16_FINAL.search(line)
                final = float(m.group(1)) if m else final
                continue
            if start is None:
                continue
            m = _T16_CLOSED.search(line)
            if m:
                closes += 1
                day += float(m.group(1))
                curve.append(curve[-1] + float(m.group(1)))
            elif _T16_OPEN.search(line):
                opens += 1
                traded.add(firm)
                leg = next((n for k, n in _T16_LEGS if k in line), None)
                if leg:
                    legs[leg] = legs.get(leg, 0) + 1
    if start is None:
        return None
    try:
        when = dt.datetime.strptime(last[0], "%Y%m%d").strftime("%a ") + last[1] if last else "—"
    except ValueError:
        when = "—"
    return {"curve": curve, "balance": curve[-1], "firm": firm, "start": start, "day": day,
            "positions": max(0, opens - closes), "last": when, "final": final, "traded": len(traded),
            "legs": legs}


def _demo_week(today=None, data_dir=None):
    """The last Mon-Fri week with AurumFunded log lines on T16, read day by day through tools/demo_check.py (read-only,
    same privacy rules): its dates, every close's P/L in order, the orders, the alert days and the currency."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("demo_check", ROOT / "tools" / "demo_check.py")
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    if data_dir:
        dc.DATA = pathlib.Path(data_dir)
    today = today or dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    for back in range(3):
        mon = monday - dt.timedelta(weeks=back)
        days = [dc.check(mon + dt.timedelta(days=k)) for k in range(5) if mon + dt.timedelta(days=k) <= today]
        if any(d["experts_lines"] for d in days):
            closes = [c for d in days for c in d["closes"]]
            return {"start": mon, "end": mon + dt.timedelta(days=4), "pl": [c["pl"] for c in closes],
                    "orders": sum(sum(d["orders_by_leg"].values()) for d in days),
                    "alerts": sum(1 for d in days if d["alert"]),
                    "currency": closes[0]["currency"] if closes else "EUR"}
    return None


def _patch_main_fidelity(src, week):
    """The Demo Versus Tester card: the demo side (curve by close, orders, P/L, alert days) from the T16 logs. No tester
    run is paired with the demo week yet (owner-only step), so the tester line is hidden and its stats show a dash."""
    if not week:
        return src
    pl = week["pl"] or [0.0]
    tot = sum(week["pl"])
    src = src.replace("Week 10-26 To 10-30 ·",
                      f"Week {week['start']:%m-%d} To {week['end']:%m-%d} ·", 1)
    src = src.replace(">Order Path And Tester Line Sample<", ">No Tester Run Paired Yet<", 1)
    src = re.sub(r"const demoInc = \[[^\]]*\];", lambda _: "const demoInc = [" + ", ".join(f"{x:.2f}" for x in pl) + "];",
                 src, count=1)
    src = src.replace("const testInc = [", "const testIncSample = [", 1)
    src = src.replace("const dC = cum(demoInc), tC = cum(testInc);", "const dC = cum(demoInc), tC = [0];", 1)
    src = src.replace("(186 - (v - lo) / (hi - lo) * 172)", "(186 - (v - lo) / ((hi - lo) || 1) * 172)", 1)
    src = src.replace("tester: fpts(tC),", "tester: '',", 1)
    green, red, ink = "#248A3D", "#D70015", "#1D1D1F"
    stats = {"Demo Orders": (str(week["orders"]), ink),
             "Demo P/L": (f"{tot:+.2f} {week['currency']}", green if tot >= 0 else red),
             "Tester P/L": ("—", "#6E6E73"), "Demo Of Tester": ("—", "#6E6E73"),
             "Alerts": (str(week["alerts"]), green if not week["alerts"] else red)}
    for label, (value, color) in stats.items():
        src = re.sub(r"\{ label: '" + re.escape(label) + r"', value: [^}]*?, style: fv\('[^']*'\) \}",
                     lambda _: f"{{ label: '{label}', value: '{_js(value)}', style: fv('{color}') }}", src, count=1)
    return src


_DEPLOY_HDR = re.compile(r"^## (\d{4}-\d\d-\d\d)(?: \([^)\n]*\))?(?:, (\d\d:\d\d))?[^\n]*?AurumFunded (\d+\.\d+) (?:deployed )?on T16", re.M)


def _funded_deploy(text=None):
    """The last AurumFunded deploy to T16 in docs/demo_log.md: {'ver', 'date', 'time'} from the latest-dated
    '## <date> ..., HH:MM...: AurumFunded X [deployed ]on T16' header (headers are not always in date order;
    'built, not deployed' headers do not match). None when the log or a header is missing."""
    try:
        text = text if text is not None else (DOCS / "demo_log.md").read_text(encoding="utf-8")
    except OSError:
        return None
    found = [(m.group(1), m.group(2) or "", i, m.group(3)) for i, m in enumerate(_DEPLOY_HDR.finditer(text))]
    if not found:
        return None
    date, time, _, ver = max(found)
    return {"ver": ver, "date": date, "time": time}


def _deployed_funded(text=None):
    """The AurumFunded version on T16 (see _funded_deploy)."""
    d = _funded_deploy(text)
    return d["ver"] if d else None


def _patch_versions(src, funded, hydra, funded_src=None, deploy=None):
    """Every page: the design's AurumFunded 1.19 / 1.20 and AurumHydra 1.42 strings become the version T16 runs
    (demo_log) and the Hydra source version; the '1.20 waits for the owner' items say whether T16 matches the source."""
    rep = []
    if funded:
        same = not funded_src or funded_src == funded
        status = "T16 Matches The Source" if same else f"Source {funded_src} Not On T16"
        when = f"{deploy['date'][5:]} {deploy['time']}".strip() if deploy else ""
        rep += [("AurumFunded v1.19", f"AurumFunded v{funded}"), ("AurumFunded 1.19", f"AurumFunded {funded}"),
                ("ver: '1.19'", f"ver: '{funded}'"), ("1.20 Waits On Owner", status), ("1.20 Committed, Not Deployed", status),
                ("1.20 Waits For The Owner", status), ("1.19 Live Vs 1.20 Committed", f"{funded} On T16 · Source {funded_src or funded}"),
                ("First 1.19 Draft", f"AurumFunded {funded}")]
        if same:
            rep += [("{ name: 'AurumFunded 1.20 Deploy', why: 'Built And Reviewed. Waits For The Owner’s Yes.', where: 'mql5/Experts/AurumFunded', state: 'Waiting' }",
                     f"{{ name: 'AurumFunded {funded} Deploy', why: 'Deployed On T16{(' ' + when) if when else ''}. The Next Deploy Waits For The Owner’s Yes.', where: 'mql5/Experts/AurumFunded', state: 'Done' }}"),
                    ("{ at: 'Sat', what: 'AurumFunded 1.20 Ready To Deploy', who: 'Reviewer · Waits For The Owner', state: 'Waiting' }",
                     f"{{ at: '{when[:5] or '—'}', what: 'AurumFunded {funded} Deployed On T16', who: 'Owner’s Yes · demo_log', state: 'Applied' }}")]
    if hydra:
        rep += [("AurumHydra 1.42", f"AurumHydra {hydra}"), ("Hydra 1.42.", f"Hydra {hydra}."), ("Matches 1.42 Run", f"Source {hydra}"),
                ("ver: '1.42'", f"ver: '{hydra}'")]
    rep += [("Deploying 1.20 To T16 And The Fidelity Pairing Are The Owner’s Call.", "EA Deploys To T16 Are The Owner’s Call."),
            ("The AurumFunded 1.20 Deploy And The Fidelity Pairing Stay With The Owner.", "EA Deploys To T16 Stay With The Owner."),
            (" · Connected · Ping 38 ms", ""), (" · Connected · Ping 44 ms", " · Tester Only, No Demo Terminal")]
    for old, new in rep:
        src = src.replace(old, new)
    return src


def _market_pill(now):
    """FX is open Sun 17:00 to Fri 17:00 New York; the pill gives the next open or close in UTC."""
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    n = now.astimezone(ny)
    wd = n.weekday()
    closed = wd == 5 or (wd == 4 and n.hour >= 17) or (wd == 6 and n.hour < 17)
    target = 6 if closed else 4
    at = dt.datetime.combine(n.date() + dt.timedelta(days=(target - wd) % 7), dt.time(17), tzinfo=ny)
    if at <= n:
        at += dt.timedelta(days=7)
    u = at.astimezone(dt.timezone.utc)
    return f"Markets Closed · FX Opens {u:%a %H:%M} UTC" if closed else f"FX Open · Closes {u:%a %H:%M} UTC"


def _heartbeat_pill(hb, now, stale=dt.timedelta(minutes=10)):
    """(text, color) for the MT5 heartbeat pill: red when the beat is not ok, missing or older than `stale`."""
    t = _ts((hb or {}).get("t"))
    if t is None:
        return "MT5 Heartbeat Missing", "#D70015"
    hm = t.astimezone(dt.timezone.utc).strftime("%H:%M")
    if not hb.get("ok"):
        return f"MT5 Heartbeat Not OK · {hm} UTC", "#D70015"
    if now - t > stale:
        return f"MT5 Heartbeat Stale · {hm} UTC", "#D70015"
    return f"MT5 Heartbeat OK · {hm} UTC", "#248A3D"


def _patch_phase(src, state):
    """Every page: the design's 'Phase 3, Day 4' becomes the desk phase and day from /api/state."""
    st = (state or {}).get("status") or {}
    p, d = st.get("phase"), st.get("phase_day")
    if p is None or d is None:
        return src
    return (src.replace("Phase 3, Day 4", f"Phase {p}, Day {d}").replace("Desk Phase 3 · Day 4", f"Desk Phase {p} · Day {d}")
            .replace("Phase 3 · Day 4 · T16", f"Phase {p} · Day {d} · T16"))


def _patch_main_status(src, state, now=None):
    """Main: the market and heartbeat pills, the Monitor card's beat, and the design text with no source behind it
    (Chance Of 5x, the funded legs' 'None Since 18:11', the Design v6 footer, the heatmap's 'Sample Values')."""
    now = now or dt.datetime.now(dt.timezone.utc)
    hb = ((state or {}).get("status") or {}).get("heartbeat") or {}
    src = src.replace("Markets Closed · FX Opens Sun 23:00", _market_pill(now), 1)
    text, color = _heartbeat_pill(hb, now)
    src = src.replace('color: #248A3D">MT5 Heartbeat OK · 17:26 UTC', f'color: {color}">{text}', 1)
    src = src.replace("st('Chance Of 5x', '10% · 3x 43%', accent)", "st('Chance Of 5x', '—', '#6E6E73')", 1)
    src = src.replace("'None Since 18:11'", "'—'")
    src = src.replace("<span>Aurum Command Center · Design v6</span>", "<span>Aurum Command Center</span>", 1)
    src = src.replace("Eight Legs, Sample Values", "Eight Legs, From docs/book.json", 1)
    t = _ts(hb.get("t"))
    if t is not None:
        age = max(0, int((now - t).total_seconds() // 60))
        fresh = hb.get("ok") and age <= 10
        beat = t.astimezone(dt.timezone.utc).strftime("%H:%M")
        issues = len(((state or {}).get("monitor") or {}).get("issues") or [])
        src = src.replace(
            "[['Last Beat', pad(d.getHours()) + ':' + pad(Math.floor(d.getMinutes() / 5) * 5)], ['Alerts Open', String(alertOpenN)], ['Caught', 'Sample'], ['Missed', 'Sample']],\n"
            "        'Beats Today', beats + ' Of 288', beats / 288 * 100)",
            f"[['Last Beat', '{beat} UTC'], ['Alerts Open', String(alertOpenN)], ['Code Issues', '{issues}'], ['Missed', '—']],\n"
            f"        'Heartbeat', '{'OK' if fresh else 'Stale'} · {age} Min Ago', {100 if fresh else 0})", 1)
    return src


def _patch_scores(src):
    """Main: the design's invented 0-99 agent scores become runs this week (ROLES score, set by _patch_roles); the
    rank, bars and leaderboard follow runs, and the IQ labels drop the made-up 'Level N'."""
    rep = [("score: Math.min(99, r.score + doneCount)", "score: r.score"),
           ("const scoreColor = (n) => n >= 85 ? '#248A3D' : n >= 75 ? '#0066CC' : '#B25000';",
            "const scoreColor = (n) => n > 0 ? '#1D1D1F' : '#AEAEB2';"),
           ("const ranked = ROLES.map((r) => r.id)", "const RUNMAX = Math.max(1, ...ROLES.map((r) => r.score)); const ranked = ROLES.map((r) => r.id)"),
           ("scoreBar: bar(score, scoreColor(score))", "scoreBar: bar(score / RUNMAX * 100, '#0071E3')"),
           ("bar: bar(score, scoreColor(score)), score: String(score)", "bar: bar(score / RUNMAX * 100, '#0071E3'), score: String(score)"),
           ("Score · Rank {{a.rank}}", "Runs This Week · Rank {{a.rank}}"),
           ('font-size: 12px">Scores</a>', 'font-size: 12px">Activity</a>'),
           ('letter-spacing: -0.012em">Scores</h3>', 'letter-spacing: -0.012em">Activity</h3>'),
           ("Performance, Intelligence And Score, Best First.", "Runs This Week From usage.jsonl, Most First."),
           (">Measured Scores<", ">What Is Measured<"),
           ("Finder: Share Of Its Ideas That Pass The Gates. Builder: Gate Passes And Clean Compiles. Judge: Agreement With "
            "The Reviewer. Monitor: Alerts Caught. Pods: R And Profit Factor Against Their Benchmark. Intelligence Follows "
            "The Model. Values Stay Sample Until The Wiring Reads The Logs.",
            "Runs, Tokens And The Last Run Per Agent Since The Week Start, From usage.jsonl. No Quality Score Is Measured "
            "Yet, So None Is Shown. The Intelligence Bar Follows The Model Tier.")]
    for old, new in rep:
        src = src.replace(old, new)
    return re.sub(r"\[(\d), 'Level \d · ([^']*)'\]", r"[\1, '\2']", src)


def _patch_main_funded(src, t16, version=None):
    """The Main funded card and the Funded Equity KPI from the T16 EA log. Floating P/L and margin are not in the log."""
    if not t16:
        return src
    bal, n = t16["balance"], t16["positions"]
    curve = t16["curve"] if len(t16["curve"]) > 1 else t16["curve"] * 2
    src = re.sub(r"this\.fundedCurve = [^;]*;", lambda _: f"this.fundedCurve = {json.dumps([round(v, 2) for v in curve])};",
                 src, count=1)
    note = f"{n} Open, Equity Not In The Log" if n else "Flat"
    change = _js(f"{_sgn(t16['day'])} On Firm Day {t16['firm']} · {note}")
    src = re.sub(r"equity: '\[T16 Equity\]', change: '[^']*'",
                 lambda _: f"equity: money({bal:.2f}), change: '{change}'", src, count=1)
    src = re.sub(r"stats: \[st\('Balance', '\[T16 Balance\]'\).*?'#6E6E73'\)\]", lambda _: (
        f"stats: [st('Balance', money({bal:.2f})), st('Floating P/L', '{'—' if n else '0.00'}'), "
        f"st('Day P/L', '{_sgn(t16['day'])}'), st('Positions', '{n}'), st('Day Start', '{t16['start']:,.2f}'), "
        f"st('Last Log', '{_js(t16['last'])}', '#6E6E73')]"), src, count=1)
    sub = f"'AurumFunded v{_js(version)}'" if version else "'AurumFunded'"
    return re.sub(r"label: 'Funded Equity', value: '\[T16\]', sub: s\.held \? 'Held By Owner' : '[^']*'",
                  lambda _: f"label: 'Funded Equity', value: '{bal:,.2f}', sub: s.held ? 'Held By Owner' : {sub}",
                  src, count=1)


def _t16_preset(ini=None, experts=None):
    """The AurumFunded inputs on T16: the .set named by the ExpertParameters line of t16_attach.ini (only that
    line is read). {} when either file is missing."""
    try:
        ini = ini or ROOT / "tools" / "autopilot" / "t16_attach.ini"
        m = re.search(r"^ExpertParameters=(.+?)\s*$", pathlib.Path(ini).read_text(encoding="utf-8", errors="replace"),
                      re.M)
        raw = (pathlib.Path(experts or ROOT / "mql5" / "Experts" / "AurumFunded") / pathlib.Path(m.group(1)).name).read_bytes()
    except (OSError, AttributeError):
        return {}
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    out = {}
    for k, v in re.findall(r"^Inp(Prop\w+)=([^|\r\n]*)", text, re.M):
        try:
            out[k] = float(v)
        except ValueError:
            out[k] = v.strip()
    return out


_T16_LOADED = re.compile(r"\t(\d\d:\d\d:\d\d)\.\d+\tExperts\texpert AurumFunded \((\S+),(\w+)\) (loaded successfully|removed)")


def _t16_loaded(data_dir=None, ini=None, days=14):
    """The preset T16 runs and its last load or removal: the .set from the ExpertParameters line of t16_attach.ini
    (only that line is read) and the last AurumFunded line of the terminal journal. {} when neither is found."""
    out = {}
    try:
        m = re.search(r"^ExpertParameters=(.+?)\s*$", pathlib.Path(ini or ROOT / "tools" / "autopilot" / "t16_attach.ini")
                      .read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            out["set"] = pathlib.Path(m.group(1)).name
    except OSError:
        pass
    for p in sorted((pathlib.Path(data_dir or T16_DATA) / "logs").glob("2*.log"))[-days:]:
        raw = p.read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
        for line in text.splitlines():
            m = _T16_LOADED.search(line)
            if m and not _T16_PRIVATE.search(line):
                out.update(day=p.stem, time=m.group(1), symbol=m.group(2), tf=m.group(3),
                           loaded=m.group(4) == "loaded successfully")
    return out


def _patch_main_preset(src, info, today=None):
    """The Main preset line: the .set T16 runs, its chart and when it was last loaded (or removed)."""
    if not info:
        return src
    tail = ""
    if info.get("time"):
        day = dt.datetime.strptime(info["day"], "%Y%m%d").date()
        when = info["time"] if day == (today or dt.date.today()) else f"{day.day} {day:%b} {info['time']}"
        tail = f" · {info['symbol']} {info['tf']} · {'Loaded' if info['loaded'] else 'Removed'} {when}"
    name = html.escape(info.get("set") or "—")
    return re.sub(r"(Preset <span[^>]*>)[^<]*(</span>)[^<]*(</div>)",
                  lambda m: m.group(1) + name + m.group(2) + html.escape(tail) + m.group(3), src, count=1)


def _patch_main_rules(src, t16, preset, daily=5.0, total=10.0):
    """The Main funded rules (FTMO 2-Step: daily loss 5% and max loss 10% of the initial balance) from the T16 log.
    The initial balance comes from the EA's static final stop and its max-stop input."""
    if not t16 or not t16.get("final") or not preset.get("PropMaxStopPct"):
        return src
    init = t16["final"] / (1 - preset["PropMaxStopPct"] / 100)
    if init <= 0:
        return src
    bal, target, days = t16["balance"], preset.get("PropTargetPct", 10.0), int(preset.get("PropMinDays", 4))
    dl = max(0.0, -t16["day"]) / init * 100
    ml = max(0.0, init - bal) / init * 100
    pt = max(0.0, bal - init) / init * 100

    def b(used, cap):
        return f"{min(100.0, used / cap * 100):.1f}"
    rules = (f"const rules = [\n"
             f"  {{ label: 'Daily Loss Limit', value: '{dl:.2f}% Of {daily:g}%', bar: bar({b(dl, daily)}, '#FF9500') }},\n"
             f"  {{ label: 'Max Loss', value: '{ml:.2f}% Of {total:g}%', bar: bar({b(ml, total)}, '#D70015') }},\n"
             f"  {{ label: 'Profit Target', value: '{pt:.2f}% Of {target:g}% · Days {t16['traded']} Of {days}', "
             f"bar: bar({b(pt, target)}, '#34C759') }}\n];")
    return re.sub(r"const rules = \[.*?\n\s*\];", lambda _: rules, src, count=1, flags=re.S)


def _patch_main_legs(src, t16, today=None):
    """The Main leg chips: opens per leg on the latest T16 firm day. When that day is not today the label names it."""
    if not t16 or not t16.get("firm"):
        return src
    counts = json.dumps(t16.get("legs") or {})
    out = src.replace(".map((n) => ({ name: n, orders: '0' }))",
                      f".map((n) => ({{ name: n, orders: String(({counts})[n] || 0) }}))", 1)
    today = today or dt.date.today()
    try:
        day = dt.datetime.strptime(t16["firm"], "%Y.%m.%d").date()
    except ValueError:
        return out
    if day != today:
        out = out.replace("Legs · Orders Today", f"Legs · Orders {day.day} {day:%b}", 1)
    return out


def _patch_gate(src, state):
    checks = (state.get("live_gate") or {}).get("checks") or {}

    def f(x):
        m = re.search(r"-?\d+(?:\.\d+)?", str(x))
        return float(m.group()) if m else None

    for label, key in (("Weeks", "weeks"), ("Trades", "trades"), ("Profit Factor", "profit_factor"),
                       ("Drawdown", "max_drawdown_pct"), ("Faults", "code_faults"), ("Against Benchmark", "ai_beats_shadow")):
        c = checks.get(key)
        if not isinstance(c, dict):
            continue
        have, need = f(c.get("have")), f(c.get("need"))
        if have is None:
            continue
        bar, txt = ("#34C759", "#248A3D") if c.get("ok") else ("#D70015", "#B3261E")
        if key == "ai_beats_shadow":
            value, pct = f"{have:+.2f} R A Trade, Benchmark {need if need is not None else '—'}", 0
        elif key == "code_faults":
            value, pct = f"{have:.0f}", 0
        else:
            unit = "%" if key == "max_drawdown_pct" else ""
            nd = {"trades": 0, "weeks": 1}.get(key, 2)
            value = f"{have:.{nd}f}{unit} Of {need:.{nd}f}{unit}" if need else f"{have:.{nd}f}{unit}"
            pct = min(100.0, max(0.0, have / need * 100)) if need else 0
        src = re.sub(rf"gv\('{label}',[^\n]*\)", lambda _: f"gv('{label}', '{_js(value)}', {pct:.1f}, '{bar}', '{txt}')",
                     src, count=1)
    return src


def _patch_pods(src, state):
    for p in state.get("pods") or []:
        sc = p.get("score") or {}
        pf = sc.get("pf")
        pf = f"{float(pf):.2f}" if isinstance(pf, (int, float)) else "—"
        row = (f"{float(p.get('share') or 0) * 100:.0f}, {int(sc.get('trades') or 0)}, "
               f"{float(sc.get('total_R') or 0):.2f}, '{pf}'")
        src = re.sub(rf"(\['{re.escape(str(p.get('name')))}',\s*'[^']*',\s*)[-\d.]+,\s*[-\d.]+,\s*[-\d.]+,\s*'[^']*'",
                     lambda m: m.group(1) + row, src, count=1)
    return src


def _patch_queue(src, rows):
    chips = {"new": "chip('#E8F2FD', '#0066CC')", "rejected": "chip('#FDECEC', '#B3261E')"}
    out = []
    for r in list(rows or [])[-8:][::-1]:
        st = str(r.get("status") or "new")
        out.append(f"{{ id: '{_js(str(r.get('id') or '?'))[:48]}', status: '{_js(st.title())}', "
                   f"chip: {chips.get(st.lower(), chr(99) + 'hip(' + chr(39) + '#E8F5EC' + chr(39) + ', ' + chr(39) + '#1E7B34' + chr(39) + ')')} }}")
    if not out:
        return src
    every = [r for r in _jsonl(DOCS / "ideas" / "queue.jsonl") if isinstance(r, dict)] or list(rows)
    n = collections.Counter(str(r.get("status") or "new").lower() for r in every)
    sub = " · ".join([f"{sum(n.values())} Ideas"] + [f"{n[k]} {k.title()}" for k in
                     ("new", "rejected", "done", "funded") if n[k]])
    src = src.replace("109 Ideas · 95 Rejected · 13 Done · 1 Funded<", sub + "<", 1)
    return re.sub(r"const queue = \[.*?\n    \];", lambda _: "const queue = [" + ", ".join(out) + "];", src, count=1, flags=re.S)


def _alert_id(pre, text):
    import hashlib
    return pre + "-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _when(day, hm=""):
    """'2026-11-01', '00:41' -> 'Sun 11-01 00:41'."""
    try:
        d = dt.date.fromisoformat(day)
    except ValueError:
        return day
    return f"{d.strftime('%a')} {d.strftime('%m-%d')} {hm}".strip()


def _desk_alert_rows(root, limit=8):
    """Every section of desk/inbox/ALERT.md (newest first): ALERT red, WARN amber; a repeated text keeps its newest date."""
    try:
        txt = (pathlib.Path(root) / "desk" / "inbox" / "ALERT.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows, seen, when = [], set(), ""
    for line in txt.splitlines():
        m = re.match(r"# Desk alert (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC", line)
        if m:
            when = _when(m.group(1), m.group(2))
            continue
        m = re.match(r"- \*\*(ALERT|WARN|HALT)\*\*\s*(.+)", line)
        if m and when:
            text = m.group(2).replace("**", "").strip()
            if text in seen:
                continue
            seen.add(text)
            rows.append([_alert_id("desk", text), "amber" if m.group(1) == "WARN" else "red", "Desk",
                         _js(_cut(text, 90)), when])
    return rows[:limit]


def _doctor_rows(root, limit=8):
    """The doctor's 'Open, for Opus' items from docs/autopilot/gaps_report.md, dated by the report header."""
    try:
        txt = (pathlib.Path(root) / "docs" / "autopilot" / "gaps_report.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = re.search(r"^# Gaps report - (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", txt, re.M)
    when = _when(m.group(1), m.group(2)) if m else "Doctor"
    sec = re.search(r"^## Open, for Opus\s*\n(.*?)(?=^## |\Z)", txt, re.M | re.S)
    rows = []
    for t in re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", sec.group(1) if sec else "", re.M):
        t = t.strip().rstrip(".")
        rows.append([_alert_id("doc", t), "amber", "Doctor", _js(_cut(t, 90)), when])
    return rows[:limit]


def _patch_alerts(src, state, root=None):
    """Alerts card: the desk's needs-you list now, then ALERT.md history, then the doctor's open items.
    Ids hash the text, so an ack holds across reloads."""
    rows = []
    for n in (state or {}).get("needs_you") or []:
        what = str(n.get("what") or "")
        if "inbox/ALERT.md" in what:  # the history rows below carry these, with their real date
            continue
        rows.append([_alert_id("live", what), "amber" if str(n.get("level")).upper() == "WARN" else "red", "Desk",
                     _js(_cut(what, 90)), "Now"])
    if root is not None:
        rows += _desk_alert_rows(root) + _doctor_rows(root)
    js = json.dumps(rows, ensure_ascii=False)
    return re.sub(r"const alertDefs = \[.*?\n    \]\.concat", lambda _: f"const alertDefs = {js}.concat", src, count=1, flags=re.S)


def _patch_sources(src):
    return src.replace("state: i === 1 ? 'Partly Live' : 'To Wire', pill: i === 1 ? chip('#E8F2FD', '#0066CC') : chip('#FFF4E5', '#B25000')",
                       "state: [0, 1, 3, 5].includes(i) ? 'Live' : 'To Wire', pill: [0, 1, 3, 5].includes(i) ? "
                       "chip('#E8F5EC', '#1E7B34') : chip('#FFF4E5', '#B25000')", 1)


_KIND_XP = {"ask": 2, "reply": 6, "share": 5, "endorse": 8, "cite": 15, "note": 2}


def _hhmm(t):
    try:
        return dt.datetime.fromisoformat(str(t)[:19]).strftime("%H:%M")
    except ValueError:
        return "—"


def _usd(v):
    v = float(v or 0)
    return ("−$" if v < 0 else "+$") + f"{abs(v):,.2f}"


def _sk_line(sc):
    """One line from a pod's scorekeeper entry: P&L, hit rate and trades over the 8-week window."""
    sc = sc if isinstance(sc, dict) else {}
    n = int(sc.get("trades") or 0)
    if not n:
        return "No Closed Trades In 8 Weeks"
    hit = sc.get("hit")
    return (f"{_usd(sc.get('pnl'))} · " + (f"{round(float(hit) * 100)}% Hit · " if hit is not None else "")
            + f"{n} Trade{'s' if n != 1 else ''}")


def _sk_js(sc):
    """The scorekeeper entry as a JS object literal for the Pods page."""
    sc = sc if isinstance(sc, dict) else {}

    def num(k):
        v = sc.get(k)
        return "null" if not isinstance(v, (int, float)) else repr(float(v))
    return (f"sk: {{ trades: {int(sc.get('trades') or 0)}, pnl: {num('pnl')}, hit: {num('hit')}, R: {num('total_R')}, "
            f"rpt: {num('R_per_trade')}, pf: {num('pf')}, dd: {num('max_dd_R')}, score: {num('score')} }}, ")


_PODS_SK_JS = [
    ("const info = PODS.map((p) => { const c = s.counts[p.id], xp = xpOf(c, p.winR), li = levelOf(xp); return { p, c, xp, li, iq: iqOf(xp, p.winR, c.trades) }; });",
     "const skUsd = (v) => (v < 0 ? '−$' : '+$') + Math.abs(v || 0).toFixed(2), skSgn = (v, d) => (v >= 0 ? '+' : '') + Number(v || 0).toFixed(d), "
     "skFx = (v, d) => v == null ? '—' : Number(v).toFixed(d);\n"
     "    const info = PODS.map((p) => { const c = s.counts[p.id], k = p.sk || {}, n = k.trades || 0; "
     "return { p, c, k, n, xp: n ? (k.score || 0) : -9, li: 0, iq: k.hit == null ? '—' : Math.round(k.hit * 100) + '%' }; });"),
    ("const lo = LEVELS[li][1], hi = li < LEVELS.length - 1 ? LEVELS[li + 1][1] : lo, pct = hi > lo ? Math.round((xp - lo) / (hi - lo) * 100) : 100;",
     "const k = p.sk || {}, n = k.trades || 0, pct = k.hit == null ? 0 : Math.round(k.hit * 100);"),
    ("tags.push({ text: 'XP Gained',", "tags.push({ text: 'Updated',"),
    ("level: LEVELS[li][0], levelNo: String(li + 1), iq: String(iq), xp: xp.toLocaleString('en-US'), pct: String(pct),\n"
     "        toNext: hi > lo ? (hi - xp).toLocaleString('en-US') + ' To ' + LEVELS[li + 1][0] : 'Top Level', xpAria: p.name + ' ' + pct + '% To Next Level',",
     "level: n ? skUsd(k.pnl) + ' P&L · ' + n + (n === 1 ? ' Trade' : ' Trades') : 'No Closed Trades · 8 Weeks', levelNo: '', iq: iq, "
     "xp: n ? skSgn(k.R, 2) + ' R · PF ' + skFx(k.pf, 2) : 'Hit Rate Starts At Trade 1', pct: String(pct),\n"
     "        toNext: n ? 'Score ' + skSgn(k.score, 3) : '', xpAria: p.name + ' Hit Rate ' + iq,"),
    ("const maxXp = Math.max(...Object.keys(XP_W).map((k) => me.c[k] * XP_W[k]), 1);",
     "const kk = me.k, nn = me.n;"),
    ("const rows = Object.keys(XP_W).map((k) => ({ label: XP_LABEL[k], count: String(me.c[k]), w: String(XP_W[k]), xp: String(me.c[k] * XP_W[k]),\n"
     "      bar: 'height: 6px; border-radius: 3px; background: #0071E3; width: ' + (me.c[k] * XP_W[k] / maxXp * 100).toFixed(1) + '%' }));",
     "const rows = [['Trades Closed', String(nn)], ['Hit Rate', me.iq], ['P&L', nn ? skUsd(kk.pnl) : '—'], ['Total R', nn ? skSgn(kk.R, 2) : '—'], "
     "['R Per Trade', nn ? skSgn(kk.rpt, 3) : '—'], ['Profit Factor', nn ? skFx(kk.pf, 2) : '—'], ['Max Drawdown', nn ? skFx(kk.dd, 2) + ' R' : '—']]"
     ".map(([label, xp]) => ({ label, count: '', w: '', xp, bar: '' }));"),
    ("name: p.name + ' · ' + LEVELS[me.li][0] + ' · IQ ' + me.iq,",
     "name: p.name + ' · ' + (me.n ? me.iq + ' Hit Rate' : 'No Closed Trades'),"),
    ("xp: me.xp.toLocaleString('en-US'), ladder,",
     "xp: me.n ? skSgn(kk.score, 3) + (me.n < 20 ? ' · ' + me.n + ' Of 20 Trades' : '') : '—', ladder,"),
    ("text: m.text, xp: m.xp + ' XP' }", "text: m.text, xp: '' }"),
    ("const totalXp = info.reduce((a, x) => a + x.xp, 0), top = info.slice().sort((a, b) => b.xp - a.xp)[0];",
     "const top = info.filter((x) => x.n).sort((a, b) => (b.k.score || 0) - (a.k.score || 0) || (b.k.pnl || 0) - (a.k.pnl || 0))[0];"),
    ("{ label: 'Top Pod', value: top.p.name, sub: LEVELS[top.li][0] + ' · IQ ' + top.iq, style: big },",
     "{ label: 'Top Pod', value: top ? top.p.name : 'None Yet', sub: top ? 'Score ' + skSgn(top.k.score, 3) + ' · ' + top.iq + ' Hit' : 'No Closed Trades In 8 Weeks', style: big },"),
]

_PODS_SK_HTML = [
    ("Six Trading Pods That Get Smarter As They Work. Every Run, Shared Note, Answer And Trade Adds Experience.",
     "Six Trading Pods, Each Judged By Its Own Closed Trades: P&amp;L, Hit Rate And R Over The Last 8 Weeks."),
    ("Pick A Pod To See How It Earned Its Level.", "Pick A Pod To See Its Scorekeeper Record."),
    ("{{p.level}} · Level {{p.levelNo}}</span>", "{{p.level}}</span>"),
    ('color: #6E6E73">IQ</span>', 'color: #6E6E73">Hit Rate</span>'),
    ("<span>{{p.xp}} XP</span>", "<span>{{p.xp}}</span>"),
    ("Where The XP Comes From</span>", "Scorekeeper · Last 8 Weeks</span>"),
    ("<span>Total</span><span>{{sel.xp}} XP</span>", "<span>Score</span><span>{{sel.xp}}</span>"),
    ("IQ = 60 Plus Experience And Win Rate, Clamped 60 To 160. The Brief Each Pod Gets Grows With Its Level: More Of Its Own Lessons, More Shared Knowledge, Longer Memory.",
     "From desk/scorekeeper.py (logs/desk/state/scores.json): Each Pod’s Closed Trades Over The Last 8 Weeks. Score = Its R Per Trade "
     "Minus The Rest Of The Desk’s, Shrunk By n/(n+20), So A Pod Is Fully Judged From Its 20th Trade."),
]


def _patch_pods_scores(src, state):
    """Pods page: the scorekeeper record (P&L, hit rate, R, score) in place of the made-up XP, level and IQ."""
    for p in state.get("pods") or []:
        pid = str(p.get("name") or "")
        if pid:
            src = re.sub(rf"\{{ id: '{re.escape(pid)}', ", lambda m, p=p: m.group(0) + _sk_js(p.get("score")), src, count=1)
    for a, b in _PODS_SK_JS + _PODS_SK_HTML:
        src = src.replace(a, b, 1)
    src = re.sub(r"\n[ \t]*rows\.push\(\{ label: 'Win Rate Bonus'[^\n]*", "", src, count=1)
    src = re.sub(r'<div style="display: grid; grid-template-columns: 150px 60px 70px minmax\(0, 1fr\) 70px;.*?\{\{r\.xp\}\}</span>\s*</div>\n',
                 lambda m: ('<div style="display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; '
                            'padding: 9px 0; border-top: 1px solid #E8E8ED"><span>{{r.label}}</span>'
                            '<span style="text-align: right; font-weight: 600">{{r.xp}}</span></div>\n'), src, count=1, flags=re.S)
    src = re.sub(r'\s*<div style="display: flex; flex-direction: column">\s*<span[^>]*>Level Ladder</span>.*?Legend 7,500 XP</span></div>\s*</div>',
                 "", src, count=1, flags=re.S)
    desk = (state.get("scores") or {}).get("desk") or {}
    n = int(desk.get("trades") or 0)
    hit = desk.get("hit")
    sub = (f"{n} Trade{'s' if n != 1 else ''}" + (f" · {round(float(hit) * 100)}% Hit" if hit is not None else "") + " · 8 Weeks") if n \
        else "No Closed Trades In 8 Weeks"
    col = "" if not n else "; color: " + ("#B3261E" if float(desk.get("pnl") or 0) < 0 else "#248A3D")
    return re.sub(r"\{ label: 'Desk XP', value: [^\n]*",
                  lambda _: f"{{ label: 'Desk P&L', value: '{_usd(desk.get('pnl')) if n else '—'}', sub: '{sub}', style: big + '{col}' }},",
                  src, count=1)


def _pod_panel(pid, p, cfg, know):
    """The selected pod's brief line, its wakes and what it knows (its own knowledge entries, most endorsed first)."""
    pc = (cfg.get("pods") or {}).get(pid) or {}
    mk = pc.get("owns") or []
    owns = ", ".join(mk[:5]) + (f" +{len(mk) - 5} More" if len(mk) > 5 else "") if mk else "No Markets Of Its Own"
    st = ("Paused" if p.get("paused") else "Active" if p.get("active")
          else f"Opens In Phase {p.get('opens_phase') or pc.get('phase') or '?'}")
    brief = f"Owns {owns} · {st} · {_sk_line(p.get('score'))}"
    wd = we = 0
    for ev in cfg.get("schedule") or []:
        if ev.get("kind") == "brief" and pid in (ev.get("pods") or [pid]):
            days = ev.get("days") or range(7)
            wd += any(d < 5 for d in days)
            we += any(d >= 5 for d in days)
    wakes = (f"{wd} Briefs Each Weekday" if wd else "No Weekday Briefs") + (f" · {we} On Weekends" if we else "") + " · Plus Triggers"
    mine = [k for k in know if k.get("pod") == pid]
    mine.sort(key=lambda k: (len(k.get("endorsed_by") or []), str(k.get("t") or "")), reverse=True)
    rows = []
    for k in mine[:3]:
        n = len(k.get("endorsed_by") or [])
        rows.append(f"['{_js(str(k.get('text') or '')[:90])}', '{f'{n} Endorsed' if n else 'New'}']")
    knows = "knows: [" + (", ".join(rows) or "['Nothing Shared Yet', '']") + "]"
    return _js(brief), _js(wakes), knows


def _patch_pods_page(src, state):
    pods = {str(p.get("name")): p for p in state.get("pods") or []}
    eq = float((state.get("limits") or {}).get("equity") or 0)
    try:
        cfg = json.loads((ROOT / "desk" / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        cfg = {}
    know = [k for k in state.get("knowledge") or [] if isinstance(k, dict)]
    for pid, p in pods.items():
        brief, wakes, knows = _pod_panel(pid, p, cfg, know)
        it, sc = p.get("intel") or {}, p.get("score") or {}
        w, tk, sh, tr = it.get("work") or {}, it.get("talk") or {}, it.get("share") or {}, it.get("trading") or {}
        trades = int(sc.get("trades") or tr.get("trades") or 0)
        c = (f"c: {{ runs: {int(w.get('runs') or 0)}, notes: {int(w.get('notes') or 0)}, asked: {int(tk.get('asked') or 0)}, "
             f"answered: {int(tk.get('answered') or 0)}, shared: {int(sh.get('shared') or 0)}, endorsed: {int(sh.get('endorsed') or 0)}, "
             f"cited: {int(sh.get('cited') or 0)}, trades: {trades} }}")
        wk = float(sc.get("pnl") or 0) / eq * 100 if eq else 0.0
        tail = (f"wk: {wk:.2f}, bench: 0, below: 0, closed: {trades}, followed: '{float(sc.get('total_R') or 0):+.2f} R'"
                + (", idle: true" if trades == 0 else ""))

        def one(m, c=c, tail=tail, alloc=round(float(p.get("share") or 0) * 100), hit=float(tr.get("hit") or sc.get("hit") or 0),
                brief=brief, wakes=wakes, knows=knows):
            s = re.sub(r"brief: '[^']*'", lambda _: f"brief: '{brief}'", m.group(0), count=1)
            s = re.sub(r"knows: \[\[.*?\]\](?= \})", lambda _: f"wakes: '{wakes}', {knows}", s, count=1)
            s = re.sub(r"alloc: \d+", f"alloc: {alloc}", s, count=1)
            s = re.sub(r"c: \{[^}]*\}", lambda _: c, s, count=1)
            s = re.sub(r"winR: [\d.]+", f"winR: {hit:.2f}", s, count=1)
            s = re.sub(r" probation: '[^']*',", "", s, count=1)
            return re.sub(r"wk: [-\d.]+, bench: [-\d.]+, below: \d+, closed: \d+, followed: '[^']*'(, idle: true)?(, quiet: \d+)?",
                          lambda _: tail, s, count=1)
        src = re.sub(rf"\{{ id: '{re.escape(pid)}', name: [^\n]*", one, src, count=1)
    src = src.replace("const nameOf = (id) => PODS.find((p) => p.id === id).name;",
                      "const nameOf = (id) => ((PODS.find((p) => p.id === id) || {}).name || String(id));", 1)
    src = src.replace("wakes: 'Six Wakes A Day',", "wakes: p.wakes || 'Six Wakes A Day',", 1)

    board = sorted(state.get("board") or [], key=lambda b: str(b.get("t") or ""), reverse=True)
    talk = []
    for b in board[:12]:
        k = str(b.get("kind") or "note").lower()
        k = {"review": "reply"}.get(k, k if k in _KIND_XP else "note")
        to = b.get("to")
        talk.append(f"{{ t: '{_hhmm(b.get('t'))}', kind: '{k}', from: '{_js(str(b.get('pod') or 'desk'))}', "
                    f"to: {repr(_js(str(to))) if to and to != 'all' else 'null'}, text: '{_js(str(b.get('text') or '')[:120])}', "
                    f"xp: '+{_KIND_XP[k]}' }}")
    if talk:
        src = re.sub(r"talk: \[\n.*?\]\.reverse\(\) \};", lambda _: "talk: [" + ", ".join(talk) + "] };", src, count=1, flags=re.S)

    tickets = sorted(state.get("tickets") or [], key=lambda t: str(t.get("updated") or t.get("created") or ""), reverse=True)
    pills = {"blocked": ("Blocked", "pill('#FDECEC', '#B3261E')"), "closed": ("Closed", "pill('#E9F7EC', '#248A3D')")}
    rev = []
    for t in tickets[:6]:
        st = str(t.get("status") or "open").lower()
        name, pl = pills.get(st, ("In Review", "pill('#E8F2FF', '#0066CC')"))
        pn = (pods.get(str(t.get("pod"))) or {}).get("name") or t.get("pod") or "?"
        risk = f" · {float(t['risk_pct']):.2f}% Risk" if isinstance(t.get("risk_pct"), (int, float)) else ""
        res = f" · {float(t['R']):+.2f} R" if isinstance(t.get("R"), (int, float)) else ""
        rev.append(f"{{ ticket: '{_js(str(t.get('id') or '?'))} · {_js(str(pn).title())}', "
                   f"what: '{_js(str(t.get('side') or '').title())} {_js(str(t.get('instrument') or ''))}{risk}{res}', "
                   f"note: '{_js(str(t.get('why') or t.get('thesis') or '')[:140])}',state: '{name}', pill: {pl} }}")
    if rev:
        src = re.sub(r"const reviews = \[\n.*?\n    \];", lambda _: "const reviews = [" + ", ".join(rev) + "];", src, count=1, flags=re.S)

    today = str(state.get("t") or dt.datetime.now().isoformat())[:10]
    msgs = sum(1 for b in board if str(b.get("t") or "")[:10] == today)
    sts = [str(t.get("status") or "open").lower() for t in tickets]
    open_n, blocked = sum(s not in ("closed", "blocked") for s in sts), sts.count("blocked")
    idle = sum(1 for p in pods.values() if not int((p.get("score") or {}).get("trades") or 0))
    src = re.sub(r"\{ label: 'Messages Today', value: [^\n]*",
                 lambda _: f"{{ label: 'Messages Today', value: '{msgs}', sub: 'Board Posts Since Midnight', style: big }},", src, count=1)
    src = re.sub(r"\{ label: 'Tickets In Review', value: [^\n]*", lambda _: (
        f"{{ label: 'Tickets In Review', value: '{open_n}', sub: '{blocked} Blocked · {sts.count('closed')} Closed', style: big }},"),
        src, count=1)
    return re.sub(r"\{ label: 'Pods Idle', value: '[^']*', sub: '[^']*'",
                  lambda _: f"{{ label: 'Pods Idle', value: '{idle}', sub: 'No Closed Trade Yet'", src, count=1)


EXPERTS = pathlib.Path(__file__).resolve().parent.parent / "mql5" / "Experts"
_LEG_ALIAS = {"hold": "goldhold", "grid": "audcad", "cross": "yen"}
_ARCHIVE_TO = {"Bell": "Hydra", "Lattice": "Hydra", "Orient": "Hydra", "Tokyo": "Hydra"}


def _ea_text(p):
    b = p.read_bytes()
    return b.decode("utf-16") if b[:2] in (b"\xff\xfe", b"\xfe\xff") else b.decode("utf-8", "replace")


def _ea_versions(root=None):
    out = {}
    for d in (root or EXPERTS).glob("Aurum*"):
        f = d / (d.name + ".mq5")
        try:
            m = re.search(r'#property\s+version\s+"([^"]+)"', _ea_text(f))
        except OSError:
            continue
        if m:
            out[d.name] = m.group(1)
    return out


def _archived(root=None):
    try:
        names = sorted(d.name[5:] for d in ((root or EXPERTS) / "_archive").iterdir() if d.is_dir() and d.name.startswith("Aurum"))
    except OSError:
        return None
    return [[n, _ARCHIVE_TO.get(n, "Retired")] for n in names]


def _patch_eas_page(src, state, positions, root=None):
    lim, st = state.get("limits") or {}, state.get("status") or {}
    fl = lim.get("floors") or {}
    eq, bal = float(lim.get("equity") or 0), float(lim.get("balance") or 0)
    kill, day = float(fl.get("kill") or 0), float(fl.get("day") or 0)
    if kill:
        src = re.sub(r"const START = 10000, KILL = [\d.]+;", lambda _: f"const START = 10000, KILL = {kill:.2f};", src, count=1)
    src = re.sub(r"\n    today\.golddip = [^\n]*", "", src, count=1)
    if eq:
        src = src.replace("equity: 9962.86, on", f"equity: {eq:.2f}, on", 1)
        src = src.replace("9962.86 + drift", "s.equity", 1)
    if bal:
        src = src.replace("sub: 'Balance 9,958.40'", f"sub: 'Balance {bal:,.2f}'", 1)

    pos = [p for p in positions or [] if isinstance(p, dict)]
    if pos:
        p0 = pos[0]
        sub = f"{p0.get('symbol') or '?'} {float(p0.get('volume') or 0):.2f}" + (f" · {p0['comment']}" if p0.get("comment") else "")
        sub += f" +{len(pos) - 1} More" if len(pos) > 1 else ""
    else:
        sub = "Flat"
    src = src.replace("value: '1', sub: 'XAUUSD 0.05 · Gold Dip'", f"value: '{len(pos)}', sub: '{_js(sub)}'", 1)

    halt = st.get("halt")
    src = src.replace("grey: ['#E8E8ED', '#424245'] };", "grey: ['#E8E8ED', '#424245'], red: ['#FDECEC', '#B3261E'] };", 1)
    if day:
        src = src.replace("['Daily Loss Guard', '3.0%', 'Armed', 'green']", f"['Daily Loss Guard', '{day:,.2f}', 'Armed', 'green']", 1)
    if kill:
        src = src.replace("['Max Loss Kill', '9,311.30', 'Armed', 'green']",
                          f"['Max Loss Kill', '{kill:,.2f}', " + ("'Halted', 'red']" if halt else "'Armed', 'green']"), 1)
    if halt:
        src = src.replace("fundedState: 'Trading', fundedPill: pill('#E9F7EC', '#248A3D')",
                          "fundedState: 'Halted', fundedPill: pill('#FDECEC', '#B3261E')", 1)

    for name, ver in _ea_versions(root).items():
        src = re.sub(rf"name: '{re.escape(name)}', ver: '[^']*'", lambda _, n=name, v=ver: f"name: '{n}', ver: '{_js(v)}'", src, count=1)
    src = src.replace("v: 'mql5/Experts/' + e.name + '.mq5'", "v: 'mql5/Experts/' + e.name + '/' + e.name + '.mq5'", 1)
    arch = _archived(root)
    if arch:
        src = re.sub(r"const ARCHIVED = \[[^\n]*\];", lambda _: "const ARCHIVED = " + json.dumps(arch).replace('"', "'") + ";", src, count=1)

    armed = (state.get("edges") or {}).get("armed") or []
    m = re.search(r"const LEGS = \[\n(.*?)\n\];", src, re.S)
    if armed and m:
        design = {}
        for row in m.group(1).split("\n"):
            g = dict(re.findall(r"(\w+): '([^']*)'", row))
            if g.get("id"):
                design[g["id"]] = g
        rows = []
        for a in armed:
            eid = str(a.get("edge") or "?")
            d = design.get(_LEG_ALIAS.get(eid, eid), {})
            risk = a.get("risk_pct")
            size = f"{float(risk):.2f}%" if isinstance(risk, (int, float)) else "—"
            rows.append(f"  {{ id: '{_js(eid)}', name: '{_js(d.get('name') or eid.title())}', market: '{_js(str(a.get('market') or '—'))}', "
                        f"window: '{_js(d.get('window') or '—')}', pod: '{_js(d.get('pod') or '—')}', size: '{size}', trades: '—', on: true }}")
        src = src[:m.start()] + "const LEGS = [\n" + ",\n".join(rows) + "\n];" + src[m.end():]
        src = src.replace("legs: '11 Of 12 Armed'", f"legs: '{len(rows)} Armed'", 1)
    return src


# Processes page: design job name -> (desk schedule key, hours after which the last run counts as late).
_JOBS = {"Calendar Pull": ("calendar", 26), "London Desk": ("london_brief", 74), "Crypto Desk": ("crypto_weekend", 192),
         "Weekly Review": ("weekly", 192), "NY Desk": ("ny_brief", 74), "NY Debrief": ("debrief", 74),
         "Scorekeeper": ("scorekeeper", 26), "Asia Desk": ("asia_brief", 74), "Commit And Push": ("commit", 26),
         "Code Monitor": ("monitor", 2)}
_RUN_TONE = {"done": ("OK", "green"), "running": ("Running", "blue"), "queued": ("Queued", "grey"),
             "skipped": ("Skipped", "grey")}


def _ts(x):
    try:
        t = dt.datetime.fromisoformat(str(x))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _ago(sec):
    sec = max(0, int(sec))
    if sec >= 172800:
        return f"{sec // 86400}d Ago"
    if sec >= 3600:
        return f"{sec // 3600}h {sec % 3600 // 60:02d}m Ago"
    return f"{sec // 60}m Ago"


def _dur(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}m {sec % 60:02d}s" if sec >= 60 else f"{sec}s"


def _patch_processes_page(src, state, live):
    now = _ts(state.get("t")) or dt.datetime.now(dt.timezone.utc)
    sched = {str(r.get("name")): _ts(r.get("ran")) for r in state.get("schedule") or [] if isinstance(r, dict)}
    recent = [r for r in ((state.get("runner") or {}).get("recent") or []) if isinstance(r, dict)]
    latest = {}
    for r in recent:  # newest first
        latest.setdefault(str(r.get("name")), r)

    def job_row(m):
        row = m.group(0)
        key, late_h = _JOBS[m.group(1)]
        ran = sched.get(key)
        if ran is None:
            return row
        age = (now - ran).total_seconds()
        last_run = latest.get(key)
        st = ("Failed" if last_run and last_run.get("status") not in _RUN_TONE
              else "Late" if age > late_h * 3600 else "OK")
        row = re.sub(r"last: '[^']*'", lambda _: f"last: '{ran.strftime('%a %H:%M')} · {_ago(age)}'", row, count=1)
        row = re.sub(r"state: '[^']*'", lambda _: f"state: '{st}'", row, count=1)
        if key == "crypto_weekend":
            row = row.replace("runs: 'Daily'", "runs: 'Weekends'")
        if key == "commit":
            row = row.replace("when: '23:30 Local', utc: 1350", "when: '23:30 UTC', utc: 1410")
        return row

    names = "|".join(re.escape(n) for n in _JOBS)
    src = re.sub(r"\{ name: '(" + names + r")', [^\n]*", job_row, src)
    src = src.replace("const t = j.state === 'OK' ? TONES.green : TONES.amber",
                      "const t = j.state === 'OK' ? TONES.green : j.state === 'Failed' ? TONES.red : TONES.amber", 1)

    # Recent runs from the desk runner.
    label = {k: n for n, (k, _) in _JOBS.items()}
    rows = []
    for r in recent[:8]:
        t0, t1 = _ts(r.get("started") or r.get("queued")), _ts(r.get("done"))
        if t0 is None:
            continue
        res, tone = _RUN_TONE.get(str(r.get("status")), ("Failed", "red"))
        note = str(r.get("kind") or "job").title()
        if r.get("pods"):
            note += " · " + ", ".join(str(p).title() for p in r["pods"])
        if t1:
            note += " · " + _dur((t1 - t0).total_seconds())
        if r.get("why") and r.get("status") != "done":
            note += " · " + str(r["why"])
        name = str(r.get("name") or r.get("pod") or "?")
        rows.append([_js(label.get(name, name.replace("_", " ").title())), _js(note), res, tone, t0.isoformat()])
    if rows:
        src = src.replace("class Component extends DCLogic {",
                          "const LIVE_RUNS = " + json.dumps(rows, ensure_ascii=False) + ";\nclass Component extends DCLogic {", 1)
        src = re.sub(r"const runs = RUN_POOL\.slice\(0, 5\)\.map\([^\n]*",
                     lambda _: "const runs = LIVE_RUNS.map((r) => ({ r, t: new Date(r[4]) }));", src, count=1)
        today = [r for r in recent if (_ts(r.get("started") or r.get("queued")) or now).date() == now.date()]
        ok = sum(r.get("status") == "done" for r in today)
        src = src.replace("value: '41', sub: '39 OK · 2 Dry'",
                          f"value: '{len(today)}', sub: '{ok} OK · {len(today) - ok} Other'", 1)
        fails = [(_ts(r.get("started") or r.get("queued")), r) for r in recent
                 if r.get("status") not in _RUN_TONE]
        fails = [(t, r) for t, r in fails if t]
        n24 = sum((now - t).total_seconds() < 86400 for t, _ in fails)
        sub = ("Last Failure " + max(t for t, _ in fails).strftime("%a %d %b")) if fails else "None In Recent Runs"
        src = src.replace("value: '0', sub: 'Last Failure Thu 29 Oct', style: big + '; color: #248A3D'",
                          f"value: '{n24}', sub: '{sub}', style: big + '; color: {'#B3261E' if n24 else '#248A3D'}'", 1)

    # Heartbeats: real ages in seconds where the desk has a source; tester and demo stay as designed.
    m = re.search(r"const age = \{ relay: (\d+), mt5: (\d+), demo: (\d+), tester: (\d+), sched: (\d+), data: (\d+) \};", src)
    if m:
        age = dict(zip(("relay", "mt5", "demo", "tester", "sched", "data"), map(int, m.groups())))
        detail = {}
        hb = (state.get("status") or {}).get("heartbeat") or {}
        hbt = _ts(hb.get("t"))
        if hbt:
            age["mt5"] = max(0, int((now - hbt).total_seconds()))
            detail["mt5"] = f"{str(hb.get('broker') or 'mt5').upper()} · " + ("Connected" if hb.get("ok") else str(hb.get("why") or "Not OK"))
        steps = ((live or {}).get("steps") or {}).get("relay") or []
        if steps:
            line = str(steps[-1])
            try:
                rt = dt.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                age["relay"] = max(0, int((dt.datetime.now() - rt).total_seconds()))
                detail["relay"] = "Last · " + line[19:].strip()[:60]
            except ValueError:
                pass
        ran = [t for t in sched.values() if t]
        if ran:
            age["sched"] = max(0, int((now - max(ran)).total_seconds()))
            detail["sched"] = f"{len(ran)} Jobs Tracked"
        age["data"] = 0
        detail["data"] = "Built On Each Page Load"
        detail.setdefault("tester", "—")  # the design's 'Running Job 1 Of 4' had no source
        src = src[:m.start()] + "const age = " + json.dumps(age) + ";" + src[m.end():]
        for bid, lim in (("relay", 7200), ("mt5", 120), ("sched", 3900), ("data", 60)):
            src = re.sub(r"(\{ id: '" + bid + r"', [^\n]*?limit: )\d+", lambda g: g.group(1) + str(lim), src, count=1)
        for bid, text in detail.items():
            src = re.sub(r"(\{ id: '" + bid + r"', [^\n]*?detail: ')[^']*'", lambda g: g.group(1) + _js(text) + "'", src, count=1)
        src = src.replace("age: a === 0 ? 'Now' : a + 's Ago', limit: b.limit + 's'",
                          "age: a === 0 ? 'Now' : dur(a) + ' Ago', limit: dur(b.limit)", 1)
    return src


DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"


def _jsonl(p):
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def _jfile(p):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _title(s):
    return " ".join(w[:1].upper() + w[1:] for w in str(s).split(" "))


def _cut(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _gate_figs(g):
    figs = {x.get("gate"): str(x.get("figure") or "") for x in (g or {}).get("gates") or [] if isinstance(x, dict)}
    halves = re.sub(r"\s*\(.*", "", figs.get("halves", "")) or "—"
    corr = re.search(r"book\s+([+-]?\d+\.\d+)", figs.get("corr", ""))
    book = re.search(r"([+-]?\d+\.\d+)\s*->\s*([+-]?\d+\.\d+)", figs.get("book", ""))
    return {"sharpe": halves + " (To 2017 / From 2018)" if halves != "—" else "—",
            "stress": ("1.5x Cost Sharpe " + figs["costs"]) if figs.get("costs") else "—",
            "corr": corr.group(1) if corr else "—",
            "adds": _sgn(float(book.group(2)) - float(book.group(1))) if book else "—"}


def _steer_gaps(text):
    m = re.search(r"^## Top \d gaps.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    out = []
    for item in re.findall(r"^\d\.\s+(.*?)(?=^\d\.\s|\Z)", m.group(1) if m else "", re.M | re.S):
        b = re.match(r"\*\*(.+?)\*\*\s*(.*)", " ".join(item.split()))
        if not b:
            continue
        name = re.sub(r"\s*\([^)]*\)", "", b.group(1)).rstrip(".")
        # The first plain sentence; ones with a colon are lead-ins to a list or an example.
        sents = re.split(r"(?<=\.)\s+", b.group(2).replace("**", ""))
        why = next((x for x in sents if ":" not in x and len(x) < 140), b.group(1))
        out.append({"key": b.group(1).lower(), "name": _title(name.split(",")[0]), "why": _cut(why, 110)})
    return out


def _patch_research_page(src, state, live, root=None):
    docs = pathlib.Path(root) if root else DOCS
    queue = _jsonl(docs / "ideas" / "queue.jsonl")
    backlog = [x for x in _jsonl(docs / "ideas" / "backlog.jsonl") if x.get("status") == "open"]
    results = _jsonl(docs / "ideas" / "results.jsonl")
    gates = [g for g in (_jfile(p) for p in sorted((docs / "gates").glob("*.json"))) if isinstance(g, dict)]
    cj = _jfile(docs / "candidates.json") or {}
    cands = [c for c in (cj.get("candidates") if isinstance(cj, dict) else cj) or [] if isinstance(c, dict)]
    book = _jfile(docs / "book.json") or {}
    gj = _jfile(docs / "gaps.json") or {}
    try:
        steer = (docs / "ideas" / "steer.md").read_text(encoding="utf-8")
    except OSError:
        steer = ""
    titles = {x.get("id"): x.get("title") for x in results + queue + backlog if x.get("title")}
    status = {c.get("id"): c.get("status") for c in cands}
    passed = [g for g in gates if str(g.get("verdict", "")).upper() == "PASS"]

    # Funnel: every idea ever tried, then each stage it reached.
    ids = {x.get("id") for x in queue + backlog + results + gates} - {None}
    live_c = [c for c in cands if c.get("status") in ("tester", "demo", "live", "integrated")]
    legs = len((book.get("legs") or {})) or len(gj.get("legs") or [])
    n = [len(ids), len({x.get("id") for x in results + gates} - {None}), len(gates), len(passed), len(live_c), legs]
    if n[0]:
        funnel = [["Ideas Found", "Finder · Queue, Scans, Gates", n[0]], ["Prescreened", "Builder · results.jsonl", n[1]],
                  ["Full Backtest", "Builder · docs/gates", n[2]], ["Passed Gate", "tools/gates.py", n[3]],
                  ["Tester Matched", "Judge · candidates.json", n[4]], ["In The Book", "docs/book.json", n[5]]]
        src = re.sub(r"const FUNNEL = \[.*?\n\];", lambda _: "const FUNNEL = " + json.dumps(funnel, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)
        src = re.sub(r"found: \d+ \}", lambda _: f"found: {n[0]} }}", src, count=1)
        # Counts span 1 to hundreds, so bars use a log scale; the labels keep the exact counts.
        src = src.replace("(v / s.found * 100).toFixed(1)", "(Math.log(1 + v) / Math.log(1 + s.found) * 100).toFixed(1)", 1)
        src = src.replace("{ label: 'Ideas · 30 Days', value: String(s.found), sub: 'Finder Rotates 4 Sources'",
                          "{ label: 'Ideas Tried', value: String(s.found), sub: 'Queue, Scans And Gates'", 1)

    # Candidates: tester legs, then gate passes still alive, then the newest open ideas.
    rows, seen = [], set()

    def gate_of(c):
        g = c.get("gates")
        return g if isinstance(g, dict) else _jfile(docs / "gates" / f"{c.get('id')}.json") or {}

    for c in sorted(live_c, key=lambda c: str(gate_of(c).get("when", "")), reverse=True):
        g, t = gate_of(c), (c.get("tester") or [{}])
        t0 = t[0] if isinstance(t, list) and t and isinstance(t[0], dict) else {}
        et = c.get("expected_tester")
        syms = [e.get("symbol") for e in (et if isinstance(et, list) else [et]) if isinstance(e, dict) and e.get("symbol")]
        verdict = str(g.get("verdict") or "")
        rows.append(dict(_gate_figs(g), id=c.get("id"), name=_cut(c.get("name") or titles.get(c.get("id")) or _title(str(c.get("id")).replace("_", " ")), 60),
                         stage="Tester", source=_cut(re.split(r"[;(]", str(c.get("source") or c.get("published") or "—"))[0], 40),
                         markets=", ".join(syms) or "—", idea=_cut(c.get("summary") or c.get("reason") or c.get("note") or "—", 240),
                         dd=f"{t0['eq_dd_max_pct']}%" if t0.get("eq_dd_max_pct") is not None else "—",
                         trades=str(t0.get("trades", "—")), gate="Pass" if verdict.upper() == "PASS" else _title(verdict.lower()) or "Not Yet",
                         next=_cut(f"{_title(str(c.get('status')))} · Step {c.get('step', '—')}" + (f" · {c['job']}" if c.get("job") else ""), 60),
                         file=f"docs/gates/{c.get('id')}.json"))
        seen.add(c.get("id"))
    for g in sorted(passed, key=lambda g: str(g.get("when", "")), reverse=True):
        gid = g.get("id")
        if gid in seen or status.get(gid) == "rejected" or len(rows) >= 7:
            continue
        rows.append(dict(_gate_figs(g), id=gid, name=_cut(titles.get(gid) or _title(str(gid).replace("_", " ")), 60), stage="Gate",
                         source=_title(str(gid).split("_")[0]), markets="—", idea=_cut(titles.get(gid) or gid, 240), dd="—",
                         trades="—", gate="Pass", next="Judge Builds It Off, Then A Tester Job", file=f"docs/gates/{gid}.json"))
        seen.add(gid)
    for b in sorted(backlog, key=lambda b: str(b.get("added", "")), reverse=True):
        if len(rows) >= 10:
            break
        rows.append({"id": b.get("id"), "name": _cut(b.get("title") or b.get("id"), 60), "stage": "Idea",
                     "source": _title(str(b.get("kind") or "—")), "markets": _title(str(b.get("gap") or "—")), "adds": "—",
                     "corr": "—", "idea": _cut(b.get("note") or b.get("title"), 240), "sharpe": "—", "dd": "—", "trades": "—",
                     "stress": "—", "gate": "Not Yet", "next": "Finder Reads It In Full, Then The Queue",
                     "file": "docs/ideas/backlog.jsonl"})
    if rows:
        src = re.sub(r"const CANDS = \[.*?\n\];", lambda _: "const CANDS = " + json.dumps(rows, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)
        src = re.sub(r"sel: '[^']*'", lambda _: "sel: '" + _js(rows[0]["id"]) + "'", src, count=1)

    # Gaps: the steer's top gaps, with the open backlog ideas aimed at each.
    sg = _steer_gaps(steer)
    if not sg:
        gp = gj.get("gaps") or {}
        sg = [{"key": m, "name": m.upper(), "why": "The Book Has No Leg On " + m.upper() + "."} for m in gp.get("markets_without_leg") or []]
        sg += [{"key": s, "name": _title(s), "why": "No Leg Earns This Style."} for s in gp.get("styles_without_leg") or []]
        sg += [{"key": h, "name": _title(h) + " Horizon", "why": "Few Legs Hold This Long."} for h in gp.get("thin_horizons") or []]
    if sg:
        out = []
        for gp in sg[:4]:
            aim = [b for b in backlog if b.get("gap") and str(b["gap"]).lower() in gp["key"]]
            out.append({"name": gp["name"], "why": gp["why"], "fill": min(1.0, len(aim) / 10),
                        "filling": f"{len(aim)} Open Idea{'s' if len(aim) != 1 else ''} · {_cut(aim[0].get('title'), 40)}" if aim else "No Candidate Yet"})
        src = re.sub(r"const GAPS = \[.*?\n\];", lambda _: "const GAPS = " + json.dumps(out, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)

    gate_ids = {g.get("id") for g in gates}
    rej = [x for x in queue if x.get("status") == "rejected"][-3:][::-1]
    if rej:
        out = [{"name": _cut(x.get("title") or x.get("id"), 60), "at": "Gate" if x.get("id") in gate_ids else "Prescreen",
                "why": _cut(x.get("reason") or x.get("result") or x.get("why") or "—", 120)} for x in rej]
        src = re.sub(r"const REJECTED = \[.*?\n\];", lambda _: "const REJECTED = " + json.dumps(out, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)

    open_n = len(backlog) + sum(1 for x in queue if x.get("status") not in ("rejected", "done", "funded"))
    src = src.replace("{ label: 'In The Queue', value: '6', sub: 'docs/ideas/queue.jsonl'",
                      f"{{ label: 'In The Queue', value: '{open_n}', sub: 'Open · docs/ideas/backlog.jsonl'", 1)
    if gates:
        src = src.replace("{ label: 'Gate Pass Rate', value: '22%', sub: '7 Of 31 Prescreened'",
                          f"{{ label: 'Gate Pass Rate', value: '{round(100 * len(passed) / len(gates))}%', sub: '{len(passed)} Of {len(gates)} Gated'", 1)
    bs = gj.get("book_sharpe_2018") or (book.get("backtest") or {}).get("sharpe_2018")
    if bs:
        src = src.replace("{ label: 'Book Sharpe', value: '1.38', sub: '+0.04 After Last Change'",
                          f"{{ label: 'Book Sharpe', value: '{float(bs):.2f}', sub: 'From 2018 · docs/gaps.json'", 1)

    # Portfolio-manager card: last weekly review, next Saturday, legs the book is better without.
    sd = re.search(r"^# Steer - (\d{4}-\d{2}-\d{2})", steer, re.M)
    try:
        last = dt.date.fromisoformat(sd.group(1)) if sd else dt.datetime.fromisoformat(str(book.get("when"))).date()
    except ValueError:
        last = None
    if last:
        hm = str(book.get("when") or "")[11:16]
        nxt = last + dt.timedelta(days=(5 - last.weekday()) % 7 or 7)
        src = re.sub(r"\{ k: 'Last Run', v: '[^']*' \}", lambda _: "{ k: 'Last Run', v: '" + last.strftime("%a %d %b").replace(" 0", " ") + (" · " + hm if hm else "") + "' }", src, count=1)
        src = re.sub(r"\{ k: 'Next Run', v: '[^']*' \}", lambda _: "{ k: 'Next Run', v: '" + nxt.strftime("%a %d %b").replace(" 0", " ") + " · Or After A Book Change' }", src, count=1)
    if gj.get("legs") and gj.get("book_sharpe_2018"):
        dil = [str(x.get("leg")) for x in gj["legs"] if isinstance(x, dict) and float(x.get("book_without") or 0) > float(gj["book_sharpe_2018"])]
        src = re.sub(r"\{ k: 'Legs Diluting The Book', v: '[^']*' \}",
                     lambda _: "{ k: 'Legs Diluting The Book', v: '" + _js(f"{len(dil)}" + (" · " + ", ".join(dil) if dil else "")) + "' }", src, count=1)
    if sg:
        src = re.sub(r"\{ k: 'Steer Written', v: '[^']*' \}",
                     lambda _: "{ k: 'Steer Written', v: '" + _js(", Then ".join(g["name"] for g in sg[:2])) + "' }", src, count=1)
    return src


ROOT = DOCS.parent
_FINAL = {"rejected", "done", "funded", "failed", "dropped"}


def _relay(role):
    """logs/autopilot/last-<role>.json (written with a BOM) or {}."""
    try:
        d = json.loads((ROOT / "logs" / "autopilot" / f"last-{role}.json").read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


_CTRL_JS = [
    # no fake "Applied" every 5 seconds: the log shows what the desk answered
    ("    const log = tick % 5 === 0 ? s.log.map((e) => (e.state === 'Drafted' ? { ...e, state: 'Applied' } : e)) : s.log;\n"
     "    this.setState({ now: new Date(), tick, log });",
     "    this.setState({ now: new Date(), tick });"),
    ("    const entry = { at: hm(s.now), what: verb + ' ' + w.name, who: 'You · From The Dashboard', state: 'Drafted' };\n"
     "    this.setState({ states: { ...s.states, [p.id]: p.to }, pending: null, log: [entry, ...s.log].slice(0, 8) });",
     "    const kind = { 'Desk Pods': 'pod', 'Pipeline': 'pipeline', 'Demo Legs': 'demo' }[w.group];\n"
     "    const action = p.to === 'Running' ? 'resume' : p.to === 'Paused' ? 'pause' : 'stop';\n"
     "    const key = Date.now();\n"
     "    const entry = { key, at: hm(s.now), what: verb + ' ' + w.name, who: 'You · From The Dashboard', state: 'Sending' };\n"
     "    this.setState({ pending: null, log: [entry, ...s.log].slice(0, 8) });\n"
     "    const done = (ok, why) => { const t = this.state; this.setState({ states: ok ? { ...t.states, [p.id]: p.to } : t.states,\n"
     "      log: t.log.map((e) => (e.key === key ? { ...e, state: ok ? 'Applied' : 'Refused', who: ok ? e.who : why } : e)) }); };\n"
     "    fetch('/api/control', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Desk': 'control' },\n"
     "      body: JSON.stringify({ kind, target: w.id, action, why: verb + ' from the dashboard' }) })\n"
     "      .then((r) => r.json().then((j) => done(r.ok && j.ok, j.error || ('HTTP ' + r.status))))\n"
     "      .catch((e) => done(false, 'Desk Not Reached: ' + e));"),
    ("Drafted: 'blue', Cancelled: 'grey' };", "Drafted: 'blue', Sending: 'blue', Refused: 'red', Cancelled: 'grey' };"),
    ("const drafts = s.log.filter((e) => e.state === 'Drafted').length;",
     "const drafts = s.log.filter((e) => e.state === 'Sending').length;"),
    ("{ label: 'Drafts Waiting', value: String(drafts), sub: 'Applied At The Next Heartbeat', style: big }",
     "{ label: 'Changes Sending', value: String(drafts), sub: 'Applied On Confirm, Logged To The Journal', style: big }"),
    ("pauseLabel: st === 'Running' ? 'Draft Pause' : 'Draft Resume'", "pauseLabel: st === 'Running' ? 'Pause' : 'Resume'"),
    (">Draft Stop</button>", ">Stop</button>"),
    ("'New Entries Start Again At The Next Heartbeat.'", "'New Entries Start Again At The Next Run.'"),
    ("<span>Switches Here Write A Draft Only; Nothing Places, Closes Or Sizes A Trade.",
     "<span>Switches Apply On Confirm (desk/controls.py) And Go Into The Journal; Nothing Places, Closes Or Sizes A Trade."),
    ("The AurumFunded 1.20 Deploy And The Fidelity", "The AurumFunded Deploy And The Fidelity"),
]


def _patch_controls_page(src, state, positions=None):
    """Controls: pod and pipeline switches, owner locks, the funded risk rows and the change log."""
    try:
        risk = json.loads((ROOT / "desk" / "risk.json").read_text(encoding="utf-8-sig"))
        prof = risk["profiles"][risk["active"]]
    except (OSError, ValueError, KeyError, TypeError):
        risk, prof = {}, {}
    try:
        owns = {k: (v or {}).get("owns") or [] for k, v in
                json.loads((ROOT / "desk" / "config.json").read_text(encoding="utf-8-sig")).get("pods", {}).items()}
    except (OSError, ValueError, AttributeError):
        owns = {}
    tickets = [t for t in state.get("tickets") or [] if isinstance(t, dict)]
    try:
        from desk import controls
        ctl = controls.status()
    except Exception:
        ctl = {}
    paused = set((state.get("alloc") or {}).get("paused") or []) | set(ctl.get("pod") or [])
    sw = []
    for p in state.get("pods") or []:
        n = str(p.get("name") or "")
        if not n:
            continue
        meta = _sk_line(p.get("score"))
        last = max((t.get("created") or "" for t in tickets if t.get("pod") == n), default="")
        if last:
            meta += " · Last Ticket " + _hhmm(last)
        o = owns.get(n) or []
        what = ("Tickets For " + ", ".join(o[:4]) + (f" And {len(o) - 4} More." if len(o) > 4 else ".")) if o else \
            f"Phase {p.get('opens_phase', '?')} Pod, Tickets Across All Markets."
        st = "Paused" if p.get("paused") or n in paused else "Running" if p.get("enabled") and p.get("active") else "Stopped"
        sw.append({"id": n, "group": "Desk Pods", "name": {"fxmacro": "FX Macro"}.get(n, _title(n)) + " Pod", "what": what, "meta": meta, "state": st})
    halted = (ROOT / "logs" / "autopilot" / "PAUSE").exists()
    ideas = [x for x in _jsonl(DOCS / "ideas" / "queue.jsonl") if isinstance(x, dict)]
    jobs = (_jfile(DOCS / "autopilot" / "queue.json") or {}).get("jobs") or []
    jobs = [j for j in (jobs if isinstance(jobs, list) else []) if isinstance(j, dict)]
    run_n = sum(j.get("status") == "running" for j in jobs)
    q_n = sum(j.get("status") == "queued" for j in jobs)
    extra_meta = {"builder": f"{sum(str(x.get('status')) not in _FINAL for x in ideas)} In The Queue",
                  "tester": f"{run_n} Running · {q_n} Queued"}
    names = {"finder": "Finder Loop", "builder": "Builder Loop", "tester": "Tester Queue", "judge": "Judge"}
    designs = {"finder": "Every 2 Hours, Four Sources, Aimed At The Top Gap.",
               "builder": "Builds, Gates And Queues Tester Jobs From The Queue.",
               "tester": "Runs Strategy Tester Jobs In The Tester Install.",
               "judge": "Judges Tester Results And Merges Passing Legs."}
    now = dt.datetime.now()
    for role in ("finder", "builder", "tester", "judge"):
        r = _relay(role)
        parts = [_title(r.get("model") or "?")]
        try:
            parts.append("Last Run " + _ago((now - dt.datetime.fromisoformat(str(r.get("ended"))[:19])).total_seconds()))
        except ValueError:
            pass
        if role in extra_meta:
            parts.append(extra_meta[role])
        if int(r.get("empty_streak") or 0) > 0:
            parts.append(f"{r['empty_streak']} Empty Runs")
        if r.get("failed"):
            parts.append("Last Run Failed")
        if role in (ctl.get("pipeline") or []):
            parts.insert(0, "Paused By You")
        elif halted:
            parts.insert(0, "Whole Pipeline Paused")
        elif int(r.get("fails_in_row") or 0) >= 3:
            parts.insert(0, "Auto-Paused After 3 Fails")
        st = "Paused" if halted or role in (ctl.get("pipeline") or []) or int(r.get("fails_in_row") or 0) >= 3 else "Running"
        sw.append({"id": role, "group": "Pipeline", "name": names[role], "what": _cut(r.get("reason"), 90) or designs[role],
                   "meta": " · ".join(parts), "state": st})
    ver = _ea_versions()
    appr = (_jfile(DOCS / "autopilot" / "approvals.json") or {}).get("items") or []
    pend = [a for a in appr if isinstance(a, dict) and a.get("status") == "pending"]
    halt = (state.get("status") or {}).get("halt")
    desk_st = "Stopped" if halt else "Running"
    for eid, ea, nm in (("hydra", "AurumHydra", "Hydra Demo Legs"), ("funded", "AurumFunded", "Funded EA · Demo")):
        v = ver.get(ea, "?")
        what = f"All Hydra Legs On The Demo. Stops New Entries." if eid == "hydra" else f"AurumFunded {v} On The Demo. Stops New Entries."
        armed = len((state.get("edges") or {}).get("armed") or [])
        meta = f"{ea} {v}" + (f" · {armed} Legs Armed" if eid == "hydra" and armed else "")
        flag = eid in (ctl.get("demo") or [])
        if flag:
            meta += " · Stop Flag Set" + (" · Read From AurumFunded 1.23" if eid == "funded" else " · Read From AurumHydra 1.43")
        sw.append({"id": eid, "group": "Demo Legs", "name": nm, "what": what, "meta": meta,
                   "state": "Stopped" if flag else desk_st})
    src = re.sub(r"const SWITCHES = \[.*?\n\];", lambda _: "const SWITCHES = " + json.dumps(sw, ensure_ascii=False) + ";",
                 src, count=1, flags=re.S)

    locks = [{"name": "Risk File", "why": "Daily Loss, Max Loss And Per-Trade Risk For Every Account.",
              "where": f"desk/risk.json · {risk.get('active', '?')}", "state": "Locked"},
             {"name": "Resume After A Halt", "why": ("Halted: " + _cut(halt if isinstance(halt, str) else (halt or {}).get("why")
                                                                       if isinstance(halt, (str, dict)) else str(halt), 70))
              if halt else "After A Guard Halts The Desk, Only The Owner Resumes It.", "where": "cli resume",
              "state": "Waiting" if halt else "Locked"},
             {"name": "Live Trading", "why": "All Accounts Trade Demo. Going Live Is The Owner’s Call.",
              "where": "allow_live: " + ("true" if prof.get("allow_live") else "false"),
              "state": "Waiting" if prof.get("allow_live") else "Off"}]
    for a in pend:
        locks.append({"name": _cut(str(a.get("what") or a.get("id")).split(":")[0], 40), "why": _cut(a.get("what"), 90),
                      "where": f"approvals · {a.get('id', '')}", "state": "Waiting"})
    locks.append({"name": "MT5 Terminal · T16", "why": "Watched For Heartbeats. Never Restarted, Closed Or Compiled Into.",
                  "where": "T16", "state": "Never Touched"})
    src = re.sub(r"const LOCKS = \[.*?\n\];", lambda _: "const LOCKS = " + json.dumps(locks, ensure_ascii=False) + ";",
                 src, count=1, flags=re.S)

    lim = state.get("limits") or {}
    if prof and lim:
        bal = float(lim.get("day_balance") or lim.get("balance") or 0) or 1.0
        day_used = round(max(0.0, bal - float(lim.get("equity") or bal)) / bal * 100, 2)
        dd = round(float((lim.get("record") or {}).get("max_dd_pct") or 0), 2)
        live_t = [t for t in tickets if t.get("status") in ("placed", "open")]
        per_ins = max(collections.Counter(str(t.get("instrument")) for t in live_t).values(), default=0)
        n_open = len(positions) if isinstance(positions, list) else len(live_t)
        per = max((float(t.get("risk_pct") or 0) for t in live_t), default=0.0)
        today = str(lim.get("day") or state.get("t", ""))[:10]
        n_today = sum(str(t.get("created") or "").startswith(today) for t in tickets)
        cap_n = int(float(prof.get("desk_open_pct") or 3) / float(prof.get("per_trade_pct") or 0.5))
        acct = str(lim.get("account") or "").split("/")
        title = "Funded Account · " + " ".join(_title(x) for x in acct[:2]) if acct[0] else "Funded Account"
        g = lambda k, d=0: float(prof.get(k) or d)
        rows = [["Daily Loss", f"Desk Halts At {g('daily_loss_pct'):g}%", day_used, g("daily_loss_pct", 4), "%"],
                ["Max Loss", f"Hard Limit {g('max_loss_pct'):g}%; Desk Halts At {g('kill_dd_pct'):g}%", dd, g("kill_dd_pct", 7), "%"],
                ["Risk Per Trade", "Per Ticket, Of Balance", per, g("per_trade_pct", 0.5), "%"],
                ["Open Positions", f"At Once; Desk Risk Cap {g('desk_open_pct'):g}%", n_open, cap_n, ""],
                ["Per Instrument", f"Desk Positions On One Symbol · {n_today} Tickets Today", per_ins,
                 g("max_per_instrument", 3), ""],
                ["News Blackout", "Minutes Each Side Of High Impact", g("news_window_min"), g("news_window_min", 2), " Min"]]
        block = ("funded: { title: " + json.dumps(title, ensure_ascii=False) + ", tag: " +
                 json.dumps(f"{risk.get('active')} · {_title(prof.get('kind') or '')}", ensure_ascii=False) +
                 ", rows: " + json.dumps(rows, ensure_ascii=False) + " },\n  fivex:")
        src = re.sub(r"funded: \{ title: .*?\n  fivex:", lambda _: block, src, count=1, flags=re.S)
        src = src.replace("sub: 'Funded · Halts At 3%'", f"sub: 'Funded · Halts At {g('daily_loss_pct'):g}%'", 1)

    jr = [j for j in state.get("journal") or [] if isinstance(j, dict)]
    keep = ("ticket_block", "ticket_approve", "ticket_new", "pause", "resume", "halt", "unhalt")
    pick = [j for j in jr if j.get("kind") in keep] or jr
    pick = sorted(pick, key=lambda j: str(j.get("t") or ""), reverse=True)[:8]
    log = [{"at": _hhmm(j.get("t")), "what": _title(str(j.get("kind") or "").replace("_", " ")) +
            (f" · {_title(str(j['target']))}" if j.get("target") else ""),
            "who": _cut(" · ".join(x for x in (_title(str(j.get("by") or "")), str(j.get("why") or "")) if x), 80),
            "state": "Cancelled" if "block" in str(j.get("kind")) else "Applied"} for j in pick]
    if log:
        src = re.sub(r"const LOG0 = \[.*?\n\];", lambda _: "const LOG0 = " + json.dumps(log, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)
    for old, new in _CTRL_JS:
        src = src.replace(old, new, 1)
    return src


def _patch_agents_page(src, live, usage):
    """Agents: role rows from the router and usage.jsonl, the finder back-off, runs today, the relay rows and the
    relay log."""
    auto = ROOT / "logs" / "autopilot"
    router = _jfile(ROOT / "tools" / "autopilot" / "router.json") or {}
    prov = str(router.get("provider") or "claude")
    tiers = ((router.get("providers") or {}).get("claude") or {}).get("tiers") or {}
    rroles = {k: v for k, v in (router.get("roles") or {}).items() if isinstance(v, dict)}
    fb = router.get("fallback") or {}
    order = [_title(str(p)) for p in fb.get("order") or []]
    bmin = fb.get("backoff_minutes")
    now = dt.datetime.now()
    today = now.date().isoformat()
    boff = _jfile(auto / "finder-backoff.json") or {}
    try:
        until = dt.datetime.fromisoformat(str(boff.get("until"))[:19])
    except ValueError:
        until = None
    backed = bool(until and until > now)
    agg = _week_agg(live, usage)
    last = {r: _relay(r) for r in ROLES}

    def one(m):
        rid, body = m.group(1), m.group(0)
        a, rr, st = agg.get(rid), rroles.get(rid), last.get(rid) or {}
        body = re.sub(r"runs: \d+", f"runs: {a['runs'] if a else 0}", body, count=1)
        body = re.sub(r"tokens: [\d.]+", f"tokens: {(a['tok'] / 1e6 if a else 0):.2f}", body, count=1)
        when = "—"
        if a and a["last"]:
            try:
                when = dt.datetime.fromisoformat(a["last"][:19]).strftime("%a %H:%M")
            except ValueError:
                pass
        body = re.sub(r"last: '[^']*'", lambda _: f"last: '{when}'", body, count=1)
        if rr:
            t = str(rr.get("tier") or "")
            body = re.sub(r"tier: '[^']*'", lambda _: f"tier: '{_title(t)}'", body, count=1)
            if tiers.get(t):
                body = re.sub(r"model: '[^']*'", lambda _: f"model: '{_title(str(tiers[t]))}'", body, count=1)
            for k in ("turns", "minutes"):
                if isinstance(rr.get(k), int):
                    body = re.sub(rf"{k}: \d+", f"{k}: {rr[k]}", body, count=1)
        if st.get("reason"):
            why = _cut(_title(_js(str(st["reason"]))), 60)
            body = re.sub(r"task: '[^']*'", lambda _: f"task: 'Last Run: {why}'", body, count=1)
        body = body.replace(", backoff: true", "")
        if rid == "finder" and backed:
            body = body[:-1].rstrip() + ", backoff: true }"
        return body

    src = re.sub(r"const ROLES = \[.*?\n\];",
                 lambda m: re.sub(r"\{ id: '(\w+)'[^\n]*\}", one, m.group(0)), src, count=1, flags=re.S)
    stamp = (until or now).strftime("%Y-%m-%dT%H:%M:%S")
    src = re.sub(r"const BACKOFF_UNTIL = new Date\('[^']*'\);", f"const BACKOFF_UNTIL = new Date('{stamp}');", src, 1)

    counts = {r: int(st.get("runs_today") or 0) for r, st in last.items() if str(st.get("runs_day")) == today}
    counts = {r: n for r, n in counts.items() if n}
    sub = ", ".join(f"{_title(r)} {n}" for r, n in sorted(counts.items(), key=lambda x: -x[1])) or "No Runs Yet"
    src = re.sub(r"const runsToday = [^\n]*;", f"const runsToday = {sum(counts.values())};", src, count=1)
    src = src.replace("sub: 'Finder 3, Builder 1, Doctor 1'", f"sub: '{_js(sub)}'", 1)
    if order:
        src = src.replace("sub: 'Fallback Order Claude, Qwen · Backoff 60 Min'",
                          f"sub: 'Fallback Order {', '.join(order)} · Backoff {bmin} Min'", 1)
        src = src.replace("value: 'Claude, Then Qwen'", f"value: '{', Then '.join(order)}'", 1)
    if bmin:
        src = src.replace("value: '60 Min'", f"value: '{bmin} Min'", 1)
    streak = int(last["finder"].get("empty_streak") or 0)
    fval = "{ label: 'Finder', value: 'Backed Off', sub: '3 Of 3 Empty Runs · ' + backoffLeft, style: big + '; color: #8A4B00' }"
    if backed:
        src = src.replace(fval, fval.replace("'3 Of 3 Empty Runs · '", f"'{streak} Empty Runs In A Row · '"), 1)
    else:
        src = src.replace(fval, f"{{ label: 'Finder', value: 'Ready', sub: '{streak} Empty Runs In A Row', style: big }}", 1)
        src = src.replace("Finder Backed Off · {{backoffLeft}}", "Finder Ready", 1)
    src = src.replace("provider: 'claude', live: {}", f"provider: '{_js(prov)}', live: {{}}", 1)
    # The empty-run list held three made-up commits; the real streak count is in the router state.
    src = re.sub(r"const empties = \[\[.*?\]\]\.map", "const empties = [].map", src, count=1, flags=re.S)
    src = src.replace("Three Empty Runs In A Row, Sun 1 Nov", f"Finder Empty Runs In A Row: {streak}", 1)
    src = _safe(_patch_weeks, src, usage)

    nxt = str((_jfile(auto / "relay.json") or {}).get("next") or "")
    if nxt:
        src = src.replace("value: 'Builder (Finder Backed Off)'",
                          f"value: '{_title(nxt)}{' (Finder Backed Off)' if backed else ''}'", 1)
    week0 = str((live.get("budget") or {}).get("week_start") or "")
    hits = [(str((v or {}).get("set") or (v or {}).get("until") or ""), p)
            for p, v in (_jfile(auto / "provider-backoff.json") or {}).items() if isinstance(v, dict)]
    hits = sorted(h for h in hits if h[0] and week0 and h[0] >= week0)
    if hits:
        at, p = hits[-1]
        src = src.replace("value: 'None This Week', style: 'font-weight: 600; color: #248A3D'",
                          f"value: '{_title(p)} · {at[:10]} {at[11:16]}', style: 'font-weight: 600; color: #8A4B00'", 1)

    try:
        lines = (auto / f"{today}_relay.log").read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        lines = [str(x) for x in ((live.get("steps") or {}).get("relay") or [])]
    log, seen = [], set()
    for ln in reversed(lines):
        m = re.match(r"\S+ (\d\d:\d\d):\d\d\s+(.*)", ln)
        if not m:
            continue
        text = m.group(2).strip()
        key = re.sub(r"\d", "", text)
        if key in seen:
            continue
        seen.add(key)
        low = text.lower()
        who = next((w for w in low.split()[:3] if w in ROLES), "")
        kind = "Backoff" if "backoff" in low or "backed off" in low else "Run" if low.startswith("start") else \
            "Relay" if "next" in low else "Done"
        log.append({"t": m.group(1), "who": _title(who) if who else "Relay", "kind": kind, "text": _cut(_title(_js(text)), 90)})
        if len(log) >= 6:
            break
    if log:
        src = re.sub(r"log: \[\n.*?\n      \] \};", lambda _: "log: " + json.dumps(log, ensure_ascii=False) + " };",
                     src, count=1, flags=re.S)
    return src


_ROLE_NAME = {"finder": "Finder", "builder": "Builder", "tester": "Tester Operator", "judge": "Judge", "reviewer": "Reviewer",
              "monitor": "Monitor", "doctor": "Doctor", "portfolio": "Portfolio Manager"}
_GATE_ORDER = ["halves", "costs", "corr", "belief", "book", "dsr"]


def _tok(r):
    return sum(int(r.get(k) or 0) for k in ("input", "output", "cache_read", "cache_create"))


_CORR_CACHE = {}


def _book_corr(names, days=252):
    """{"legs", "corr"}: the book legs' pairwise correlation over the last `days` days, from tools/book_sim.py legs().
    Runs in a child Python so pandas stays out of the server; cached until book.json or a leg file changes."""
    import subprocess
    import sys
    files = [ROOT / "marketdata" / "hydra_legs_daily.csv.gz", DOCS / "candidates.json", DOCS / "book.json"]
    key = (tuple(names), days, tuple(f.stat().st_mtime if f.exists() else 0 for f in files))
    if key not in _CORR_CACHE:
        code = ("import sys, json; sys.path.insert(0, 'tools'); import book_sim as b; n = json.loads(sys.argv[1]); "
                "L = b.legs(); L = L[[k for k in n if k in L]].iloc[-int(sys.argv[2]):]; "
                "print(json.dumps({'legs': list(L.columns), 'corr': L.corr().fillna(0).round(2).values.tolist()}))")
        res = {}
        try:
            out = subprocess.run([sys.executable, "-c", code, json.dumps(list(names)), str(days)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if out.returncode == 0 and out.stdout.strip():
                res = json.loads(out.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        _CORR_CACHE.clear()
        _CORR_CACHE[key] = res  # a failure is cached too, so a broken file costs one run, not one per page
    return _CORR_CACHE[key]


_LEG_SHORT = {"breakout": "Brk", "morning": "Mor", "cross": "Crs", "noise": "Nse", "quartet": "Qrt", "after": "Aft"}


def _patch_main_book(src, book, corr, days=252):
    """Book Exposure: the headline line from docs/book.json and the leg correlation heatmap from the leg series."""
    bt = book.get("backtest") or {}
    if bt.get("sharpe") is not None:
        pm = bt.get("profitable_months_2018", bt.get("profitable_months")) or 0
        sub = (f"Sharpe {bt.get('sharpe_2018', bt['sharpe'])} Since 2018 ({bt['sharpe']} All Years) · "
               f"{round(pm * 100)}% Profitable Months · "
               f"{round(((bt.get('prop') or {}).get('pass_12m') or 0) * 100)}% FTMO Payout Within 12 Months")
        src = re.sub(r"(Book Exposure</h2>\s*<p[^>]*>)[^<]*", lambda m: m.group(1) + html.escape(sub), src, count=1)
    legs, cm = corr.get("legs") or [], corr.get("corr") or []
    if len(legs) >= 2 and len(cm) == len(legs):
        n = len(legs)
        hl = [str(k).title() for k in legs]
        hs = [_LEG_SHORT.get(k, str(k).title()[:4]) for k in legs]
        src = re.sub(r"const HL = \[.*?\];", lambda _: "const HL = " + json.dumps(hl) + ";", src, count=1)
        src = re.sub(r"const HS = \[.*?\];", lambda _: "const HS = " + json.dumps(hs) + ";", src, count=1)
        src = re.sub(r"const corrSpecial = .*?\n(\s*)const corr = [^\n]*",
                     lambda m: "const CM = " + json.dumps(cm) + ";\n" + m.group(1) + "const corr = (i, j) => CM[i][j];",
                     src, count=1, flags=re.S)
        src = re.sub(r'(<div role="img" aria-label=")Correlation Heatmap Of [^"]*(" style="[^"]*?repeat\()8,',
                     lambda m: f"{m.group(1)}Correlation Heatmap Of {n} Legs, Last {days} Days{m.group(2)}{n},",
                     src, count=1)
        src = src.replace('hint-placeholder-count="81"', f'hint-placeholder-count="{(n + 1) ** 2}"', 1)
        src = src.replace(">Heatmap Sample<", ">Risk Bar Sample<", 1)
    return src


def _main_book(src):
    book = _jfile(DOCS / "book.json") or {}
    w = {k: float((v or {}).get("weight") or 0) for k, v in (book.get("legs") or {}).items() if isinstance(v, dict)}
    names = sorted(w, key=lambda k: -w[k])
    return _patch_main_book(src, book, _book_corr(names) if names else {})


def _patch_main_live(src, live, usage, root=None, today=None):
    """Main page: token chart, recent runs, funnel, gate fails and the Tokens/Runs Today KPIs from the logs."""
    docs = pathlib.Path(root) if root else DOCS
    day = (today or dt.date.today()).isoformat()
    rows = [r for r in usage or [] if isinstance(r, dict) and r.get("ts")]
    todays = [r for r in rows if str(r["ts"])[:10] == day]

    # Token chart: today's tokens per role, in millions (the template adds runs in flight).
    per = collections.Counter()
    for r in todays:
        per[_ROLE_NAME.get(r.get("role"), _title(str(r.get("role"))))] += _tok(r)
    base = {n: round(v / 1e6, 4) for n, v in per.items() if v}
    src = re.sub(r"const baseTok = \{.*?\};", lambda _: "const baseTok = " + json.dumps(base) + ";", src, count=1)

    # Recent runs: the last ten usage rows, newest first.
    last = sorted(rows, key=lambda r: str(r["ts"]), reverse=True)[:10]
    runs = [[str(r["ts"])[11:16], _title(str(r.get("role") or "?")), _title(str(r.get("model") or "—")),
             int(r.get("input") or 0), int(r.get("output") or 0), int(r.get("cache_read") or 0),
             int(r.get("cache_create") or 0)] for r in last]
    src = re.sub(r"const baseRuns = \[.*?\n    \]\.map\(", lambda _: "const baseRuns = " + json.dumps(runs) + ".map(",
                 src, count=1, flags=re.S)

    # KPIs: today's tokens and runs, and this week's runs.
    week = sum(a["runs"] for a in _week_agg(live, usage).values())
    tok = sum(_tok(r) for r in todays)
    src = src.replace("fmtTok(20.28e6 + liveTok + doneTok)", f"fmtTok({tok} + liveTok + doneTok)")
    src = src.replace(": '36 Runs'", f": '{len(todays)} Runs'", 1)
    src = src.replace("String(36 + s.done.length)", f"String({len(todays)} + s.done.length)")
    src = src.replace("sub: '37 This Week'", f"sub: '{week} This Week'", 1)

    # Funnel and gate fails, from the idea logs and the gate files.
    queue = _jsonl(docs / "ideas" / "queue.jsonl")
    backlog = _jsonl(docs / "ideas" / "backlog.jsonl")
    results = _jsonl(docs / "ideas" / "results.jsonl")
    gates = [g for g in (_jfile(p) for p in sorted((docs / "gates").glob("*.json"))) if isinstance(g, dict)]
    cj = _jfile(docs / "candidates.json") or {}
    cands = [c for c in (cj.get("candidates") if isinstance(cj, dict) else cj) or [] if isinstance(c, dict)]
    book = _jfile(docs / "book.json") or {}
    wl = sorted(([str(k).title(), round(float(v.get("weight") or 0) * 100, 1), round(float(v.get("sharpe") or 0), 2)]
                 for k, v in (book.get("legs") or {}).items() if isinstance(v, dict)), key=lambda x: -x[1])
    if wl:
        src = re.sub(r"const wl = \[\[.*?\]\];", lambda _: "const wl = " + json.dumps(wl) + ";", src, count=1)
    ids = {x.get("id") for x in queue + backlog + results + gates} - {None}
    if ids:
        funnel = [["Ideas Tried", len(ids)],
                  ["Prescreened", len({x.get("id") for x in results + gates} - {None})],
                  ["Full Backtest", len(gates)],
                  ["Passed Gate", sum(str(g.get("verdict", "")).upper() == "PASS" for g in gates)],
                  ["Tester Matched", sum(c.get("status") in ("tester", "demo", "live", "integrated") for c in cands)],
                  ["In The Book", len(book.get("legs") or {})]]
        src = re.sub(r"const funnel = \[\[.*?\]\]\n", lambda _: "const funnel = " + json.dumps(funnel) + "\n", src, count=1)
        # Counts span 1 to hundreds, so the bars use a log scale.
        src = src.replace("(n / 109 * 100).toFixed(1)", f"(Math.log(1 + n) / Math.log({1 + len(ids)}) * 100).toFixed(1)", 1)
        n_pass = funnel[3][1]
        sub = (f"{len(ids)} Ideas · {len(gates) - n_pass} Rejected · {n_pass} Passed · "
               f"{funnel[5][1]} In The Book · {len(gates)} Gate Files")
        src = src.replace("109 Ideas · 95 Rejected · 13 Done · 1 Funded · 91 Gate Files", sub, 1)
        src = src.replace('{{sampleChip}}">Middle Stages Sample<', '{{srcChip}}">Live Counts<', 1)
    first = collections.Counter()
    for g in gates:
        fails = {x.get("gate") for x in g.get("gates") or [] if isinstance(x, dict) and x.get("pass") is False}
        hit = next((k for k in _GATE_ORDER if k in fails), None)
        if hit:
            first[hit] += 1
    if first:
        def gf(m):
            return re.sub(r"\[(\d), ('[^']*'), ('[^']*'), \d+\]",
                          lambda r: f"[{r.group(1)}, {r.group(2)}, {r.group(3)}, {first.get(_GATE_ORDER[int(r.group(1)) - 1], 0)}]",
                          m.group(0))
        src = re.sub(r"const gateFails = \[\[.*?\]\]\n", gf, src, count=1)
        src = src.replace("(f / 33 * 100).toFixed(1)", f"(f / {max(first.values())} * 100).toFixed(1)", 1)
    return src


_PROC_CACHE = {}  # pid -> psutil.Process, so cpu_percent() measures since the last page load
_T16_GUARD = "s.held ? 'Held' : 'Hold And Release'"


def _commit_gb():
    """Commit charge (used, limit) in GB from Windows GetPerformanceInfo, or None off Windows."""
    import ctypes
    from ctypes import wintypes

    class PI(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable", "SystemCache",
            "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + \
            [(n, wintypes.DWORD) for n in ("HandleCount", "ProcessCount", "ThreadCount")]
    pi = PI()
    pi.cb = ctypes.sizeof(pi)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb):
        return None
    return pi.CommitTotal * pi.PageSize / 2 ** 30, pi.CommitLimit * pi.PageSize / 2 ** 30


def _proc_doing(name, exe, cmd):
    """(doing, guard JS) for a watched process, or None to skip it."""
    low = [c.lower() for c in cmd]
    if name == "terminal64.exe":
        folder = pathlib.Path(exe).parent.name
        tail = folder.split(" - ", 1)[1] if " - " in folder else ""
        if tail == "16":
            return "T16 · AurumFunded", _T16_GUARD
        if tail.lower() == "desk":
            return "Desk Terminal", "'Desk Kill'"
        if tail.lower() == "tester":
            return "Strategy Tester", "'Read Only'"
        return ("MT5 " + tail if tail else folder or "MT5"), "'Read Only'"
    if name in ("python.exe", "pythonw.exe"):
        if "-c" in low:
            return None
        if any("hermes" in c for c in low):
            return ("Hermes Gateway" if "gateway" in low else "Hermes"), "'—'"
        mod = low[low.index("-m") + 1] if "-m" in low[:-1] else next((c for c in low[1:] if c.endswith(".py")), "")
        if mod == "desk.dashboard":
            return "Desk Dashboard · State API", "'—'"
        if mod.endswith("dashboard_live.py"):
            return "Live Dashboard Server", "'—'"
        if not mod:
            return None
        return _title(pathlib.PureWindowsPath(mod).stem.replace(".", " ").replace("_", " ")), "'—'"
    if name == "claude.exe":
        if "-p" in low or "--print" in low:
            return None  # headless autopilot runs show as role runs instead
        return "Claude Session", "'—'"
    return None


def _procs():
    """(rows, mem): the running terminals, Python jobs and Claude sessions, and RAM/commit in GB."""
    import psutil
    found, ncpu = [], psutil.cpu_count() or 1
    for p in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline", "memory_info"]):
        try:
            name = (p.info["name"] or "").lower()
            got = _proc_doing(name, p.info["exe"] or "", p.info["cmdline"] or [])
            if not got:
                continue
            pr = _PROC_CACHE.setdefault(p.pid, p)
            found.append({"pid": p.pid, "ppid": p.info["ppid"], "cmd": p.info["cmdline"], "name": _title(name[:-4]),
                          "doing": got[0], "guard": got[1], "cpu": pr.cpu_percent(None) / ncpu,
                          "mb": (p.info["memory_info"].rss if p.info["memory_info"] else 0) / 2 ** 20})
        except (psutil.Error, OSError, ValueError):
            continue
    # A venv launcher and its child do the same job: keep the child, which holds the memory.
    parents = {r["ppid"] for r in found for q in found if q["pid"] == r["ppid"] and q["doing"] == r["doing"]}
    rows = [r for r in found if r["pid"] not in parents]
    for pid in set(_PROC_CACHE) - {r["pid"] for r in found}:
        _PROC_CACHE.pop(pid, None)
    order = {"Terminal64": 0, "Pythonw": 1, "Python": 2, "Claude": 3}
    rows.sort(key=lambda r: (order.get(r["name"], 9), r["pid"]))
    vm = psutil.virtual_memory()
    try:
        commit = _commit_gb()
    except (AttributeError, OSError):
        commit = None
    if not commit:
        sw = psutil.swap_memory()
        commit = ((vm.used + sw.used) / 2 ** 30, (vm.total + sw.total) / 2 ** 30)
    return rows, {"ram": vm.total / 2 ** 30, "commit": commit[0], "limit": commit[1]}


def _patch_main_procs(src, rows, mem):
    """Main page: the process table and the RAM/commit lines from the running machine."""
    if rows:
        js = ",\n      ".join(
            "{ pid: '%d', name: '%s', doing: '%s', cpu: '%.1f', mb: '%d', guard: %s }"
            % (r["pid"], _js(r["name"]), _js(r["doing"]), r["cpu"], round(r["mb"]), r["guard"]) for r in rows)
        src = re.sub(r"const procs = \[\n.*?\n    \]\.concat\(liveRuns",
                     lambda _: "const procs = [\n      " + js + "\n    ].concat(liveRuns", src, count=1, flags=re.S)
    if mem:
        lim = round(mem["limit"], 1)
        src = src.replace("const commit = 25.8 +", f"const commit = {mem['commit']:.1f} +", 1)
        src = src.replace("' Of 29 GB'", f"' Of {lim:g} GB'", 1)
        src = src.replace("(commit / 29 * 100)", f"(commit / {lim:g} * 100)", 1)
        src = src.replace("commit / 29 > 0.9", f"commit / {lim:g} > 0.9", 1)
        src = src.replace("'RAM 7.9 GB · '", f"'RAM {mem['ram']:.1f} GB · '", 1)
    return src


_FEED_TAGS = {"monitor": "Monitor", "watchdog": "Keeper", "terminal_started": "Keeper", "clock_stalled": "Alert",
              "commit_error": "Alert"}
_FEED_ROLE = {"finder": "Finder", "builder": "Builder", "portfolio-manager": "Portfolio", "portfolio": "Portfolio",
              "doctor": "Doctor", "monitor": "Monitor"}


def _git_today():
    """[(HH:MM local, subject)] for today's commits, newest first."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "--since=midnight", "--format=%ad|%s", "--date=format:%H:%M"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [tuple(l.split("|", 1)) for l in out.splitlines() if "|" in l]


def _feed_text(r):
    k = str(r.get("kind") or "")
    if k == "agent_run":
        s = f"{_ROLE_NAME.get(r.get('role'), _title(re.sub('[_-]', ' ', str(r.get('role') or 'agent'))))} Run"
        if r.get("model"):
            s += f" · {_title(r['model'])}"
        if r.get("tokens"):
            s += f" · {int(r['tokens']):,} Tokens"
        return s if r.get("ok", True) else s + " · Failed"
    if k == "monitor":
        n = r.get("issues")
        return f"Monitor: {len(n) if isinstance(n, list) else n or 0} Issues"
    if k.startswith("ticket_"):
        what = {"new": "New", "approve": "Approved", "block": "Blocked"}.get(k[7:], _title(k[7:]))
        s = f"Ticket {what}"
        if r.get("id"):
            s += f" · {r['id']}"
        if k == "ticket_new" and r.get("instrument"):
            s += f" · {r['instrument']} {r.get('side') or ''}".rstrip()
        return s + (f" · {r['why']}" if r.get("why") else "")
    if k == "shadow" and r.get("total_r") is not None:
        return f"Shadow Book · {float(r['total_r']):+.2f}R"
    bits = [_title(k.replace("_", " "))]
    for f in ("pod", "instrument", "name", "did", "why", "events", "last"):
        if r.get(f) not in (None, "", [], {}):
            v = r[f]
            bits.append(str(len(v)) + " Events" if isinstance(v, list) else str(v))
    return " · ".join(bits)


def _patch_main_feed(src, state, usage, git_rows, today=None):
    """Main page: the activity feed from today's agent runs, journal rows and commits, newest first."""
    today = today or dt.date.today()
    rows = []
    for r in usage or []:
        ts = str(r.get("ts") or "")
        if ts[:10] != today.isoformat():
            continue
        role = str(r.get("role") or "")
        txt = f"Run Done · {_title(r.get('model') or role)} · {int(r.get('output') or 0):,} Out"
        rows.append((ts[11:16], _FEED_ROLE.get(role, "Desk"), txt))
    for r in (state or {}).get("journal") or []:
        t = _ts(r.get("t"))
        if t is None:
            continue
        t = t.astimezone()
        if t.date() != today:
            continue
        k = str(r.get("kind") or "")
        tag = "Ticket" if k.startswith("ticket_") else _FEED_TAGS.get(k, "Desk")
        rows.append((t.strftime("%H:%M"), tag, _feed_text(r)))
    for hm, subj in git_rows or []:
        rows.append((hm, "Git", subj))
    if not rows:
        return src
    rows.sort(key=lambda x: x[0], reverse=True)
    js = json.dumps([[t, g, _js(_cut(x, 90))] for t, g, x in rows[:30]], ensure_ascii=False)
    return re.sub(r"const baseFeed = \[\n.*?\n    \]\.map\(\(\[t, src, text\]\)",
                  lambda _: "const baseFeed = " + js[:-1] + "\n    ].map(([t, src, text])", src, count=1, flags=re.S)


# Where a blocked ticket stopped on the 11-stage lane (Pod, Head Trader, Halts, Ticket, Market, Risk, Book, Prop,
# Size, Executor, MT5), read from the gate's reason.
_LANE_WORDS = ((("broker refused",), 10), (("halt", "kill"), 2), (("market", "session", "weekend", "cutoff", "closed"), 4),
               (("book", "correl"), 6), (("prop", "daily", "loss"), 7), (("volume", "size", "lot"), 8), (("risk",), 5))


def _lane_ticket(t, pods):
    st, why = str(t.get("status") or "").lower(), str(t.get("why") or "")
    pn = (pods.get(str(t.get("pod"))) or {}).get("name") or t.get("pod") or "?"
    title = f"{_title(str(pn))} · {_title(str(t.get('side') or ''))} {t.get('instrument') or ''}".strip()
    stage, done, blocked, ask, rej = 1, False, None, False, False
    r = f"{float(t['R']):+.2f} R" if isinstance(t.get("R"), (int, float)) else ""
    note = why or str(t.get("thesis") or "")
    if st == "proposed":
        ask, note = True, "Waits For The Head Trader. Your Sign-Off Stands In For Theirs."
    elif st == "approved":
        stage = 9
    elif st == "placed":
        stage = 10
    elif st in ("open", "closed"):
        stage, done = 10, True
        note = ("Closed " + str(t.get("updated") or "")[5:10] + (" · " + r if r else "") if st == "closed" else "Open On MT5") \
            + (" · " + note if note else "")
    elif st == "rejected":
        blocked, rej, note = 1, True, "Rejected" + (": " + why if why else "")
    elif st in ("cancelled", "expired"):
        blocked, note = 9, _title(st) + " Before It Was Placed" + (": " + why if why else "")
    else:
        low = why.lower()
        blocked = next((n for ws, n in _LANE_WORDS if any(w in low for w in ws)), 5)
        note = "Blocked: " + (why or "no reason given")
    stage = blocked if blocked is not None else stage
    return (f"{{ id: '{_js(str(t.get('id') or '?'))}', title: '{_js(title)}', stage: {stage}, done: {str(done).lower()}, "
            f"blocked: {'null' if blocked is None else blocked}, ask: {str(ask).lower()}, rejected: {str(rej).lower()}, "
            f"loop: false, note: '{_js(_cut(_title(note), 120))}' }}")


def _patch_main_tickets(src, state):
    """Ticket Lane: the six most recently updated desk tickets, each on the stage its status puts it."""
    pods = {str(p.get("name")): p for p in state.get("pods") or []}
    tickets = sorted((t for t in state.get("tickets") or [] if isinstance(t, dict)),
                     key=lambda t: str(t.get("updated") or t.get("created") or ""), reverse=True)[:6]
    rows = [_lane_ticket(t, pods) for t in tickets]
    src = re.sub(r"tickets: \[\n.*?\n      \], tkSeq: \d+",
                 lambda _: "tickets: [" + ", ".join(rows) + f"], tkSeq: {len(rows)}", src, count=1, flags=re.S)
    src = src.replace("filledN / s.tickets.length * 100", "filledN / Math.max(1, s.tickets.length) * 100")
    return src.replace(">Sample Tickets<", ">Live Tickets<" if rows else ">No Tickets Yet<", 1)


def _patch_main_debrief(src, state, root):
    """Debrief card: this week's (Mon-Fri, New York) finished debrief runs, the closed tickets they read, the lessons."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        ny = dt.timezone.utc

    def at(s):
        try:
            d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(ny)
        except ValueError:
            return None
    now = at(state.get("t") or dt.datetime.now(dt.timezone.utc).isoformat()) or dt.datetime.now(ny)
    mon = (now - dt.timedelta(days=now.weekday())).date()
    rows = _jsonl(root / "logs" / "desk" / "state" / "jobs.jsonl")
    last_ev = {r.get("job"): r for r in rows if r.get("job")}
    runs = [at(r.get("queued")) for r in rows if r.get("kind") == "debrief" and r.get("id")
            and (last_ev.get(r["id"]) or {}).get("event") == "done"]
    lessons = [(at(r.get("t")), r) for r in _jsonl(root / "desk" / "memory" / "lessons.jsonl")]
    week = lambda d: d is not None and mon <= d.date() <= now.date() and d.weekday() < 5
    days = {d.date() for d in runs if week(d)} | {d.date() for d, _ in lessons if week(d)}
    due = 5 if now.weekday() >= 5 else now.weekday() + 1
    read = sum(1 for t in state.get("tickets") or [] if str(t.get("status")).lower() == "closed" and week(at(t.get("updated"))))
    n_les = sum(1 for d, _ in lessons if week(d))
    stamps = [d for d in runs if d] + [d for d, _ in lessons if d]
    last = max(stamps).strftime("%a %H:%M NY") if stamps else "None Yet"
    vals = (f"[['Last', '{last}'], ['This Week', '{len(days)} Of {due}'], ['Trades Read', '{read}'], "
            f"['Lessons', '{n_les}']],\n        'Debriefs This Week', '{len(days)} Of {due}', {round(100 * len(days) / due)})")
    return re.sub(r"\[\['Last', 'Fri 17:15 NY'\].*?'Debriefs This Week', '5 Of 5', 100\)", lambda _: vals, src, count=1, flags=re.S)


def _patch_main_podxp(src, state):
    """Pod ranking and cards: each pod's scorekeeper record (P&L, hit rate, R, score; desk/scorekeeper.py) in place
    of the old XP, level and IQ, plus its activity counts (runs, notes, asks) from desk/intel.py."""
    xp = {}
    for p in state.get("pods") or []:
        if not p.get("name"):
            continue
        it, sc = p.get("intel") or {}, p.get("score") or {}
        w, tk, sh, tr = (it.get(k) or {} for k in ("work", "talk", "share", "trading"))
        xp[str(p["name"])] = {"runs": w.get("runs") or 0, "notes": w.get("notes") or 0,
                              "asked": tk.get("asked") or 0, "answered": tk.get("answered") or 0,
                              "shared": sh.get("shared") or 0, "endorsed": sh.get("endorsed") or 0,
                              "cited": sh.get("cited") or 0,
                              "trades": int(sc.get("trades") or 0) if sc else int(tr.get("trades") or 0),
                              "winR": 0, "iqBase": 100, "xp": 0, "iq": 0,
                              "pnl": float(sc.get("pnl") or 0), "hit": sc.get("hit"), "R": float(sc.get("total_R") or 0),
                              "score": float(sc.get("score") or 0)}
    if not xp:
        return src
    src, n = re.subn(r"podXp: \{\n.*?\n\s*\}, podBusy", lambda _: "podXp: " + json.dumps(xp) + ", podBusy", src, count=1, flags=re.S)
    if not n:
        return src
    src = src.replace("const xpTotal = (x) => Math.round(", "const xpTotal = (x) => x.xp != null ? x.xp : Math.round(", 1)
    src = src.replace("const iqOf = (x) => Math.max(", "const iqOf = (x) => x.iq != null ? x.iq : Math.max(", 1)
    usd = "(xp.pnl < 0 ? '−$' : '+$') + Math.abs(xp.pnl || 0).toFixed(2)"
    hitPct = "(xp.hit == null ? 0 : Math.round(xp.hit * 100))"
    for a, b in [
        ("iqBadge: 'Level ' + (lv + 1) + ' · ' + POD_LEVELS[lv][1], iqStyle: pill(POD_TINT[lv][0], POD_TINT[lv][1]),",
         f"iqBadge: xp.trades ? {usd} + ' P&L' : 'No Closed Trades', "
         "iqStyle: !xp.trades ? pill('#F5F5F7', '#6E6E73') : xp.pnl < 0 ? pill('#FDECEC', '#B3261E') : pill('#E9F7EC', '#248A3D'),"),
        ("iqNum: 'IQ ' + iqOf(xp), xpPct,",
         f"iqNum: xp.hit == null ? '— Hit' : Math.round(xp.hit * 100) + '% Hit', xpPct: {hitPct},"),
        ("xpLabel: hi ? nf(tot) + ' / ' + nf(hi) + ' XP' : nf(tot) + ' XP', xpNext: hi ? nf(hi - tot) + ' To Level ' + (lv + 2) : 'Top Level',",
         "xpLabel: xp.trades + (xp.trades === 1 ? ' Trade' : ' Trades') + ' · ' + (xp.R >= 0 ? '+' : '') + Number(xp.R || 0).toFixed(2) + ' R · 8 Weeks', "
         "xpNext: xp.trades ? 'Score ' + (xp.score >= 0 ? '+' : '') + Number(xp.score || 0).toFixed(3) : 'Hit Rate',"),
        ("xpBar: bar(xpPct, '#AF52DE'),", f"xpBar: bar({hitPct}, '#34C759'),"),
        ("'No New XP · '", "'Off · '"),
        ("(fl.n ? '+' + fl.n + ' XP · ' : '') + fl.label", "fl.label"),
        ("'Run Now +' + (10 + 2 * POD_MKTS[id]) + ' XP'", "'Run Now'"),
        ('aria-label="Experience To Next Level"', 'aria-label="Hit Rate"'),
        (">Smartest Pods</span>", ">Pods By Score</span>"),
        ("' Notes · +' + (10 + 2 * k) + ' XP (Simulated)'", "' Notes (Simulated)'"),
        ("' · ' + podName(pid) + ' +5 XP'", "' · ' + podName(pid)"),
        ("' · +' + 8 * k.by.length + ' XP To ' + podName(k.from)", "''"),
        ('{{sampleChip}}">Pod Split Sample<', '{{srcChip}}">Scorekeeper P&amp;L And Hit Rate<'),
        ('{{sampleChip}}">Real Counts 10-31, Simulated Events<', '{{srcChip}}">desk/scorekeeper.py<'),
        ("Values Stay Sample Until The Wiring Reads The Logs.",
         "Pod Values Come From desk/scorekeeper.py (logs/desk/state/scores.json)."),
    ]:
        src = src.replace(a, b, 1)
    src = re.sub(r"if \(lv > podLevel\(xpTotal\(s\.podXp\[id\]\)\)\) events = \[[^\n]*?Reached Level[^\n]*?\.concat\(events\);", "", src, count=1)
    src = re.sub(r"const podRank = POD_IDS\.map\(.*?style: pill\(POD_TINT\[lv\]\[0\], POD_TINT\[lv\]\[1\]\) \};",
                 lambda _: ("const podRank = POD_IDS.map((id) => [id, s.podXp[id] || {}]).sort((a, b) => (b[1].trades ? 1 : 0) - (a[1].trades ? 1 : 0) "
                            "|| (b[1].score || 0) - (a[1].score || 0) || (b[1].pnl || 0) - (a[1].pnl || 0)).map(([id, x], i) => {\n"
                            "      return { label: (i + 1) + ' ' + podName(id), val: x.trades ? 'Score ' + (x.score >= 0 ? '+' : '') + Number(x.score || 0).toFixed(3) "
                            "+ ' · ' + (x.hit == null ? '—' : Math.round(x.hit * 100) + '%') + ' Hit' : 'No Trades', "
                            "style: !x.trades ? pill('#F5F5F7', '#6E6E73') : x.score < 0 ? pill('#FDECEC', '#B3261E') : pill('#E9F7EC', '#248A3D') };"),
                 src, count=1, flags=re.S)
    return re.sub(r"Pod Intelligence Comes From Each Pod’s Real Record.*?(?=</p>)",
                  lambda _: ("Each Pod Is Scored On Its Own Closed Trades Over The Last 8 Weeks, From desk/scorekeeper.py "
                             "(logs/desk/state/scores.json): P&amp;L, Hit Rate, R And A Score = Its R Per Trade Minus The Rest Of The Desk’s, "
                             "Shrunk By n/(n+20), So A Pod Is Fully Judged From Its 20th Trade. Runs, Notes And Asks Come From desk/intel.py."),
                  src, count=1, flags=re.S)


def patch_page(src, i, live, usage, positions, label, extra=None):
    src = src.replace(">Sample Data<", f">{label}<")
    src = src.replace("background: #FFF4E5; color: #8A4B00", "background: #E8F5EC; color: #1E7B34")
    src = _stop_sim(src)
    if i == 0:
        src = _patch_roles(src, live, _week_agg(live, usage))
        src = _safe(_patch_scores, src)
        src = _patch_talk(src, live)
        src = _patch_positions(src, positions)
        src = src.replace("t: 'Sample'", "t: 'Live'")
        src = _wire_kill(src)
        state = (extra or {}).get("state")
        if isinstance(state, dict):
            src = _safe(_patch_desk, src, state, positions)
            src = _safe(_patch_gate, src, state)
            src = _safe(_patch_pods, src, state)
            src = _safe(_patch_main_tickets, src, state)
            src = _safe(_patch_main_debrief, src, state, ROOT)
            src = _safe(_patch_main_podxp, src, state)
            src = _safe(lambda s: _patch_main_feed(s, state, usage, _git_today()), src)
            src = _safe(_patch_main_status, src, state)
            src = _patch_sources(src)
        src = _safe(_patch_alerts, src, state if isinstance(state, dict) else {}, ROOT)
        src = _safe(_patch_queue, src, (extra or {}).get("queue"))
        src = _safe(_patch_main_live, src, live, usage)
        src = _safe(lambda s: _patch_main_procs(s, *_procs()), src)
        t16 = _t16_log()
        src = _safe(lambda s: _patch_main_funded(s, t16, _deployed_funded()), src)
        src = _safe(lambda s: _patch_main_rules(s, t16, _t16_preset()), src)
        src = _safe(lambda s: _patch_main_legs(s, t16), src)
        src = _safe(lambda s: _patch_main_preset(s, _t16_loaded()), src)
        src = _safe(lambda s: _patch_main_fidelity(s, _demo_week()), src)
        src = _safe(_main_book, src)
    elif i == 1 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_pods_page, src, extra["state"])
        src = _safe(_patch_pods_scores, src, extra["state"])
    elif i == 2 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_eas_page, src, extra["state"], positions)
    elif i == 3 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_processes_page, src, extra["state"], live)
    elif i == 4 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_research_page, src, extra["state"], live)
    elif i == 5 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_controls_page, src, extra["state"], positions)
    elif i == 6 and live:
        src = _safe(_patch_agents_page, src, live, usage)
    if isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_phase, src, extra["state"])
    vers, dep = _ea_versions(), _funded_deploy()
    src = _safe(lambda s: _patch_versions(s, dep and dep["ver"], vers.get("AurumHydra"), vers.get("AurumFunded"), dep), src)
    return src


# The app shell (owner 2026-11-01: "feel like an actual dashboard, not an html file"). The export's own template is a
# design canvas: seven fixed 1440 px boards stacked on a padded beige page, 32,000 px tall, and its nav tabs are links
# to X.dc.html files that do not exist inside the bundle. The shell shows one page at a time, full window, each
# scrolling inside its own frame; a tab click (or the Aurum logo) switches pages by hash (#main, #agents, ...), so back
# and forward work, a reload stays on the tab, and Alt+1..7 jumps in nav order. The loader still mounts every frame from
# its about:blank#<uuid> marker.
PAGES = [("main", "Main.dc.html", "Command Center"), ("pods", "Pods.dc.html", "Pods"), ("eas", "EAs.dc.html", "EAs"),
         ("processes", "Processes.dc.html", "Processes"), ("research", "Research.dc.html", "Research"),
         ("controls", "Controls.dc.html", "Controls"), ("agents", "Agents.dc.html", "Agents")]
NAV = ["main", "agents", "pods", "eas", "processes", "research", "controls"]
_SHELL_JS = r"""
(function () {
  var R = __ROUTES__, NAV = __NAV__, frames = {}, byFile = {};
  R.forEach(function (r) { frames[r.id] = document.getElementById('f-' + r.id); byFile[r.file.toLowerCase()] = r.id; });
  function cur() { var h = (location.hash || '').replace(/^#\/?/, '').toLowerCase(); return frames[h] ? h : 'main'; }
  function show() {
    var id = cur();
    R.forEach(function (r) {
      var on = r.id === id, f = frames[r.id];
      f.classList.toggle('on', on); f.setAttribute('aria-hidden', on ? 'false' : 'true'); f.tabIndex = on ? 0 : -1;
      if (on) { document.title = 'Aurum · ' + r.label; try { f.contentWindow.focus(); } catch (e) {} }
    });
    try { localStorage.setItem('aurum.tab', id); } catch (e) {}
  }
  function go(id) { if (!frames[id]) return; if (cur() !== id || !location.hash) location.hash = id; else show(); }
  function keys(e) {
    if (!e.altKey || e.ctrlKey || e.metaKey) return;
    var n = parseInt(e.key, 10);
    if (n >= 1 && n <= NAV.length) { e.preventDefault(); go(NAV[n - 1]); }
  }
  function hook(f) {
    var d; try { d = f.contentDocument; } catch (e) { return; }
    if (!d || d.__aurum || !/^blob:/.test(String(d.URL))) return;
    d.__aurum = 1;
    d.addEventListener('click', function (e) {
      var a = e.target && e.target.closest && e.target.closest('a[href]');
      if (!a) return;
      var id = byFile[(a.getAttribute('href') || '').split('#')[0].split('?')[0].split('/').pop().toLowerCase()];
      if (!id) return;
      e.preventDefault(); e.stopPropagation(); go(id);
    }, true);
    d.addEventListener('keydown', keys, true);
    f.classList.add('ready');
  }
  function hookAll() { R.forEach(function (r) { hook(frames[r.id]); }); }
  R.forEach(function (r) { frames[r.id].addEventListener('load', hookAll); });
  setInterval(hookAll, 400);
  window.addEventListener('hashchange', show);
  window.addEventListener('keydown', keys, true);
  if (!location.hash) {
    var s = null; try { s = localStorage.getItem('aurum.tab'); } catch (e) {}
    if (s && frames[s]) history.replaceState(null, '', '#' + s);
  }
  show(); hookAll();
})();
"""


def _shell_template(order, heres=None):
    """The shell HTML for the bundle's outer template. order: the bundle's page uuids; heres: page index -> the
    page's own HERE file name where it names one (so a re-export that moves pages still routes right)."""
    heres = heres or {}
    known = {f.lower(): (pid, f, lab) for pid, f, lab in PAGES}
    routes, seen = [], set()
    for i, uid in enumerate(order):
        pid, f, lab = known.get(str(heres.get(i, "")).lower()) or (PAGES[i] if i < len(PAGES) else (f"p{i}", "", f"Page {i + 1}"))
        if pid in seen:
            pid = f"p{i}"
        seen.add(pid)
        routes.append({"id": pid, "file": f, "label": lab, "uuid": uid})
    frames = "\n".join(f'<iframe id="f-{r["id"]}" src="about:blank#{r["uuid"]}" title="Aurum {html.escape(r["label"])}" '
                       f'loading="eager" aria-hidden="true" tabindex="-1"></iframe>' for r in routes)
    nav = [n for n in NAV if any(r["id"] == n for r in routes)]
    js = _SHELL_JS.replace("__ROUTES__", json.dumps(routes)).replace("__NAV__", json.dumps(nav))
    return ('<!DOCTYPE html>\n<html lang="en"><head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="color-scheme" content="light">\n<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n<title>Aurum · Command Center</title>\n<style>\n'
            'html,body{margin:0;height:100%;overflow:hidden;background:#fbfbfd}\n'
            'iframe{position:fixed;inset:0;width:100%;height:100%;border:0;background:#fbfbfd;'
            'visibility:hidden;pointer-events:none}\n'
            'iframe.on{visibility:visible;pointer-events:auto}\n'
            '</style>\n</head>\n<body>\n' + frames + '\n<script>' + js + '</script>\n</body></html>')


def _patch_shell(outer, order, heres=None):
    """Swap the bundle's outer canvas template for the app shell."""
    tm = _TEMPLATE.search(outer)
    if not tm:
        return outer
    enc = json.dumps(_shell_template(order, heres), ensure_ascii=False).replace("</", "<\\u002F")
    return outer[:tm.start(2)] + enc + outer[tm.end(2):]


_HERE = re.compile(r"HERE\s*=\s*'([A-Za-z]+\.dc\.html)'")


def build(bundle_path, live, usage, positions, extra=None):
    """The bundle bytes with live data in. live: dashboard/live.js as a dict; usage: usage.jsonl rows; positions: the
    desk's open positions (broker dicts) or None."""
    live = live if isinstance(live, dict) else {}
    outer = bundle_path.read_text(encoding="utf-8")
    m = _MANIFEST.search(outer)
    man = json.loads(m.group(2))
    order = json.loads(_ORDER.search(outer).group(1))
    try:
        snap = dt.datetime.fromisoformat(str(live.get("generated_iso"))[:19])
    except ValueError:
        snap = dt.datetime.now()
    label = "Live Snapshot · " + snap.strftime("%a %d %b %H:%M")
    heres = {}
    for i, uid in enumerate(order):
        e = man[uid]
        raw = base64.b64decode(e["data"])
        inner = (gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")
        hm = _HERE.search(inner)
        if hm:
            heres[i] = hm.group(1)
        tm = _TEMPLATE.search(inner)
        if not tm:
            continue
        src = patch_page(json.loads(tm.group(2)), i, live, usage, positions, label, extra)
        enc = json.dumps(src, ensure_ascii=False).replace("</", "<\\u002F")
        inner = inner[:tm.start(2)] + enc + inner[tm.end(2):]
        b = inner.encode("utf-8")
        e["data"] = base64.b64encode(gzip.compress(b, 6) if e.get("compressed") else b).decode("ascii")
    man_js = json.dumps(man, separators=(",", ":"))
    outer = outer[:m.start(2)] + man_js + outer[m.end(2):]
    try:
        outer = _patch_shell(outer, order, heres)
    except Exception:  # the canvas still works; never lose the page over the shell
        pass
    return outer.encode("utf-8")


def cached(bundle_path, get_inputs):
    """build() at most once every TTL seconds; get_inputs() returns (live, usage, positions)."""
    now = time.time()
    if _CACHE["body"] is None or now - _CACHE["t"] > TTL:
        _CACHE["body"] = build(bundle_path, *get_inputs())
        _CACHE["t"] = now
    return _CACHE["body"]


def forget():
    """Drop the cached page, so the next load shows a switch just changed."""
    _CACHE["body"] = None
