"""Each pod's own market model (owner 2026-11-01): what it believes about the markets it watches, written down so it
carries from one run to the next, the other pods can read it, and its forecasts and tickets can be held against it.

A model is one overall view plus one entry per market the pod has a view on:
  bias       up | down | flat
  regime     trend | range | breakout | volatile | quiet
  levels     the prices that matter, low to high
  drivers    why: what moves this market now, in the pod's own words
  conviction 1 (a hunch) to 3 (would trade it)
  edges      the tested edges the pod leans on for this market (any in the library, desk.edges)
  updated    when; an entry older than STALE_DAYS is shown as stale until the pod looks again

The model is not graded itself: the forecasts are (desk/forecasts.py). The brief puts a pod's biases next to its open
forecasts, so a view the pod never puts a probability on is easy to see.

Files in logs/desk/state/models: POD.json (the model now) and POD.log.jsonl (every change, for the pod's own review).
"""
import datetime as dt

from desk import clocks, journal, paths

DIR = paths.STATE / "models"
BIASES = ("up", "down", "flat")
REGIMES = ("trend", "range", "breakout", "volatile", "quiet")
STALE_DAYS = 7
MAX_MARKETS = 20
FIELDS = ("bias", "regime", "levels", "drivers", "conviction", "edges")


def _file(pod):
    return DIR / f"{pod}.json"


def get(pod):
    return paths.read_json(_file(pod), {"pod": pod, "view": "", "markets": {}})


def _stale(entry, t):
    try:
        return t - dt.datetime.fromisoformat(entry["updated"]) > dt.timedelta(days=STALE_DAYS)
    except (KeyError, ValueError):
        return True


def _check_pod(pod, cfg):
    if pod not in cfg.get("pods", {}):
        raise ValueError(f"unknown pod {pod}")


def _save(pod, m, change, t):
    DIR.mkdir(parents=True, exist_ok=True)
    paths.write_json(_file(pod), m)
    paths.append_jsonl(DIR / f"{pod}.log.jsonl", {"t": t.isoformat(timespec="seconds")} | change)
    journal.log("model", pod=pod, **{k: v for k, v in change.items() if k != "drivers"})


def set_market(pod, instrument, t=None, **fields):
    """Add or change one market's entry. Only the fields given change. Raises ValueError on a bad value."""
    t = t or clocks.now()
    cfg = paths.config()
    _check_pod(pod, cfg)
    instrument = instrument.upper()
    if instrument not in cfg.get("instruments", {}):
        raise ValueError(f"{instrument} is not a desk market; markets are {', '.join(cfg.get('instruments', {}))}")
    bad = set(fields) - set(FIELDS)
    if bad:
        raise ValueError(f"unknown field {', '.join(sorted(bad))}; fields are {', '.join(FIELDS)}")
    new = {}
    if "bias" in fields:
        if fields["bias"] not in BIASES:
            raise ValueError(f"bias is {' | '.join(BIASES)}")
        new["bias"] = fields["bias"]
    if "regime" in fields:
        if fields["regime"] not in REGIMES:
            raise ValueError(f"regime is {' | '.join(REGIMES)}")
        new["regime"] = fields["regime"]
    if "conviction" in fields:
        c = int(fields["conviction"])
        if c not in (1, 2, 3):
            raise ValueError("conviction is 1 (a hunch), 2 or 3 (would trade it)")
        new["conviction"] = c
    if "levels" in fields:
        lv = fields["levels"]
        lv = [float(x) for x in (lv.split(",") if isinstance(lv, str) else lv) if str(x).strip()]
        new["levels"] = sorted(lv)
    if "edges" in fields:
        from desk import edges
        names = fields["edges"]
        names = [n.strip() for n in (names.split(",") if isinstance(names, str) else names) if n.strip()]
        unknown = [n for n in names if n not in edges.EDGES]
        if unknown:
            raise ValueError(f"no edge {', '.join(unknown)} in the library (edge list shows them)")
        new["edges"] = names
    if "drivers" in fields:
        new["drivers"] = str(fields["drivers"]).strip()
    m = get(pod)
    if instrument not in m["markets"] and len(m["markets"]) >= MAX_MARKETS:
        raise ValueError(f"{pod} already models {MAX_MARKETS} markets; drop one first")
    entry = m["markets"].get(instrument, {})
    if instrument not in m["markets"] and "bias" not in new:
        raise ValueError("a new market needs a bias (up, down or flat)")
    entry = entry | new | {"updated": t.isoformat(timespec="seconds")}
    m["markets"][instrument] = entry
    _save(pod, m, {"op": "set", "instrument": instrument} | new, t)
    return entry


def set_view(pod, text, t=None):
    t = t or clocks.now()
    _check_pod(pod, paths.config())
    if not str(text).strip():
        raise ValueError("say what the view is")
    m = get(pod)
    m["view"], m["view_updated"] = str(text).strip(), t.isoformat(timespec="seconds")
    _save(pod, m, {"op": "view", "view": m["view"]}, t)
    return m


def drop(pod, instrument, t=None):
    t = t or clocks.now()
    m = get(pod)
    if m["markets"].pop(instrument.upper(), None) is None:
        raise ValueError(f"{pod} has no view on {instrument.upper()}")
    _save(pod, m, {"op": "drop", "instrument": instrument.upper()}, t)
    return m


def history(pod, n=20):
    return paths.read_jsonl(DIR / f"{pod}.log.jsonl")[-n:]


def consensus(t=None):
    """Every pod's bias per market, so a pod can see where it stands with or against the desk."""
    t = t or clocks.now()
    out = {}
    for pod in paths.config().get("pods", {}):
        for sym, e in get(pod)["markets"].items():
            if not _stale(e, t):
                out.setdefault(sym, {})[pod] = f"{e.get('bias')}{e.get('conviction', '')}"
    return dict(sorted(out.items()))


def brief(pod, t=None):
    """What a pod sees: its model with stale entries marked, its biases no open forecast backs, and the desk's map."""
    from desk import forecasts
    t = t or clocks.now()
    m = get(pod)
    called = {f["instrument"] for f in forecasts.open_for(pod)}
    markets = {s: e | ({"stale": True} if _stale(e, t) else {}) for s, e in m["markets"].items()}
    return {"view": m.get("view") or "(none yet: one line on what drives the markets this week)",
            "markets": markets,
            "stale": sorted(s for s, e in markets.items() if e.get("stale")),
            "biases_with_no_forecast": sorted(s for s, e in markets.items()
                                              if e.get("bias") in ("up", "down") and not e.get("stale")
                                              and s not in called),
            "desk_biases": consensus(t)}
