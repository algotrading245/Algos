"""The Aurum Command Center page (desk/dashboard/command_center.html) with the desk's live data patched in.

The file is a bundle: an outer page whose manifest holds one gzipped inner page per screen (Main, Pods, EAs,
Processes, Research, Controls, Agents). Each inner page carries its HTML as a JSON string in a template script.
build() decodes each screen, patches it, and packs it back, so the design stays exactly as uploaded.

Live on every screen: the "Live Snapshot" label and chip, and the sample simulation is stopped (the clock still ticks).
Live on Main: role runs, tokens, last run and task (this budget week), the agent talk feed from the relay log, the
desk's open positions, and the kill button, which POSTs /api/kill. The rest is still the design's sample content.
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


def patch_page(src, i, live, usage, positions, label):
    src = src.replace(">Sample Data<", f">{label}<")
    src = src.replace("background: #FFF4E5; color: #8A4B00", "background: #E8F5EC; color: #1E7B34")
    src = _stop_sim(src)
    if i == 0:
        src = _patch_roles(src, live, _week_agg(live, usage))
        src = _patch_talk(src, live)
        src = _patch_positions(src, positions)
        src = src.replace("t: 'Sample'", "t: 'Live'")
        src = _wire_kill(src)
    return src


def build(bundle_path, live, usage, positions):
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
        src = patch_page(json.loads(tm.group(2)), i, live, usage, positions, label)
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
