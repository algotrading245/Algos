"""Live view of the autopilot agents on this PC: http://127.0.0.1:8765

    python tools/live_server.py [--port 8765]

Tails logs/autopilot/events/*.jsonl (written by tools/autopilot/run-agent.ps1 from `claude -p --output-format
stream-json`) and pushes each event to the browser over Server-Sent Events within ~30 ms of it being written.
Shows what an agent says, the tool calls it makes with their results, and the reasoning text the model exposes;
hidden chain of thought is not available, only what the stream carries.  Read-only: it never starts, stops or
changes an agent.  Binds to 127.0.0.1 only.
"""
import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "autopilot"
EVENTS = LOGS / "events"
PAGE = Path(__file__).resolve().parent / "live_page.html"
MAX_TEXT = 6000
PRIVATE = re.compile(r"(?i)(login|account|password|passwd|api[_-]?key|token)\W{0,3}\s*[:=]?\s*\S+")


def clip(s, n=MAX_TEXT):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = PRIVATE.sub(lambda m: m.group(1) + " [hidden]", s)
    return s if len(s) <= n else s[:n] + f"... [{len(s) - n} more chars]"


def digest(ev, replay):
    """One stream-json event -> a small dict for the page, or None when it carries nothing to show."""
    t = ev.get("type")
    if t == "stream_event":
        e = ev.get("event", {})
        et = e.get("type")
        if et == "content_block_delta" and not replay:
            d = e.get("delta", {})
            dt = d.get("type")
            if dt == "text_delta":
                return {"k": "delta", "ch": "text", "s": d.get("text", ""), "i": e.get("index")}
            if dt == "thinking_delta":
                return {"k": "delta", "ch": "thinking", "s": d.get("thinking", ""), "i": e.get("index")}
            if dt == "input_json_delta":
                return {"k": "delta", "ch": "tool", "s": d.get("partial_json", ""), "i": e.get("index")}
        if et == "content_block_start" and not replay:
            b = e.get("content_block", {})
            return {"k": "start", "ch": b.get("type"), "name": b.get("name"), "i": e.get("index")}
        if et == "message_start" and not replay:
            return {"k": "turn", "model": e.get("message", {}).get("model")}
        return None
    if t == "assistant":
        out = []
        for c in ev.get("message", {}).get("content", []):
            ct = c.get("type")
            if ct == "text":
                out.append({"k": "text", "s": clip(c.get("text", ""))})
            elif ct == "thinking":
                out.append({"k": "thinking", "s": clip(c.get("thinking", ""))})
            elif ct == "tool_use":
                out.append({"k": "tool", "id": c.get("id"), "name": c.get("name"), "input": clip(c.get("input", {}), 3000)})
        return {"k": "msg", "parts": out, "model": ev.get("message", {}).get("model")} if out else None
    if t == "user":
        out = []
        c = ev.get("message", {}).get("content", [])
        for b in c if isinstance(c, list) else []:
            if b.get("type") == "tool_result":
                cc = b.get("content")
                if isinstance(cc, list):
                    cc = "\n".join(x.get("text", "") for x in cc if isinstance(x, dict))
                out.append({"k": "result", "id": b.get("tool_use_id"), "s": clip(cc or ""), "err": bool(b.get("is_error"))})
        return {"k": "msg", "parts": out} if out else None
    if t == "system":
        st = ev.get("subtype")
        if st == "init":
            return {"k": "init", "model": ev.get("model"), "tools": len(ev.get("tools", [])), "perm": ev.get("permissionMode")}
        if st in ("status", "api_retry", "compact_boundary"):
            return {"k": "sys", "s": clip(ev.get("status") or st)}
        return None
    if t == "result":
        return {"k": "done", "ok": not ev.get("is_error"), "turns": ev.get("num_turns"), "ms": ev.get("duration_ms"),
                "cost": ev.get("total_cost_usd"), "usage": ev.get("usage"), "stop": ev.get("terminal_reason"),
                "denied": len(ev.get("permission_denials") or [])}
    if t == "rate_limit_event":
        return {"k": "sys", "s": "rate limit info: " + clip(ev.get("rate_limit_info", ev), 300)}
    return None


def run_id(path):
    stem = path.stem  # 20261017-164500_tester
    return stem, stem.split("_", 1)[1]


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def state():
    roles = ["orchestrator", "tester", "monitor", "researcher", "scanner", "fidelity"]
    now = time.time()
    agents = {}
    for r in roles:
        last = read_json(LOGS / f"last-{r}.json") or {}
        files = sorted(EVENTS.glob(f"*_{r}.jsonl")) if EVENTS.exists() else []
        live = bool(files) and now - files[-1].stat().st_mtime < 20 and "done" not in tail_kinds(files[-1])
        agents[r] = {"last": last, "runs": len(files), "live": live, "latest": files[-1].stem if files else None}
    hold = LOGS / "hold-terminal"
    q = read_json(ROOT / "docs" / "autopilot" / "queue.json") or {}
    return {"now": now, "paused": (LOGS / "PAUSE").exists(), "hold": read_json(hold) if hold.exists() else None,
            "relay": read_json(LOGS / "relay.json"), "agents": agents,
            "jobs": [{k: j.get(k) for k in ("id", "status", "title", "note")} for j in q.get("jobs", [])][-12:]}


def tail_kinds(path, n=20000):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, path.stat().st_size - n))
            return "done" if b'"duration_ms"' in f.read() else ""
    except OSError:
        return ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif self.path.startswith("/api/state"):
            self.send(200, "application/json", json.dumps(state()).encode())
        elif self.path.startswith("/stream"):
            self.stream()
        else:
            self.send(404, "text/plain", b"not found")

    def stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        pos = {}      # file -> bytes already sent
        buf = {}      # file -> partial last line
        replayed = set()
        last_beat = last_state = 0.0
        try:
            while True:
                files = sorted(EVENTS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)[-8:] if EVENTS.exists() else []
                for f in files:
                    rid, role = run_id(f)
                    first = f not in pos
                    size = f.stat().st_size
                    if first:
                        pos[f], buf[f] = 0, b""
                    if size <= pos[f]:
                        continue
                    with open(f, "rb") as fh:
                        fh.seek(pos[f])
                        data = fh.read(size - pos[f])
                    pos[f] = size
                    lines = (buf[f] + data).split(b"\n")
                    buf[f] = lines.pop()
                    replay = first and f != files[-1] or (first and time.time() - f.stat().st_mtime > 30)
                    out = []
                    for ln in lines:
                        try:
                            d = digest(json.loads(ln), replay)
                        except Exception:
                            d = None
                        if d:
                            d.update(run=rid, role=role, t=time.time())
                            out.append(d)
                    if out:
                        self.wfile.write(("data: " + json.dumps({"batch": out}, ensure_ascii=False) + "\n\n").encode())
                        self.wfile.flush()
                now = time.time()
                if now - last_state > 2:
                    self.wfile.write(("event: state\ndata: " + json.dumps(state()) + "\n\n").encode())
                    self.wfile.flush()
                    last_state = now
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.daemon_threads = True
    print(f"live view: http://127.0.0.1:{a.port}  (events: {EVENTS})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
