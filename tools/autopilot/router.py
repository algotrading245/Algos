# The model router (owner 2026-10-18): one switch picks the provider for every agent run, and each role maps to a
# tier that each provider names a model for. run-agent.ps1 asks this script which binary, model and limits to use, so
# no routing rule lives in PowerShell.
#
#   python tools/autopilot/router.py show
#   python tools/autopilot/router.py use qwen                 # every role on Qwen
#   python tools/autopilot/router.py use claude               # every role back on Claude
#   python tools/autopilot/router.py use claude --role orchestrator    # one role apart from the switch
#   python tools/autopilot/router.py use qwen --role orchestrator --model qwen3-coder-plus
#   python tools/autopilot/router.py use qwen --tier judge --model qwen3.8-max   # one tier's model
#   python tools/autopilot/router.py clear --role orchestrator           # drop an override
#   python tools/autopilot/router.py resolve --role tester [--tier code] [--model opus]
#       -> one JSON line for run-agent.ps1: {"provider","model","tier","turns","minutes","agent","settings"}
#          provider "none" when no provider can run (all backed off, no key, not installed): code-only mode
#   python tools/autopilot/router.py available                # {"any": true|false, "first", "providers": {...}}
#   python tools/autopilot/router.py backoff --provider claude [--minutes 60] [--stdin]   # after a limit
#   python tools/autopilot/router.py backoff --provider claude --clear                    # limit lifted early
#
# No secret is ever stored here: the Qwen key lives in ~/.qwen/settings.json, outside the repo.
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTER = HERE / "router.json"
REPO = HERE.parents[1]
QWEN_SETTINGS = "~/.qwen/settings.json"


def load():
    return json.loads(ROUTER.read_text(encoding="utf-8-sig"))


def save(r):
    ROUTER.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def roles(r):
    """The role entries of router.json (its "roles" object also carries an "about" string)."""
    return {k: v for k, v in r["roles"].items() if isinstance(v, dict)}


def resolve(r, role, tier=None, model=None):
    """The run's provider, model and limits. A literal model name wins; then a per-role override; then the switch."""
    known = roles(r)
    if role not in known:
        sys.exit(f"unknown role '{role}' (known: {', '.join(sorted(known))})")
    cfg = known[role]
    ov = (r.get("overrides") or {}).get(role)
    ov = ov if isinstance(ov, dict) else {}
    provider = ov.get("provider") or r["provider"]
    if provider not in r["providers"]:
        sys.exit(f"router.json names provider '{provider}', which it does not define")
    t = tier or ov.get("tier") or cfg["tier"]

    # A provider that cannot run (backed off after a limit, no key, not installed) is not a reason for the pipeline
    # to idle: walk the fallback order and say so (run-agent.ps1 logs it). None left: provider "none", code-only.
    wanted = provider
    skipped = []
    for cand in chain(r, wanted):
        why = unavailable(r, cand)
        if not why:
            provider = cand
            break
        skipped.append(f"{cand} {why}")
    else:
        return {"provider": "none", "cli": None, "model": None, "tier": t, "turns": cfg.get("turns", 40),
                "minutes": cfg.get("minutes", 60), "fell_back": "; ".join(skipped), "agent": None,
                "agent_file": None, "args": [], "settings": None, "base_url": None, "key_env": []}
    fell_back = "; ".join(skipped) if provider != wanted else None
    p = r["providers"][provider]
    if model and (provider == wanted or model in p["tiers"]):
        # A tier name of the active provider is accepted as a shortcut ("--model judge"). A literal model of the
        # provider we fell back from ("opus") means nothing here, so the tier decides instead.
        m = p["tiers"].get(model, model)
    else:
        m = ov.get("model") if (ov.get("provider") or r["provider"]) == provider else None
        m = m or p["tiers"].get(t)
        if not m:
            sys.exit(f"provider '{provider}' has no model for tier '{t}'")
    cli = cli_of(r, provider)
    return {
        "provider": provider,
        "cli": cli,
        "model": m,
        "tier": t,
        "turns": cfg.get("turns", 40),
        "minutes": cfg.get("minutes", 60),
        "fell_back": fell_back,
        # Claude runs four roles as a subagent definition (--agent) and the other two on the tier model alone. Qwen
        # has no --agent flag, so run-agent.ps1 inlines the same definition into the prompt instead.
        "agent": cfg.get("claude_agent") if cli == "claude" else None,
        "agent_file": (cfg.get("agent_file") or None) if cli != "claude" else None,
        "args": p.get("args") or [],
        "settings": ("tools/autopilot/settings.json" if cli == "claude" else ".qwen/settings.json"),
        # An extra OpenAI-compatible provider run through Qwen Code: run-agent.ps1 points OPENAI_BASE_URL at base_url
        # and copies its key from the first key_env variable set (never from an argument).
        "base_url": p.get("base_url"),
        "key_env": list(p.get("key_env") or []),
    }


# ---------------------------------------------------------------- fallback and per-provider back-off

BACKOFF = REPO / "logs" / "autopilot" / "provider-backoff.json"


def cli_of(r, provider):
    """Which CLI drives a provider: claude, or qwen (Qwen Code, also for any other OpenAI-compatible API)."""
    return (r["providers"].get(provider) or {}).get("cli") or provider


def chain(r, first):
    """The provider to try first, then the rest of the fallback order."""
    order = list((r.get("fallback") or {}).get("order") or [])
    return [first] + [p for p in order if p != first and p in r["providers"]]


def read_backoff():
    try:
        b = json.loads(BACKOFF.read_text(encoding="utf-8-sig"))
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def backed_off(provider):
    """The back-off entry of a provider while it lasts, else None."""
    e = read_backoff().get(provider)
    try:
        if e and datetime.fromisoformat(e["until"]) > datetime.now():
            return e
    except Exception:
        pass
    return None


def installed(cli):
    if cli == "claude":
        npm = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        return npm.exists() or bool(shutil.which("claude.exe") or shutil.which("claude"))
    if cli == "qwen":
        entry = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@qwen-code" / "qwen-code" / "cli-entry.js"
        return entry.exists() and bool(shutil.which("node"))
    return False


def has_key(r, provider):
    p = r["providers"][provider]
    if cli_of(r, provider) == "claude":
        return True                      # Claude Code signs in by itself (subscription login)
    names = p.get("key_env")
    if not names:
        return qwen_key()
    return any(str(os.environ.get(n, "")).strip() for n in names) or user_env_has(names)


def user_env_has(names):
    """A Windows user environment variable set after this process started (setx) counts too."""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            for n in names:
                try:
                    if str(winreg.QueryValueEx(k, n)[0]).strip():
                        return True
                except OSError:
                    pass
    except OSError:
        pass
    return False


def unavailable(r, provider):
    """Why a provider cannot take a run now, or None when it can."""
    e = backed_off(provider)
    if e:
        return f"backed off until {e['until']} ({e.get('reason', 'limit')})"
    if not installed(cli_of(r, provider)):
        return "is not installed"
    if not has_key(r, provider):
        return "has no API key"
    return None


RESET_AT = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
RESET_EPOCH = re.compile(r"limit reached\|(\d{10})")


def reset_time(text, minutes):
    """When a limit ends: the time the CLI names ("resets 3pm", "...limit reached|<epoch>"), else now + minutes.
    Never more than 7 days and never less than 5 minutes away."""
    now = datetime.now()
    until = now + timedelta(minutes=minutes)
    m = RESET_EPOCH.search(text or "")
    if m:
        until = datetime.fromtimestamp(int(m.group(1)))
    else:
        m = RESET_AT.search(text or "")
        if m:
            h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
            if ap == "pm" and h < 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            if h < 24 and mi < 60:
                until = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                if until <= now:
                    until += timedelta(days=1)
    until += timedelta(minutes=2)
    return min(max(until, now + timedelta(minutes=5)), now + timedelta(days=7))


def cmd_backoff(r, provider, minutes, reason, text, clear):
    b = read_backoff()
    if clear:
        b.pop(provider, None)
        print(f"{provider}: back-off cleared")
    else:
        if provider not in r["providers"]:
            sys.exit(f"unknown provider '{provider}'")
        mins = minutes or int((r.get("fallback") or {}).get("backoff_minutes") or 60)
        until = reset_time(text, mins) if text else datetime.now() + timedelta(minutes=mins)
        b[provider] = {"until": until.isoformat(timespec="seconds"), "reason": (reason or "limit")[:160],
                       "set": datetime.now().isoformat(timespec="seconds")}
        print(f"{provider}: backed off until {b[provider]['until']}")
    BACKOFF.parent.mkdir(parents=True, exist_ok=True)
    BACKOFF.write_text(json.dumps(b, indent=2) + "\n", encoding="utf-8")


def cmd_available(r):
    """One JSON line: is any provider able to take a run, and why not for each that cannot."""
    order = chain(r, r["provider"])
    state = {p: (unavailable(r, p) or "ok") for p in order}
    print(json.dumps({"any": any(v == "ok" for v in state.values()),
                      "first": next((p for p in order if state[p] == "ok"), None), "providers": state}))


def cmd_show(r):
    print(f"provider switch: {r['provider']}")
    for name, p in r["providers"].items():
        tiers = ", ".join(f"{k}={v}" for k, v in p["tiers"].items())
        print(f"  {name:7s} {tiers}")
    print("roles:")
    for role in roles(r):
        got = resolve(r, role)
        ov = (r.get("overrides") or {}).get(role)
        mark = "  (override)" if isinstance(ov, dict) and ov else ""
        if got.get("fell_back"):
            mark += f"  [FALLBACK: {got['fell_back']}]"
        print(f"  {role:13s} tier {got['tier']:8s} -> {got['provider']} {str(got['model'] or 'code-only'):18s} "
              f"{got['turns']:3d} turns / {got['minutes']:3d} min{mark}")
    if r["provider"] == "qwen" or any(isinstance(v, dict) and v.get("provider") == "qwen"
                                      for v in (r.get("overrides") or {}).values()):
        print(f"qwen api key in {QWEN_SETTINGS}: "
              f"{'found' if qwen_key() else 'MISSING (runs fall back to claude until it is set)'}")
    order = chain(r, r["provider"])
    print("fallback order: " + " -> ".join(order) + " -> code-only")
    for name in order:
        why = unavailable(r, name)
        print(f"  {name:7s} {why or 'ok'}")


KEY_VARS = ("DASHSCOPE_API_KEY", "BAILIAN_TOKEN_PLAN_API_KEY", "BAILIAN_CODING_PLAN_API_KEY", "OPENAI_API_KEY")


def qwen_key():
    """True when a Qwen/OpenAI-compatible credential is reachable: a real environment variable, or the "env" block
    of the user-level ~/.qwen/settings.json (Qwen Code loads it as a fallback), or the deprecated
    security.auth.apiKey. Never prints the value."""
    for name in KEY_VARS:
        if str(os.environ.get(name, "")).strip():
            return True
    try:
        s = json.loads(Path(os.path.expanduser(QWEN_SETTINGS)).read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    if not isinstance(s, dict):
        return False
    env = s.get("env")
    if isinstance(env, dict):
        for name in KEY_VARS:
            v = str(env.get(name, "")).strip()
            # A placeholder ("sk-...", "<your key>", "$DASHSCOPE_API_KEY") is not a key.
            if v and not v.startswith("$") and "<" not in v and v not in ("sk-...", "changeme", "REPLACE_ME"):
                return True
    auth = ((s.get("security") or {}).get("auth") or {})
    if str(auth.get("apiKey", "")).strip():
        return True
    return False


def cmd_use(r, provider, role, tier, model):
    if provider not in r["providers"]:
        sys.exit(f"unknown provider '{provider}' (known: {', '.join(r['providers'])})")
    if tier and model:
        r["providers"][provider].setdefault("tiers", {})[tier] = model
        print(f"{provider} tier {tier} -> {model}")
    if role:
        if role not in roles(r):
            sys.exit(f"unknown role '{role}' (known: {', '.join(sorted(roles(r)))})")
        ov = r.setdefault("overrides", {})
        entry = ov.setdefault(role, {})
        entry["provider"] = provider
        if model and not tier:
            entry["model"] = model
        print(f"role {role} -> {provider}" + (f" {model}" if model and not tier else ""))
    elif not (tier and model):
        r["provider"] = provider
        print(f"provider switch -> {provider} (every role without an override)")
    save(r)
    cmd_show(r)


# ---------------------------------------------------------------- the Qwen credential, without it passing through an agent
#
# The key is never an argument (it would land in the shell's history and in an agent's transcript): qwen-key reads it
# from a hidden prompt, or from stdin with --stdin. It is stored only in ~/.qwen/settings.json, outside the repo, and
# is printed masked at most.

ENDPOINTS = [
    ("Token Plan, global (Singapore)", "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
     "BAILIAN_TOKEN_PLAN_API_KEY"),
    ("Token Plan, China (Beijing)", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
     "BAILIAN_TOKEN_PLAN_API_KEY"),
    ("Coding Plan, international", "https://coding-intl.dashscope.aliyuncs.com/v1", "BAILIAN_CODING_PLAN_API_KEY"),
    ("Coding Plan, China", "https://coding.dashscope.aliyuncs.com/v1", "BAILIAN_CODING_PLAN_API_KEY"),
    ("Standard API key, international", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    ("Standard API key, China", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    ("Standard API key, US", "https://dashscope-us.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
]
PROJECT_QWEN_SETTINGS = REPO / ".qwen" / "settings.json"


def mask(key):
    return f"...{key[-4:]}" if key and len(key) > 4 else "(none)"


def probe(base_url, key, model):
    """One minimal chat completion against base_url. Returns (ok, message); the message never holds the key."""
    import urllib.error
    import urllib.request
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            d = json.loads(resp.read().decode("utf-8", "replace"))
        return True, f"HTTP 200, answered as model {d.get('model') or model}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").replace(key, "<key>")[:220]
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e).replace(key, '<key>')[:220]}"


def write_user_env(var, key):
    """Stores one environment variable in ~/.qwen/settings.json, keeping whatever else is there."""
    path = Path(os.path.expanduser(QWEN_SETTINGS))
    try:
        s = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(s, dict):
            s = {}
    except Exception:
        s = {}
    env = s.setdefault("env", {})
    for name in KEY_VARS:          # one credential, one name: drop the others so no stale copy is left behind
        if name != var:
            env.pop(name, None)
    env[var] = key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    return path


def write_project_route(model_id, base_url, env_var):
    """Points the project's modelProviders route for model_id at the endpoint that answered. No secret is written."""
    try:
        s = json.loads(PROJECT_QWEN_SETTINGS.read_text(encoding="utf-8-sig"))
    except Exception:
        return "the project's .qwen/settings.json is unreadable; its route was not updated"
    routes = ((s.get("modelProviders") or {}).get("openai")) or []
    hit = next((m for m in routes if isinstance(m, dict) and m.get("id") == model_id), None)
    if hit is None:
        hit = {"id": model_id}
        routes.append(hit)
        s.setdefault("modelProviders", {})["openai"] = routes
    changed = hit.get("baseUrl") != base_url or hit.get("envKey") != env_var
    hit["baseUrl"], hit["envKey"] = base_url, env_var
    if changed:
        PROJECT_QWEN_SETTINGS.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    return ("route updated" if changed else "route already correct") + f": {model_id} -> {base_url} (env {env_var})"


def cmd_qwen_key(a):
    path = Path(os.path.expanduser(QWEN_SETTINGS))
    if a.show:
        try:
            env = (json.loads(path.read_text(encoding="utf-8-sig")) or {}).get("env") or {}
        except Exception:
            env = {}
        found = [(k, v) for k, v in env.items() if k in KEY_VARS and str(v).strip()]
        print(f"{path}: " + (", ".join(f"{k} = {mask(str(v))}" for k, v in found) if found else "no key stored"))
        return
    if a.clear:
        try:
            s = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            s = {}
        env = s.get("env") or {}
        for name in KEY_VARS:
            env.pop(name, None)
        if env:
            s["env"] = env
        else:
            s.pop("env", None)
        path.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
        print(f"removed the stored key from {path}")
        return

    if a.stdin:
        key = sys.stdin.readline().strip()
    else:
        import getpass
        key = getpass.getpass("Paste the Alibaba Model Studio API key (input is hidden, it is not stored anywhere "
                              "else): ").strip()
    if not key:
        sys.exit("no key read")

    if a.base_url and a.var:
        var, base = a.var, a.base_url
        ok, msg = probe(base, key, a.model)
        print(f"{base}: {msg}")
        if not ok:
            sys.exit("that endpoint refused the key; nothing was stored")
    else:
        print(f"trying {a.model} against the Alibaba Model Studio endpoints (one 1-token call each):")
        var = base = None
        for name, url, env_var in ENDPOINTS:
            ok, msg = probe(url, key, a.model)
            print(f"  {'OK  ' if ok else 'no  '} {name:34s} {msg.splitlines()[0][:110]}")
            if ok and not var:
                var, base = env_var, url
        if not var:
            sys.exit("no endpoint accepted the key with that model id; nothing was stored. "
                     "Try --model with the id your plan serves, or set --var and --base-url yourself.")
    stored = write_user_env(var, key)
    print(f"stored {var} = {mask(key)} in {stored} (outside the repo; not committed)")
    print(write_project_route(a.model, base, var))
    print("now check: python tools/autopilot/router.py show")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    for name in ("use", "clear"):
        p = sub.add_parser(name)
        if name == "use":
            p.add_argument("provider", choices=["claude", "qwen"])
        p.add_argument("--role")
        p.add_argument("--tier")
        p.add_argument("--model")
    p = sub.add_parser("resolve")
    p.add_argument("--role", required=True)
    p.add_argument("--tier")
    p.add_argument("--model")
    p = sub.add_parser("qwen-key", help="store the Qwen API key in ~/.qwen/settings.json (hidden prompt, never an "
                                        "argument) after finding the endpoint that serves the model")
    p.add_argument("--model", default="qwen3.8-max", help="model id to test and to point the route at")
    p.add_argument("--var", help="store under this env var name instead of probing (needs --base-url)")
    p.add_argument("--base-url", help="use this endpoint instead of probing (needs --var)")
    p.add_argument("--stdin", action="store_true", help="read the key from stdin instead of a hidden prompt")
    p.add_argument("--show", action="store_true", help="print which key is stored, masked")
    p.add_argument("--clear", action="store_true", help="remove the stored key")
    sub.add_parser("available", help="can any provider take a run now (JSON)")
    p = sub.add_parser("backoff", help="hold a provider back after a limit, so runs fall back down the order")
    p.add_argument("--provider", required=True)
    p.add_argument("--minutes", type=int, help="default: fallback.backoff_minutes, or the reset time --stdin names")
    p.add_argument("--reason")
    p.add_argument("--stdin", action="store_true", help="read the CLI's limit message from stdin for its reset time")
    p.add_argument("--clear", action="store_true", help="lift the back-off now")
    a = ap.parse_args()
    r = load()

    if a.cmd == "show":
        cmd_show(r)
    elif a.cmd == "use":
        cmd_use(r, a.provider, a.role, a.tier, a.model)
    elif a.cmd == "clear":
        if not a.role:
            sys.exit("clear needs --role")
        (r.get("overrides") or {}).pop(a.role, None)
        save(r)
        print(f"override for {a.role} dropped")
        cmd_show(r)
    elif a.cmd == "resolve":
        print(json.dumps(resolve(r, a.role, tier=a.tier, model=a.model)))
    elif a.cmd == "qwen-key":
        cmd_qwen_key(a)
    elif a.cmd == "available":
        cmd_available(r)
    elif a.cmd == "backoff":
        text = sys.stdin.read() if a.stdin else ""
        cmd_backoff(r, a.provider, a.minutes, a.reason, text, a.clear)


if __name__ == "__main__":
    main()
