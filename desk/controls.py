"""The Controls screen's switches, applied for real (owner 2026-11-01).

Three kinds of switch, each with pause / resume (stop is pause: new entries stop, nothing open is closed):
  pod       desk pods: the `paused` list in logs/desk/state/alloc.json, the same list the scorekeeper uses, so a
            paused pod gets no wakes (runner) and no phase seat (phase.active_pods).
  pipeline  finder / builder / tester / judge: logs/autopilot/PAUSE-<role>; relay.ps1 skips a paused role (and a
            paused tester also skips tester_step.py). The whole-pipeline logs/autopilot/PAUSE stays the keeper's.
  demo      hydra / funded: <MT5 Common Files>/Aurum/stop_<leg>.flag; the EA stops new entries while it exists
            (AurumFunded 1.23 and AurumHydra 1.43 read it, via CAurumTrade in Include/Aurum/Legs.mqh; older builds
            on the demo ignore it; the tester never reads it).
Owner-only things are refused here: desk/risk.json, cli resume after a halt, live trading, deploys, the fidelity
pairing and the T16 terminal. Every change goes into the desk journal (kinds pause / resume, by owner).
"""
import os
from pathlib import Path

from desk import journal, paths, phase

ROOT = paths.ROOT
AP_LOGS = Path(os.environ.get("AURUM_AUTOPILOT_LOGS", ROOT / "logs" / "autopilot"))
COMMON = Path(os.environ.get("AURUM_MT5_COMMON",
                             Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files"))
ROLES = ("finder", "builder", "tester", "judge")
LEGS = ("hydra", "funded")
ACTIONS = ("pause", "resume", "stop")
OWNER_ONLY = {"risk", "resume_halt", "live", "deploy", "fidelity", "t16"}


class Refused(Exception):
    pass


def _pods():
    return set(((paths.config() or {}).get("pods") or {}).keys())


def role_flag(role):
    return AP_LOGS / f"PAUSE-{role}"


def leg_flag(leg):
    return COMMON / "Aurum" / f"stop_{leg}.flag"


def status():
    """What is paused right now, by kind."""
    alloc = paths.read_json(phase.ALLOC, {}) or {}
    return {"pod": sorted(alloc.get("paused") or []),
            "pipeline": [r for r in ROLES if role_flag(r).exists()],
            "pipeline_all": (AP_LOGS / "PAUSE").exists(),
            "demo": [g for g in LEGS if leg_flag(g).exists()]}


def apply(kind, target, action, why=""):
    """Pause, stop or resume one switch. Returns the new status(); raises Refused for anything else."""
    kind, target, action = str(kind or "").lower(), str(target or "").strip(), str(action or "").lower()
    why = (str(why or "").strip() or "dashboard")[:200]
    if kind in OWNER_ONLY or target in OWNER_ONLY:
        raise Refused(f"{target or kind} stays with the owner's own hands, not a dashboard switch")
    if action not in ACTIONS:
        raise Refused(f"unknown action {action!r}")
    off = action in ("pause", "stop")
    if kind == "pod":
        if target not in _pods():
            raise Refused(f"no desk pod named {target!r}")
        alloc = paths.read_json(phase.ALLOC, {}) or {}
        paused = set(alloc.get("paused") or [])
        if off == (target in paused):
            return status()
        paused = paused | {target} if off else paused - {target}
        alloc["paused"] = sorted(paused)
        paths.write_json(phase.ALLOC, alloc)
    elif kind == "pipeline":
        if target not in ROLES:
            raise Refused(f"no pipeline role named {target!r}")
        f = role_flag(target)
        if off == f.exists():
            return status()
        if off:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"paused by the owner from the dashboard: {why}\n", encoding="utf-8")
        else:
            f.unlink()
    elif kind == "demo":
        if target not in LEGS:
            raise Refused(f"no demo leg named {target!r}")
        f = leg_flag(target)
        if off == f.exists():
            return status()
        if off:
            if not COMMON.is_dir():
                raise Refused(f"MT5 Common Files not found at {COMMON}")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"{action} new entries: {why}\n", encoding="utf-8")
        else:
            f.unlink()
    else:
        raise Refused(f"unknown switch kind {kind!r}")
    journal.log("pause" if off else "resume", by="owner", why=why, switch=kind, target=target, action=action)
    return status()
