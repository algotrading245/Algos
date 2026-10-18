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
#
# No secret is ever stored here: the Qwen key lives in ~/.qwen/settings.json, outside the repo.
import argparse
import json
import os
import sys
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

    # A provider that cannot authenticate is not a reason for the pipeline to idle: fall back to the other one and
    # say so (run-agent.ps1 logs it). Putting the key in ~/.qwen/settings.json switches the runs to Qwen at once.
    fell_back = None
    if provider == "qwen" and not qwen_key():
        fell_back = "qwen has no API key (see ~/.qwen/settings.json)"
        provider = "claude" if "claude" in r["providers"] else provider
    p = r["providers"][provider]
    if model:
        # A tier name of the active provider is accepted as a shortcut ("--model judge").
        m = p["tiers"].get(model, model)
    else:
        m = ov.get("model") if (ov.get("provider") or r["provider"]) == provider else None
        m = m or p["tiers"].get(t)
        if not m:
            sys.exit(f"provider '{provider}' has no model for tier '{t}'")
    return {
        "provider": provider,
        "model": m,
        "tier": t,
        "turns": cfg.get("turns", 40),
        "minutes": cfg.get("minutes", 60),
        "fell_back": fell_back,
        # Claude runs four roles as a subagent definition (--agent) and the other two on the tier model alone. Qwen
        # has no --agent flag, so run-agent.ps1 inlines the same definition into the prompt instead.
        "agent": cfg.get("claude_agent") if provider == "claude" else None,
        "agent_file": (cfg.get("agent_file") or None) if provider != "claude" else None,
        "args": p.get("args") or [],
        "settings": ("tools/autopilot/settings.json" if provider == "claude" else ".qwen/settings.json"),
    }


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
        print(f"  {role:13s} tier {got['tier']:8s} -> {got['provider']} {got['model']:18s} "
              f"{got['turns']:3d} turns / {got['minutes']:3d} min{mark}")
    if r["provider"] == "qwen" or any(isinstance(v, dict) and v.get("provider") == "qwen"
                                      for v in (r.get("overrides") or {}).values()):
        print(f"qwen api key in {QWEN_SETTINGS}: "
              f"{'found' if qwen_key() else 'MISSING (runs fall back to claude until it is set)'}")


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


if __name__ == "__main__":
    main()
