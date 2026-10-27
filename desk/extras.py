"""The Phase 1-2 cli commands (DESIGN.md sections 3c and 6); they register themselves with desk.cli.

board post "text" [instrument=SYM] [cites=b1,b2]   post as your pod (the owner posts as "owner")
board read [N] [pod=POD]
memory similar TICKET | calibration [POD] | lessons [POD] [N]
memory lesson POD "text" [ticket=ID]               the debrief or the owner
playbook show POD | log POD
playbook edit POD FILE "why"                       the head trader or the owner
playbook rollback POD V "why"                      the head trader or the owner
edge list | describe NAME | score NAME
edge sandbox NAME [MARKET] [key=value ...] [from=YYYY-MM-DD] [to=YYYY-MM-DD]
edge arm NAME MARKET [key=value ...] [risk=PCT]    any pod on a market it owns (systematic: any market), or the
                                                   owner [pod=POD]; needs a passing sandbox run
edge disarm NAME [MARKET]                          a pod disarms its own legs; systematic and the owner any leg
scores                                            the scorekeeper's last scores and the pod allocation
live-gate                                          the live gate, evaluated now (it also writes reports/live_gate.md)
"""
from pathlib import Path

from desk import cli, live_gate, memory, paths, playbooks, scorekeeper, tickets
from desk.cli import HEAD, Refused

EDITORS = (HEAD, "")  # the head trader, or the owner (no role)
ARM_MIN_TRADES, ARM_MIN_PF = 30, 1.1  # a leg's own sandbox run, after costs, before any pod may arm it


def _kv_split(args):
    pos, kv = [], {}
    for a in args:
        if "=" in a and not a.startswith(("http", "\"")) and a.split("=", 1)[0].isidentifier():
            k, v = a.split("=", 1)
            kv[k] = v
        else:
            pos.append(a)
    return pos, kv


def _pod(name, cfg=None):
    cfg = cfg or paths.config()
    if name not in cfg.get("pods", {}):
        raise Refused(f"no pod {name}; pods are {', '.join(cfg.get('pods', {}))}")
    return name


def board(args):
    op = args[0] if args else "read"
    pos, kv = _kv_split(args[1:])
    if op == "post":
        if not pos:
            raise Refused('board post "text" [instrument=SYM] [cites=b1,b2]')
        who = cli.role() or "owner"
        if who not in paths.config().get("pods", {}) and who not in (HEAD, "owner"):
            raise Refused(f"role {who} does not post on the board")
        cites = [c for c in kv.get("cites", "").split(",") if c]
        return memory.post(who, " ".join(pos), kv.get("instrument"), cites)
    if op == "read":
        return memory.board(int(pos[0]) if pos else 30, kv.get("pod"))
    raise Refused("board post|read")


def memory_cmd(args):
    op = args[0] if args else ""
    pos, kv = _kv_split(args[1:])
    if op == "similar":
        if not pos:
            raise Refused("memory similar TICKET")
        tk = tickets.fold().get(pos[0])
        if not tk:
            raise Refused(f"no ticket {pos[0]}")
        return memory.similar(tk, int(kv.get("n", 20)))
    if op == "calibration":
        return memory.calibration(_pod(pos[0]) if pos else None)
    if op == "lessons":
        pod = _pod(pos[0]) if pos and not pos[0].isdigit() else None
        n = int(pos[-1]) if pos and pos[-1].isdigit() else 20
        return memory.lessons(pod, n)
    if op == "lesson":
        if cli.role() not in ("debrief", ""):
            raise Refused("only the debrief or the owner writes lessons")
        if len(pos) < 2:
            raise Refused('memory lesson POD "text" [ticket=ID]')
        return memory.add_lesson(_pod(pos[0]), " ".join(pos[1:]), kv.get("ticket"))
    raise Refused("memory similar|calibration|lessons|lesson")


def playbook(args):
    op = args[0] if args else ""
    if op in ("show", "log"):
        if len(args) < 2:
            raise Refused(f"playbook {op} POD")
        pod = _pod(args[1])
        if op == "log":
            return playbooks.log(pod)
        return {"pod": pod, "version": playbooks.version(pod), "text": playbooks.show(pod)}
    if op in ("edit", "rollback"):
        if cli.role() not in EDITORS:
            raise Refused("only the head trader or the owner changes a playbook")
        if len(args) < 4:
            raise Refused(f'playbook {op} POD {"FILE" if op == "edit" else "V"} "why"')
        pod, why, by = _pod(args[1]), " ".join(args[3:]), cli.role() or "owner"
        try:
            if op == "edit":
                f = Path(args[2])
                if not f.is_absolute():
                    f = paths.ROOT / f
                if not f.exists():
                    raise Refused(f"no file {args[2]}")
                return {"ok": True, "pod": pod, "version": playbooks.edit(pod, f.read_text(encoding="utf-8"), why, by)}
            return {"ok": True, "pod": pod, "version": playbooks.rollback(pod, args[2], why, by)}
        except ValueError as e:
            raise Refused(str(e))
    raise Refused("playbook show|log|edit|rollback")


def edge(args):
    from desk import edges, sandbox
    op = args[0] if args else "list"
    if op == "list":
        edges.load_new()
        return {"edges": {n: {k: e.get(k) for k in ("pod", "kind", "markets", "tf") if k in e}
                          for n, e in sorted(edges.EDGES.items())},
                "broken": edges.BROKEN}
    if len(args) < 2:
        raise Refused(f"edge {op} NAME")
    try:
        e = edges.get(args[1])
    except KeyError:
        raise Refused(f"no edge {args[1]}")
    if op == "describe":
        return edges.describe(e) | {"card": paths.read_json(sandbox.CARDS / f"{args[1]}.json", {})}
    if op == "score":
        card = paths.read_json(sandbox.CARDS / f"{args[1]}.json", {})
        bt = [v.get("total_r", 0) / v["trades"] for v in (card.get("backtest") or {}).values() if v.get("trades")]
        return memory.edge_score(args[1], sum(bt) / len(bt) if bt else 0.0)
    if op == "sandbox":
        try:
            name, market, params, start, end = sandbox.parse(args[1:])
            return sandbox.run_edge(name, market, params, start, end)
        except ValueError as err:
            raise Refused(str(err))
    if op in ("arm", "disarm"):
        return _arm(op, e, args[1:])
    raise Refused("edge list|describe|score|sandbox|arm|disarm")


def _arm(op, e, args):
    """Arm a leg only on the evidence of its own sandbox card: same market, same params, enough trades, PF after costs."""
    from desk import sandbox, systematic
    cfg = paths.config()
    role = cli.role()
    if role and role not in cfg.get("pods", {}):
        raise Refused("only a pod or the owner arms or disarms a leg")
    pos, kv = _kv_split(args)
    pod = _pod(kv.pop("pod", systematic.POD), cfg) if not role else role
    name = pos[0]
    market = pos[1] if len(pos) > 1 else None
    if op == "disarm":
        return {"ok": True, "armed": systematic.disarm(name, market, None if role in ("", systematic.POD) else role)}
    if not market:
        raise Refused("edge arm NAME MARKET [key=value ...] [risk=PCT]")
    owns = cfg["pods"][pod].get("owns", [])
    if pod != systematic.POD and market not in owns:
        raise Refused(f"{pod} arms legs only on its own markets ({', '.join(owns) or 'none'}), not {market}")
    other = [a.get("pod", systematic.POD) for a in systematic.state()["armed"]
             if (a["edge"], a["market"]) == (name, market) and a.get("pod", systematic.POD) != pod]
    if other and role:
        raise Refused(f"{name} on {market} is already armed by {other[0]}: the same signal twice is one leg twice "
                      "the size")
    risk = float(kv.pop("risk", systematic.RISK_PCT))
    params = sandbox.parse([name, market] + [f"{k}={v}" for k, v in kv.items()])[2]
    want = dict(e["defaults"]) | (params or {})
    run = (paths.read_json(sandbox.CARDS / f"{name}.json", {}).get("backtest") or {}).get(market)
    if not run or run.get("error"):
        raise Refused(f"no sandbox run of {name} on {market}: run edge sandbox {name} {market} first")
    if run.get("params") != want:
        raise Refused(f"the last sandbox run of {name} on {market} used {run.get('params')}, not {want}")
    if run.get("from") or run.get("to"):
        raise Refused(f"arm on a run over the whole history, not {run.get('from')}..{run.get('to')}")
    if (run.get("trades") or 0) < ARM_MIN_TRADES or (run.get("pf") or 0) < ARM_MIN_PF:
        raise Refused(f"{name} on {market}: {run.get('trades')} trades, PF {run.get('pf')} after costs; arming needs "
                      f"{ARM_MIN_TRADES}+ trades and PF {ARM_MIN_PF}+")
    try:
        return {"ok": True, "armed": systematic.arm(name, market, params, risk, pod)}
    except ValueError as err:
        raise Refused(str(err))


def scores(_args):
    return {"scores": paths.read_json(scorekeeper.SCORES, {}), "alloc": paths.read_json(scorekeeper.ALLOC, {})}


def gate(_args):
    return live_gate.write()


for _name, _fn in (("board", board), ("memory", memory_cmd), ("playbook", playbook), ("edge", edge),
                   ("scores", scores), ("live-gate", gate)):
    cli.register(_name, _fn)
