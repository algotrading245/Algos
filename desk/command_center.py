"""The Aurum Command Center page (desk/dashboard/command_center.html) with the desk's live data patched in.

The file is a bundle: an outer page whose manifest holds one gzipped inner page per screen (Main, Pods, EAs,
Processes, Research, Controls, Agents). Each inner page carries its HTML as a JSON string in a template script.
build() decodes each screen, patches it, and packs it back, so the design stays exactly as uploaded.

Live on every screen: the "Live Snapshot" label and chip, and the sample simulation is stopped (the clock still ticks).
Live on Main: role runs, tokens, last run and task (this budget week), the agent talk feed from the relay log, the
desk's open positions, and the kill button, which POSTs /api/kill. With extra = {"state": /api/state, "queue": queue
rows}: the desk card (equity, balance, P/L, margin, last tick), drawdown and daily loss, the live-gate checks, the pod
rows, the alerts (needs_you) and the idea queue. Live on Pods (from the same state): each pod's allocation, work and
talk counts (so XP, level and IQ), hit rate, P/L and closed trades, the board posts, the tickets and the KPI row; the
pod briefs, what each pod knows and the rules are still design text. Live on EAs: equity, balance, the kill floor,
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
    return re.sub(r"const queue = \[.*?\n    \];", lambda _: "const queue = [" + ", ".join(out) + "];", src, count=1, flags=re.S)


def _patch_alerts(src, state):
    rows = [[f"live-{i}", "amber" if str(n.get("level")).upper() == "WARN" else "red", "Desk",
             _js(str(n.get("what") or ""))[:90], "Now"] for i, n in enumerate(state.get("needs_you") or [])]
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


def _patch_pods_page(src, state):
    pods = {str(p.get("name")): p for p in state.get("pods") or []}
    eq = float((state.get("limits") or {}).get("equity") or 0)
    for pid, p in pods.items():
        it, sc = p.get("intel") or {}, p.get("score") or {}
        w, tk, sh, tr = it.get("work") or {}, it.get("talk") or {}, it.get("share") or {}, it.get("trading") or {}
        trades = int(sc.get("trades") or tr.get("trades") or 0)
        c = (f"c: {{ runs: {int(w.get('runs') or 0)}, notes: {int(w.get('notes') or 0)}, asked: {int(tk.get('asked') or 0)}, "
             f"answered: {int(tk.get('answered') or 0)}, shared: {int(sh.get('shared') or 0)}, endorsed: {int(sh.get('endorsed') or 0)}, "
             f"cited: {int(sh.get('cited') or 0)}, trades: {trades} }}")
        wk = float(sc.get("pnl") or 0) / eq * 100 if eq else 0.0
        tail = (f"wk: {wk:.2f}, bench: 0, below: 0, closed: {trades}, followed: '{float(sc.get('total_R') or 0):+.2f} R'"
                + (", idle: true" if trades == 0 else ""))

        def one(m, c=c, tail=tail, alloc=round(float(p.get("share") or 0) * 100), hit=float(tr.get("hit") or sc.get("hit") or 0)):
            s = re.sub(r"alloc: \d+", f"alloc: {alloc}", m.group(0), count=1)
            s = re.sub(r"c: \{[^}]*\}", lambda _: c, s, count=1)
            s = re.sub(r"winR: [\d.]+", f"winR: {hit:.2f}", s, count=1)
            s = re.sub(r" probation: '[^']*',", "", s, count=1)
            return re.sub(r"wk: [-\d.]+, bench: [-\d.]+, below: \d+, closed: \d+, followed: '[^']*'(, idle: true)?(, quiet: \d+)?",
                          lambda _: tail, s, count=1)
        src = re.sub(rf"\{{ id: '{re.escape(pid)}', name: [^\n]*", one, src, count=1)
    src = src.replace("const nameOf = (id) => PODS.find((p) => p.id === id).name;",
                      "const nameOf = (id) => ((PODS.find((p) => p.id === id) || {}).name || String(id));", 1)

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
    paused = set((state.get("alloc") or {}).get("paused") or [])
    sw = []
    for p in state.get("pods") or []:
        n = str(p.get("name") or "")
        if not n:
            continue
        lv = ((p.get("intel") or {}).get("level") or {})
        meta = f"Level {lv.get('n', '?')} · {lv.get('name', '')}".rstrip(" ·")
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
        st = "Paused" if halted or int(r.get("fails_in_row") or 0) >= 3 else "Running"
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
        sw.append({"id": eid, "group": "Demo Legs", "name": nm, "what": what, "meta": meta, "state": desk_st})
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
        live_t = [t for t in tickets if t.get("status") in ("open", "live", "filled", "approved")]
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
                ["Trades Today", "Across All Pods", n_today, 12, ""],
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
    log = [{"at": _hhmm(j.get("t")), "what": _title(str(j.get("kind") or "").replace("_", " ")),
            "who": _cut(" · ".join(x for x in (_title(str(j.get("by") or "")), str(j.get("why") or "")) if x), 80),
            "state": "Cancelled" if "block" in str(j.get("kind")) else "Applied"} for j in pick]
    if log:
        src = re.sub(r"const LOG0 = \[.*?\n\];", lambda _: "const LOG0 = " + json.dumps(log, ensure_ascii=False) + ";",
                     src, count=1, flags=re.S)
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


def patch_page(src, i, live, usage, positions, label, extra=None):
    src = src.replace(">Sample Data<", f">{label}<")
    src = src.replace("background: #FFF4E5; color: #8A4B00", "background: #E8F5EC; color: #1E7B34")
    src = _stop_sim(src)
    if i == 0:
        src = _patch_roles(src, live, _week_agg(live, usage))
        src = _patch_talk(src, live)
        src = _patch_positions(src, positions)
        src = src.replace("t: 'Sample'", "t: 'Live'")
        src = _wire_kill(src)
        state = (extra or {}).get("state")
        if isinstance(state, dict):
            src = _safe(_patch_desk, src, state, positions)
            src = _safe(_patch_gate, src, state)
            src = _safe(_patch_pods, src, state)
            src = _safe(_patch_alerts, src, state)
            src = _patch_sources(src)
        src = _safe(_patch_queue, src, (extra or {}).get("queue"))
    elif i == 1 and isinstance((extra or {}).get("state"), dict):
        src = _safe(_patch_pods_page, src, extra["state"])
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
    return src


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
    for i, uid in enumerate(order):
        e = man[uid]
        raw = base64.b64decode(e["data"])
        inner = (gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")
        tm = _TEMPLATE.search(inner)
        if not tm:
            continue
        src = patch_page(json.loads(tm.group(2)), i, live, usage, positions, label, extra)
        enc = json.dumps(src, ensure_ascii=False).replace("</", "<\\u002F")
        inner = inner[:tm.start(2)] + enc + inner[tm.end(2):]
        b = inner.encode("utf-8")
        e["data"] = base64.b64encode(gzip.compress(b, 6) if e.get("compressed") else b).decode("ascii")
    man_js = json.dumps(man, separators=(",", ":"))
    return (outer[:m.start(2)] + man_js + outer[m.end(2):]).encode("utf-8")


def cached(bundle_path, get_inputs):
    """build() at most once every TTL seconds; get_inputs() returns (live, usage, positions)."""
    now = time.time()
    if _CACHE["body"] is None or now - _CACHE["t"] > TTL:
        _CACHE["body"] = build(bundle_path, *get_inputs())
        _CACHE["t"] = now
    return _CACHE["body"]
