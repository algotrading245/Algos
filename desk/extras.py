"""The Phase 1-2 cli commands (DESIGN.md sections 3c and 6); they register themselves with desk.cli.

board post "text" [instrument=SYM] [cites=b1,b2]   post as your pod (the owner posts as "owner")
board read [N] [pod=POD]
board ask POD|all "question" [instrument=SYM]      a question to another pod; it shows in that pod's brief
board reply ASK_ID "answer"                        answer an ask; the asker sees it in its next brief
board asks [POD]                                   the asks still open for a pod (yours by default)
memory similar TICKET | calibration [POD] | lessons [POD] [N]
memory lesson POD "text" [ticket=ID]               the debrief or the owner
memory learn "text" [instrument=SYM] [share=desk|pod]   share what you learned; desk puts it in every pod's brief
memory endorse KNOWLEDGE_ID                        vouch for another pod's entry (once each)
memory knowledge [POD] [n=40]
intel [POD]                                        a pod's intelligence profile, from its real record
playbook show POD | log POD
playbook edit POD FILE "why"                       the pod itself, the head trader or the owner (the pod's own rules)
playbook rollback POD V "why"                      the pod itself, the head trader or the owner
edge list | describe NAME | score NAME
edge sandbox NAME [MARKET] [key=value ...] [from=YYYY-MM-DD] [to=YYYY-MM-DD]
edge arm NAME MARKET [key=value ...] [risk=PCT]    any pod, on any desk market (owner 2026-11-01), or the owner
                                                   [pod=POD]; needs a passing sandbox run; the leg's P&L is the pod's
edge disarm NAME [MARKET]                          a pod disarms its own legs; systematic and the owner any leg
forecast new SYM up|down PROB HOURS "why" [level=PRICE]   a pod's call: SYM closes above/below the level (the mid
                                                   now by default) in HOURS (1-120), with chance PROB (0.5-0.99);
                                                   graded daily against the real price, the skill feeds the pod's
                                                   score and token share
forecast list [POD] [open|graded|void] [n=20] | forecast skill [POD]
model set SYM bias=up|down|flat [regime=trend|range|breakout|volatile|quiet] [levels=a,b] [conviction=1-3]
          [edges=x,y] ["drivers"]                  a pod's own view of a market (any desk market), kept between runs
model view "text" | drop SYM                       the pod's one-line view of the week; forget a market
model show [POD] | log [POD] | consensus           a pod's model (stale after 7 days), its changes, every pod's bias
scores                                            the scorekeeper's last scores and the pod allocation
live-gate                                          the live gate, evaluated now (it also writes reports/live_gate.md)
"""
from pathlib import Path

from desk import cli, forecasts, live_gate, market_model, memory, paths, playbooks, scorekeeper, tickets
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


def _talker():
    who = cli.role() or "owner"
    if who not in paths.config().get("pods", {}) and who not in (HEAD, "owner"):
        raise Refused(f"role {who} does not post on the board")
    return who


def _mem(fn, *a):
    try:
        return fn(*a)
    except ValueError as e:
        raise Refused(str(e))


def board(args):
    op = args[0] if args else "read"
    pos, kv = _kv_split(args[1:])
    if op == "post":
        if not pos:
            raise Refused('board post "text" [instrument=SYM] [cites=b1,b2]')
        cites = [c for c in kv.get("cites", "").split(",") if c]
        return memory.post(_talker(), " ".join(pos), kv.get("instrument"), cites)
    if op == "read":
        return memory.board(int(pos[0]) if pos else 30, kv.get("pod"))
    if op == "ask":
        if len(pos) < 2:
            raise Refused('board ask POD|all "question" [instrument=SYM]')
        to = pos[0] if pos[0] in ("all", HEAD) else _pod(pos[0])
        return _mem(memory.ask, _talker(), to, " ".join(pos[1:]), kv.get("instrument"))
    if op == "reply":
        if len(pos) < 2:
            raise Refused('board reply ASK_ID "answer"')
        return _mem(memory.reply, _talker(), pos[0], " ".join(pos[1:]))
    if op == "asks":
        return memory.open_asks(_pod(pos[0]) if pos else _talker())
    if op == "review":
        if len(pos) < 2:
            raise Refused('board review TICKET "comment"')
        return _mem(memory.review, _talker(), pos[0], " ".join(pos[1:]))
    raise Refused("board post|read|ask|reply|asks|review")


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
    if op == "learn":
        if not pos:
            raise Refused('memory learn "what you learned" [instrument=SYM] [share=desk|pod]')
        return _mem(memory.learn, _talker(), " ".join(pos), kv.get("instrument"), kv.get("share", "desk"))
    if op == "endorse":
        if not pos:
            raise Refused("memory endorse KNOWLEDGE_ID")
        return _mem(memory.endorse, _talker(), pos[0])
    if op == "knowledge":
        return memory.knowledge(_pod(pos[0]) if pos else None)[-int(kv.get("n", 40)):]
    raise Refused("memory similar|calibration|lessons|lesson|learn|endorse|knowledge")


def intel_cmd(args):
    from desk import intel
    return intel.profile(_pod(args[0])) if args else intel.all_profiles()


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
        if len(args) < 4:
            raise Refused(f'playbook {op} POD {"FILE" if op == "edit" else "V"} "why"')
        pod, why, by = _pod(args[1]), " ".join(args[3:]), cli.role() or "owner"
        if cli.role() not in EDITORS and cli.role() != pod:
            raise Refused("a pod changes only its own playbook (the head trader or the owner any)")
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
    over = _spread_over_cost(market, cfg)
    if over:
        raise Refused(f"{market}'s normal broker spread {over[0]:.6g} is above its cost in config.json ({over[1]:.6g}), "
                      "so the card's costs are too low: the owner raises the cost first, then re-run the sandbox")
    try:
        return {"ok": True, "armed": systematic.arm(name, market, params, risk, pod)}
    except ValueError as err:
        raise Refused(str(err))


def _spread_over_cost(market, cfg):
    """(normal spread, cost) when the broker's all-day median spread (spreads.json, the risk gate's daily table) is
    above the instrument's cost in config.json, which every sandbox card is costed at (owner 2026-10-27); else None."""
    from desk import spreads
    ins = cfg["instruments"].get(market, {})
    names = ins.get("broker") or []
    cache = paths.read_json(spreads.FILE, {})
    for n in [market, *([names] if isinstance(names, str) else names)]:
        med = ((cache.get(n) or {}).get("med") or {}).get("all")
        if med and ins.get("cost") is not None and med > ins["cost"]:
            return med, ins["cost"]
    return None


def forecast(args):
    pos, kv = _kv_split(args)
    if not pos or pos[0] not in ("new", "list", "skill"):
        raise Refused('forecast new SYM up|down PROB HOURS "why" [level=PRICE] | list [POD] [open|graded|void] | '
                      'skill [POD]')
    op, rest = pos[0], pos[1:]
    if op == "skill":
        return forecasts.skill(_pod(rest[0])) if rest else forecasts.skills()
    if op == "list":
        st = next((a for a in rest if a in ("open", "graded", "void")), None)
        pod = next((_pod(a) for a in rest if a not in ("open", "graded", "void")), None)
        rows = [f for f in forecasts.all_rows() if (pod is None or f["pod"] == pod) and (st is None or f["status"] == st)]
        return rows[-int(kv.get("n", 20)):]
    if len(rest) < 5:
        raise Refused('forecast new SYM up|down PROB HOURS "why" [level=PRICE]')
    cfg = paths.config()
    me = cli._pod_role(cfg)
    if me is None:
        if cli.role() != "":
            raise Refused("only a pod (or the owner, with pod=POD) makes forecasts")
        me = _pod(kv.get("pod", ""), cfg)
    elif kv.get("pod", me) != me:
        raise Refused("a pod makes forecasts as itself")
    sym, direction, prob, hours, why = rest[0].upper(), rest[1], rest[2], rest[3], " ".join(rest[4:])
    try:
        level = float(kv["level"]) if "level" in kv else None
        return {"ok": True, "forecast": forecasts.new(me, sym, direction, prob, hours, why, level)}
    except ValueError as e:
        raise Refused(str(e))


def _me(kv, cfg, what):
    """The pod acting: a pod as itself, or the owner naming one with pod=POD."""
    me = cli._pod_role(cfg)
    if me is None:
        if cli.role() != "":
            raise Refused(f"only a pod (or the owner, with pod=POD) {what}")
        return _pod(kv.get("pod", ""), cfg)
    if kv.get("pod", me) != me:
        raise Refused(f"a pod {what} as itself")
    return me


def model(args):
    pos, kv = _kv_split(args)
    usage = ('model show [POD] | set SYM bias=up|down|flat [regime=..] [levels=a,b] [conviction=1-3] [edges=x,y] '
             '["drivers"] | view "text" | drop SYM | log [POD] | consensus')
    if not pos or pos[0] not in ("show", "set", "view", "drop", "log", "consensus"):
        raise Refused(usage)
    op, rest = pos[0], pos[1:]
    if op == "consensus":
        return market_model.consensus()
    cfg = paths.config()
    if op in ("show", "log"):
        pod = _pod(rest[0], cfg) if rest else (cli._pod_role(cfg) or _pod(kv.get("pod", ""), cfg))
        return market_model.brief(pod) if op == "show" else market_model.history(pod, int(kv.get("n", 20)))
    me = _me(kv, cfg, "edits its market model")
    try:
        if op == "view":
            return {"ok": True, "view": market_model.set_view(me, " ".join(rest))["view"]}
        if not rest:
            raise Refused(usage)
        if op == "drop":
            market_model.drop(me, rest[0])
            return {"ok": True, "dropped": rest[0].upper()}
        fields = {k: v for k, v in kv.items() if k != "pod"}
        if len(rest) > 1:
            fields["drivers"] = " ".join(rest[1:])
        return {"ok": True, rest[0].upper(): market_model.set_market(me, rest[0], **fields)}
    except ValueError as e:
        raise Refused(str(e))


def scores(_args):
    return {"scores": paths.read_json(scorekeeper.SCORES, {}), "alloc": paths.read_json(scorekeeper.ALLOC, {})}


def gate(_args):
    return live_gate.write()


for _name, _fn in (("board", board), ("memory", memory_cmd), ("playbook", playbook), ("edge", edge),
                   ("scores", scores), ("live-gate", gate), ("intel", intel_cmd), ("forecast", forecast),
                   ("model", model)):
    cli.register(_name, _fn)
