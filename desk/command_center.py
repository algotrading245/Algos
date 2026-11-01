"""The Aurum Command Center page (desk/dashboard/command_center.html) with the desk's live data patched in.

The file is a bundle: an outer page whose manifest holds one gzipped inner page per screen (Main, Pods, EAs,
Processes, Research, Controls, Agents). Each inner page carries its HTML as a JSON string in a template script.
build() decodes each screen, patches it, and packs it back, so the design stays exactly as uploaded.

Live on every screen: the "Live Snapshot" label and chip, and the sample simulation is stopped (the clock still ticks).
Live on Main: role runs, tokens, last run and task (this budget week), the agent talk feed from the relay log, the
desk's open positions, and the kill button, which POSTs /api/kill. With extra = {"state": /api/state, "queue": queue
rows}: the desk card (equity, balance, P/L, margin, last tick), drawdown and daily loss, the live-gate checks, the pod
rows, the alerts (needs_you) and the idea queue. The rest is still the design's sample content.
"""
import base64
import collections
import datetime as dt
import gzip
import json
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
