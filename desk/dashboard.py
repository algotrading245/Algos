"""The desk's live dashboard: a local web page that refreshes every second.

python -m desk.dashboard [--host 127.0.0.1] [--port 8765]     then open http://127.0.0.1:8765

GET  /            the Aurum Command Center (desk/dashboard/command_center.html, live data patched in by
                  desk/command_center.py); falls back to the classic page if that build fails
GET  /classic     the classic page (desk/dashboard/index.html)
GET  /api/state   everything the page shows, as JSON
GET  /api/live    dashboard/live.js (window.AURUM_LIVE, rewritten about every second) as JSON, plus "age_s"
GET  /api/aurum   dashboard/data.js (window.AURUM) as JSON, slimmed: runs cut to the latest 40, ledger and gates
                  summarised, demo log tailed; cached by file mtime
GET  /api/queue   docs/ideas/queue.jsonl (latest 60 rows) and docs/gaps.json
GET  /api/usage   logs/autopilot/usage.jsonl, latest 300 rows
POST /api/kill    the kill switch, the same as `python -m desk.cli kill "why"`; the clock closes every desk position on
                  its next pass. Only from this PC (127.0.0.1), with the X-Desk: kill header and no foreign Origin.
                  Resume stays owner-only on the command line.

The dashboard reads the desk terminal live (account and positions only, never an order call), and only when that
terminal is already running, so it never launches one; otherwise it shows the clock's last heartbeat. It writes nothing
but the KILL file.
"""
import argparse
import collections
import datetime as dt
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from desk import allowance, clocks, command_center, controls, jobs, journal, live_gate, memory, news, paths, phase, risk_gate, runner, scorekeeper, systematic, tickets

PAGE = paths.DESK / "dashboard" / "index.html"
BUNDLE = paths.DESK / "dashboard" / "command_center.html"
# The nav's Aurum mark (a cube), gold on dark, as the browser tab icon.
FAVICON = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" '
           b'fill="#1d1d1f"/><g fill="none" stroke="#e8b84a" stroke-width="2" stroke-linecap="round" '
           b'stroke-linejoin="round"><path d="M12 4l7 4v8l-7 4-7-4V8z"/><path d="M12 12l7-4M12 12v8M12 12L5 8"/>'
           b'</g></svg>')
LIVE_JS = paths.ROOT / "dashboard" / "live.js"
DATA_JS = paths.ROOT / "dashboard" / "data.js"
QUEUE = paths.ROOT / "docs" / "ideas" / "queue.jsonl"
GAPS = paths.ROOT / "docs" / "gaps.json"
USAGE = paths.ROOT / "logs" / "autopilot" / "usage.jsonl"
_JS_CACHE = {}


def read_js(path):
    """Parse a `window.X = {...};` file to a dict; cached by mtime. Returns {"error":..} when missing or broken."""
    try:
        mt = path.stat().st_mtime
        hit = _JS_CACHE.get(path)
        if hit and hit[0] == mt:
            return hit[1], mt
        txt = path.read_text(encoding="utf-8")
        data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        _JS_CACHE[path] = (mt, data)
        return data, mt
    except Exception as e:  # noqa: BLE001 - the page shows the error as "no data"
        return {"error": f"{type(e).__name__}: {e}"}, None


def slim_aurum(d):
    """data.js is ~1.2 MB; keep what the page draws."""
    if "error" in d:
        return d
    o = dict(d)
    o["runs"] = (d.get("runs") or [])[-40:]
    led = d.get("ledger") or {}
    keep = ("id", "name", "source", "status", "step", "ea", "summary", "stress_sharpe", "tag")
    o["ledger"] = {"about": led.get("about"),
                   "candidates": [{k: c.get(k) for k in keep if k in c} for c in led.get("candidates", [])],
                   "rejected": led.get("rejected", [])}
    o["gates"] = {k: {"id": g.get("id"), "when": g.get("when"), "verdict": g.get("verdict"),
                      "gates": [{"gate": x.get("gate"), "pass": x.get("pass"), "figure": x.get("figure")}
                                for x in g.get("gates", [])]} for k, g in (d.get("gates") or {}).items()}
    demo = dict(d.get("demo") or {})
    demo["log"] = (demo.get("log") or "")[-3000:]
    o["demo"] = demo
    return o


def read_tail_jsonl(path, n):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return None
    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except ValueError:
            pass
    return rows
SLOW_TTL = 5          # seconds the file-heavy sections are cached
LIVE_TTL = 1          # seconds a live MT5 read is reused
PROC_TTL = 10         # seconds between checks that the desk terminal is running
SERIES = 3600         # equity samples kept in memory (an hour at one a second)


def _try(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:  # one broken section must not blank the page
        return {"error": f"{type(e).__name__}: {e}"}


def _age_min(iso, t):
    try:
        return round((t - dt.datetime.fromisoformat(iso)).total_seconds() / 60, 1)
    except (TypeError, ValueError):
        return None


# ---- live MT5 reads --------------------------------------------------------------------------------------------------

class Live:
    """Read-only view of the desk terminal, shared by every request."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.broker = None
        self.why = ""
        self.last = None
        self.last_t = 0.0
        self.proc_ok = False
        self.proc_t = 0.0
        self.retry_t = 0.0
        self.series = collections.deque(maxlen=SERIES)

    def _terminal_running(self):
        if time.time() - self.proc_t < PROC_TTL:
            return self.proc_ok
        self.proc_t = time.time()
        want = str(Path(self.cfg["terminal"]["path"]).resolve()).lower()
        try:
            import psutil
            self.proc_ok = any((p.info.get("exe") or "").lower() == want
                               for p in psutil.process_iter(["exe"]))
        except Exception as e:
            self.why, self.proc_ok = f"process check failed: {e}", False
        return self.proc_ok

    def _connect(self):
        if self.broker is not None and self.broker.connected():
            return True
        if time.time() < self.retry_t:
            return False
        self.broker = None
        if os.environ.get("AURUM_DESK_DRY"):
            self.why = "dry mode"
            return False
        if not self._terminal_running():
            self.why = "desk terminal not running"
            self.retry_t = time.time() + PROC_TTL
            return False
        from desk import broker
        b = broker.MT5Broker(self.cfg)
        if not b.connected():
            self.why = b.why or "not connected"
            self.retry_t = time.time() + 15
            return False
        self.broker, self.why = b, ""
        return True

    def read(self):
        with self.lock:
            if self.last is not None and time.time() - self.last_t < LIVE_TTL:
                return self.last
            out = {"source": "heartbeat", "why": None, "account": None, "positions": None}
            try:
                if self._connect():
                    acc, pos = self.broker.account(), self.broker.positions()
                    if acc is not None:
                        out.update(source="mt5", account=acc, positions=pos)
                        self.series.append([clocks.now().isoformat(timespec="seconds"), acc.get("equity")])
                    else:
                        self.broker, self.why = None, "account read failed"
            except Exception as e:
                self.broker, self.why = None, f"{type(e).__name__}: {e}"
                self.retry_t = time.time() + 15
            if out["source"] != "mt5":
                hb = (paths.read_json(paths.STATE / "heartbeat.json", {}) or {}).get("summary") or {}
                out["why"] = self.why
                out["account"] = {k: hb.get(k) for k in ("equity", "balance")} if hb else None
            out["t"] = clocks.now().isoformat(timespec="seconds")
            self.last, self.last_t = out, time.time()
            return out


# ---- the state the page shows ----------------------------------------------------------------------------------------

def _intel(cfg):
    """state/intel.json, which the runner rewrites after every job; computed here when no job has run yet."""
    from desk import intel
    got = paths.read_json(intel.FILE, {}) or {}
    if not got.get("pods"):
        got = {"pods": intel.all_profiles(cfg), "talk": memory.talk(40), "knowledge": memory.knowledge()[-40:]}
    return got


def _pods(cfg, st, iq=None):
    iq = iq or {}
    alloc = paths.read_json(phase.ALLOC, {}) or {}
    shares, paused = alloc.get("token_shares") or alloc.get("shares") or {}, set(alloc.get("paused") or [])
    sc = (paths.read_json(scorekeeper.SCORES, {}) or {}).get("pods", {})
    active = set(phase.pods_active(cfg, st.get("phase") if isinstance(st, dict) else None))
    out = []
    for name, p in cfg["pods"].items():
        out.append({"name": name, "active": name in active, "opens_phase": p.get("phase"),
                    "enabled": p.get("enabled", True), "paused": name in paused,
                    "base_share": p.get("base_share"), "share": shares.get(name, p.get("base_share")),
                    "tilt": _try(phase.tilt, name), "score": sc.get(name),
                    "tokens": {"spent": runner.spent(name, cfg, key=name), "budget": runner.pod_budget(name, cfg)},
                    "intel": iq.get(name)})
    return out


def _watch(rows):
    """The watcher's fires and the wakes it was refused, newest first, one row per thing that fired."""
    out = []
    for r in rows:
        if r.get("kind") == "watch_fired":
            for w in r.get("watch") or []:
                what = {"level": lambda: f"{w.get('dir')} through {w.get('level')} ({w.get('from')} to {w.get('price')})",
                        "edge": lambda: f"{w.get('edge')} {'/'.join(s.get('side', '') for s in w.get('signals') or [])}",
                        "shock": lambda: f"bar range {w.get('range_atr')} x ATR"}.get(w.get("kind"), lambda: "")()
                out.append({"t": r.get("t"), "pod": r.get("pod"), "kind": w.get("kind"), "market": w.get("market"),
                            "what": what})
        elif r.get("kind") == "wake_refused":
            out.append({"t": r.get("t"), "pod": r.get("pod"), "kind": "refused", "market": "", "what": r.get("why")})
    return out[-30:][::-1]


def _budgets(cfg):
    return [{"group": g, "spent": runner.spent(g, cfg, key=g), "limit": allowance.pool(cfg) if g == "pod" else lim}
            for g, lim in cfg.get("budgets", {}).items() if not g.startswith("_") and g in cfg.get("models", {})]


def _brief(v):
    keep = ("id", "pod", "instrument", "side", "status", "risk_pct", "entry", "stop", "targets", "thesis", "why",
            "created", "updated", "pnl", "R", "by")
    out = {k: v[k] for k in keep if k in v}
    if isinstance(out.get("thesis"), str):
        out["thesis"] = out["thesis"][:240]
    return out


def _tickets(state):
    rows = sorted(state.values(), key=lambda v: v.get("updated", ""), reverse=True)
    return [_brief(v) for v in rows[:20]]


def _r_series(state):
    done = sorted((v for v in state.values() if v.get("status") == "closed" and v.get("R") is not None),
                  key=lambda v: v.get("updated", ""))
    total, out = 0.0, []
    for v in done:
        total += float(v["R"])
        out.append([v.get("updated"), round(total, 3), v.get("pod")])
    return out


def _news(t):
    rows = [{"t": e.get("t"), "ccy": e.get("ccy"), "title": e.get("title"), "forecast": e.get("forecast"),
             "previous": e.get("previous")} for e in news.upcoming(48, t)]
    return {"stale": news.stale(t), "events": rows[:14]}


def _alert_head():
    f = paths.INBOX / "ALERT.md"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8", errors="replace")
    parts = text.split("\n# ")
    head = parts[0].lstrip("# ").strip()
    lines = head.splitlines()
    return {"title": lines[0] if lines else "", "items": [ln[2:].replace("**", "") for ln in lines if ln.startswith("- ")],
            "t": dt.datetime.fromtimestamp(f.stat().st_mtime, clocks.UTC).isoformat(timespec="seconds")}


def _phase(st):
    s = phase.state() or {}
    d0 = s.get("day0")
    out = {"day0": d0, "phase": st.get("phase") if isinstance(st, dict) else None, "day": phase.days_in(),
           "profile": st.get("profile") if isinstance(st, dict) else None,
           "risk_scale": st.get("risk_scale") if isinstance(st, dict) else None, "live_day0": s.get("live_day0")}
    if d0 and s.get("phase3_at"):
        out["steps"] = [{"phase": 1, "from": dt.datetime.fromisoformat(d0).date().isoformat(),
                         "what": "systematic + fxmacro at 0.25x, normal rules"},
                        {"phase": 3, "from": phase.phase3_start(s).date().isoformat(),
                         "what": "owner started everything: all pods, 1.0x, prop-firm rules, the live gate counting"},
                        {"phase": 4, "from": None, "what": "live, only on the owner's yes"}]
    elif d0:
        t0 = dt.datetime.fromisoformat(d0)
        out["steps"] = [{"phase": 1, "from": t0.date().isoformat(), "what": "systematic + fxmacro at 0.25x, normal rules"},
                        {"phase": 2, "from": (t0 + dt.timedelta(days=14)).date().isoformat(),
                         "what": "all pods at 0.5x, prop-firm rules (owner switches to prop_10k)"},
                        {"phase": 3, "from": (t0 + dt.timedelta(days=28)).date().isoformat(),
                         "what": "1.0x, the live gate starts counting"},
                        {"phase": 4, "from": None, "what": "live, only on the owner's yes"}]
    return out


def _schedule(t):
    sch = paths.read_json(paths.STATE / "schedule.json", {}) or {}
    return [{"name": k, "ran": v.get("ran"), "age_min": _age_min(v.get("ran"), t)} for k, v in sch.items()]


def _runner():
    r = paths.read_json(jobs.RUNNER, {}) or {}
    folded = sorted(jobs.fold().values(), key=lambda j: j.get("queued", ""), reverse=True)[:12]
    keep = ("id", "kind", "name", "pod", "pods", "queued", "status", "why", "started", "done")
    return {"runner": r, "busy": _try(jobs.runner_busy),
            "pending": [{"id": j["id"], "kind": j["kind"], "pod": j.get("pod")} for j in jobs.pending()],
            "recent": [{k: j[k] for k in keep if k in j} for j in folded]}


def _edges():
    s = paths.read_json(systematic.FILE, {}) or {}
    sh = paths.read_json(systematic.SHADOW, {}) or {}
    return {"armed": s.get("armed", []), "shadow_total_r": sh.get("total_r"), "shadow_since": sh.get("since")}


def _journal(rows):
    out = []
    for r in rows[-40:][::-1]:
        r = dict(r)
        for k, v in list(r.items()):
            if isinstance(v, str) and len(v) > 300:
                r[k] = v[:300] + "..."
        out.append(r)
    return out


def _alerts(st, live, mon, alert, t, nws):
    """What needs the owner, worst first: level ALERT or WARN, and what."""
    out = []
    if isinstance(st, dict):
        if st.get("halt"):
            out.append({"level": "HALT", "what": f"Trading halted: {st['halt']}"})
        hb = st.get("heartbeat") or {}
        age = _age_min(hb.get("t"), t)
        if age is None or age > 3:
            out.append({"level": "ALERT", "what": f"Clock heartbeat is {age} min old (it beats every minute)"})
        elif hb.get("ok") is False:
            out.append({"level": "ALERT", "what": f"Last clock pass failed: {hb.get('why')}"})
    acc = (live or {}).get("account") or {}
    if live.get("source") == "mt5" and (acc.get("trade_allowed") is False or acc.get("terminal_algo") is False):
        out.append({"level": "ALERT", "what": "Algo Trading is off on the desk terminal (or the account forbids trading)"})
    for i in (mon or {}).get("issues") or []:
        out.append({"level": "ALERT", "what": i if isinstance(i, str) else json.dumps(i, default=str)})
    if alert and _age_min(alert.get("t"), t) is not None and _age_min(alert["t"], t) < 120:
        for i in alert.get("items", []):
            out.append({"level": "WARN", "what": f"{i} (inbox/ALERT.md, {alert['title']})"})
    if isinstance(nws, dict) and nws.get("stale"):
        out.append({"level": "WARN", "what": f"News: {nws['stale']}; entries are blocked until it refreshes"})
    return out


class State:
    def __init__(self, cfg=None):
        self.cfg = cfg or paths.config()
        self.live = Live(self.cfg)
        self.slow, self.slow_t = None, 0.0
        self.lock = threading.Lock()

    def _slow(self, st, t):
        with self.lock:
            if self.slow is not None and time.time() - self.slow_t < SLOW_TTL:
                return self.slow
            cfg = paths.config()
            tk = _try(tickets.fold)
            tk = tk if isinstance(tk, dict) and "error" not in tk else {}
            rows = _try(journal.recent, None, 2)
            rows = rows if isinstance(rows, list) else []
            iq = _try(_intel, cfg)
            iq = iq if isinstance(iq, dict) and "error" not in iq else {}
            self.slow = {
                "pods": _try(_pods, cfg, st, iq.get("pods")), "budgets": _try(_budgets, cfg),
                "allowance": _try(allowance.status, cfg, t),
                "watch": _try(_watch, rows),
                "talk": (iq.get("talk") or [])[::-1], "knowledge": (iq.get("knowledge") or [])[::-1],
                "level_ups": [r for r in rows if r.get("kind") == "level_up"][-10:][::-1],
                "scores": _try(paths.read_json, scorekeeper.SCORES, {}),
                "alloc": _try(paths.read_json, phase.ALLOC, {}),
                "board": _try(lambda: memory.board(15)[::-1]),
                "journal": _journal(rows),
                "agents": [r for r in rows if r.get("kind") in ("agent_run", "agent_skipped")][-20:][::-1],
                "tickets": _try(_tickets, tk), "r_series": _try(_r_series, tk),
                "news": _try(_news, t), "monitor": _try(paths.read_json, paths.STATE / "monitor.json", {}),
                "alert_file": _try(_alert_head), "runner": _try(_runner), "edges": _try(_edges),
                "live_gate": _try(live_gate.evaluate), "phase": _try(_phase, st), "schedule": _try(_schedule, t),
            }
            self.slow_t = time.time()
            return self.slow

    def build(self):
        from desk import cli
        t = clocks.now()
        st = _try(cli.status)
        live = self.live.read()
        out = {"t": t.isoformat(timespec="seconds"), "status": st,
               "limits": _try(paths.read_json, paths.STATE / "limits.json", {}),
               "live": live, "equity_series": list(self.live.series)}
        out.update(self._slow(st, t))
        mon = out["monitor"] if isinstance(out["monitor"], dict) else {}
        alert = out["alert_file"] if isinstance(out["alert_file"], dict) and "error" not in out["alert_file"] else None
        out["needs_you"] = _try(_alerts, st, live, mon, alert, t, out["news"])
        return out


# ---- the server ------------------------------------------------------------------------------------------------------

LOCAL = ("127.0.0.1", "::1")


class Handler(BaseHTTPRequestHandler):
    state = None  # set by serve()

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if not ctype.startswith("image") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _cc_inputs(self):
        try:
            positions = (self.state.live.read() or {}).get("positions")
        except Exception:
            positions = None
        try:
            state = self.state.build()
        except Exception:
            state = None
        extra = {"state": state, "queue": read_tail_jsonl(QUEUE, 60) or []}
        return read_js(LIVE_JS)[0], read_tail_jsonl(USAGE, 5000) or [], positions, extra

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                return self._send(200, command_center.cached(BUNDLE, self._cc_inputs), "text/html")
            except Exception:
                return self._send(200, PAGE.read_bytes(), "text/html")
        if path == "/classic":
            return self._send(200, PAGE.read_bytes(), "text/html")
        if path in ("/favicon.svg", "/favicon.ico"):
            return self._send(200, FAVICON, "image/svg+xml")
        if path == "/api/state":
            return self._send(200, self.state.build())
        if path == "/api/live":
            d, mt = read_js(LIVE_JS)
            return self._send(200, {**d, "file_age_s": None if mt is None else round(time.time() - mt, 1)})
        if path == "/api/aurum":
            d, mt = read_js(DATA_JS)
            return self._send(200, {**slim_aurum(d), "file_age_s": None if mt is None else round(time.time() - mt, 1)})
        if path == "/api/queue":
            try:
                gaps = json.loads(GAPS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                gaps = None
            return self._send(200, {"queue": read_tail_jsonl(QUEUE, 60), "gaps": gaps})
        if path == "/api/usage":
            return self._send(200, {"rows": read_tail_jsonl(USAGE, 300)})
        return self._send(404, {"error": "not found"})

    def _local_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = origin.split("//", 1)[-1].split(":")[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 4096)) or b"{}") if n else {}
        except ValueError:
            body = {}
        return body if isinstance(body, dict) else {}

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/control":
            # The Controls switches: same guard as the kill, its own header value.
            if self.client_address[0] not in LOCAL or self.headers.get("X-Desk") != "control" or not self._local_origin():
                return self._send(403, {"ok": False, "error": "switches only from this PC's dashboard"})
            b = self._body()
            try:
                st = controls.apply(b.get("kind"), b.get("target"), b.get("action"), b.get("why"))
            except controls.Refused as e:
                return self._send(400, {"ok": False, "error": str(e)})
            except Exception as e:
                return self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})
            self.state.slow = None
            command_center.forget()
            return self._send(200, {"ok": True, "status": st})
        if path != "/api/kill":
            return self._send(404, {"error": "not found"})
        if self.client_address[0] not in LOCAL or self.headers.get("X-Desk") != "kill" or not self._local_origin():
            return self._send(403, {"ok": False, "error": "kill only from this PC's dashboard"})
        body = self._body()
        why = (str(body.get("why") or "").strip() or "kill switch on the dashboard")[:200]
        try:
            risk_gate.kill(why, by="owner")
        except Exception as e:
            return self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})
        self.state.slow = None
        return self._send(200, {"ok": True, "halt": risk_gate.halted()})


class Server(ThreadingHTTPServer):
    allow_reuse_address = sys.platform != "win32"  # on Windows reuse lets a second copy bind the same port
    daemon_threads = True


def server(host="127.0.0.1", port=8765, state=None):
    Handler.state = state or State()
    return Server((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m desk.dashboard")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        srv = server(a.host, a.port)
    except OSError as e:  # already running (the logon task) or the port is taken
        print(f"dashboard not started: {e}")
        return 1
    print(f"desk dashboard on http://{a.host}:{a.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
