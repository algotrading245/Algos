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
