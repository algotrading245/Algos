"""The desk's only door to a market. MT5Broker talks to the desk terminal (C:\\MetaTrader 5 - Desk, portable);
PaperBroker is an in-memory market for tests; DryBroker is what the desk runs on until the owner logs a demo in.

No method exposes or takes a login or password. Bars come in server time (unix seconds of the server wall clock),
the forming bar dropped. Times returned on positions and deals are UTC datetimes.
"""
import datetime as dt
import os
from pathlib import Path

import pandas as pd

from desk import clocks, paths

TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def server_epoch_to_utc(sec):
    return clocks.from_server(dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(sec)))


def utc_to_server_epoch(t):
    return int((clocks.server(t) - dt.datetime(1970, 1, 1)).total_seconds())


class Broker:
    mode = "dry"

    def connected(self):
        return False

    def account(self):
        return None

    def resolve(self, canonical):
        return None

    def spec(self, sym):
        return None

    def tick(self, sym):
        return None

    def bars(self, sym, tf, n):
        return None

    def positions(self):
        return []

    def orders(self):
        return []

    def deals_since(self, t):
        return []

    def calc_margin(self, sym, side, volume, price):
        return None

    def send(self, **kw):
        return {"ok": False, "comment": "dry: no account"}

    def modify_position(self, ticket, sl=None, tp=None):
        return {"ok": False, "comment": "dry"}

    def close_position(self, ticket, volume=None):
        return {"ok": False, "comment": "dry"}

    def cancel(self, order):
        return {"ok": False, "comment": "dry"}

    def shutdown(self):
        pass


class DryBroker(Broker):
    def __init__(self, why=""):
        self.why = why


class MT5Broker(Broker):
    """The desk terminal only. initialize() is always given the desk path; anything else is refused."""
    mode = "mt5"

    def __init__(self, cfg):
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.cfg = cfg
        term = cfg["terminal"]["path"]
        self.why = ""
        self._ok = False
        self._sym = {}
        if not Path(term).exists():
            self.why = f"desk terminal not installed: {term}"
            return
        # 20 s: a terminal with no account logged in never answers (IPC timeout), and the clock runs every minute
        if not mt5.initialize(path=term, portable=cfg["terminal"].get("portable", True), timeout=20000):
            self.why = f"initialize failed: {mt5.last_error()}"
            return
        info = mt5.terminal_info()
        if info is None or Path(info.path).resolve() != Path(term).parent.resolve():
            self.why = f"connected to the wrong terminal ({getattr(info, 'path', None)}); refusing"
            mt5.shutdown()
            return
        acc = mt5.account_info()
        if acc is None:
            self.why = "no account logged in on the desk terminal"
            return
        self._ok = True
        self.terminal_trade_allowed = bool(info.trade_allowed)

    def connected(self):
        return self._ok and self.mt5.account_info() is not None

    def account(self):
        a = self.mt5.account_info()
        if a is None:
            return None
        kind = {0: "demo", 1: "contest", 2: "live"}.get(a.trade_mode, "live")
        return {"balance": a.balance, "equity": a.equity, "margin": a.margin, "margin_free": a.margin_free,
                "currency": a.currency, "leverage": a.leverage, "kind": kind, "hedging": a.margin_mode == 2,
                "company": a.company, "trade_allowed": bool(a.trade_allowed and a.trade_expert),
                "terminal_algo": bool(self.mt5.terminal_info().trade_allowed)}

    def resolve(self, canonical):
        if canonical in self._sym:
            return self._sym[canonical]
        ins = self.cfg["instruments"].get(canonical, {})
        names = ins.get("broker", [canonical])
        found = None
        for base in names:
            for suf in self.cfg.get("suffixes", [""]):
                s = self.mt5.symbol_info(base + suf)
                if s is not None and s.trade_mode != 0:
                    found = base + suf
                    break
            if found:
                break
        if found:
            self.mt5.symbol_select(found, True)
        self._sym[canonical] = found
        return found

    def spec(self, sym):
        s = self.mt5.symbol_info(sym)
        if s is None:
            return None
        return {"digits": s.digits, "point": s.point, "tick_size": s.trade_tick_size or s.point,
                "tick_value": s.trade_tick_value_loss or s.trade_tick_value, "vol_min": s.volume_min,
                "vol_max": s.volume_max, "vol_step": s.volume_step, "stops_level": s.trade_stops_level,
                "freeze_level": s.trade_freeze_level, "contract_size": s.trade_contract_size,
                "trade_mode": s.trade_mode, "filling": s.filling_mode, "spread_pts": s.spread}

    def tick(self, sym):
        t = self.mt5.symbol_info_tick(sym)
        if t is None or t.bid <= 0:
            return None
        return {"bid": t.bid, "ask": t.ask, "time": server_epoch_to_utc(t.time)}

    def bars(self, sym, tf, n):
        tfc = getattr(self.mt5, "TIMEFRAME_" + tf)
        r = self.mt5.copy_rates_from_pos(sym, tfc, 1, n)  # from 1: the forming bar dropped
        if r is None or len(r) == 0:
            return None
        df = pd.DataFrame(r)[["time", "open", "high", "low", "close", "spread"]]
        return df.reset_index(drop=True)

    def _pos(self, p):
        return {"ticket": p.ticket, "symbol": p.symbol, "side": "buy" if p.type == 0 else "sell", "volume": p.volume,
                "price_open": p.price_open, "sl": p.sl, "tp": p.tp, "profit": p.profit + p.swap, "magic": p.magic,
                "comment": p.comment, "time": server_epoch_to_utc(p.time), "price_current": p.price_current}

    def positions(self):
        return [self._pos(p) for p in (self.mt5.positions_get() or [])]

    def orders(self):
        out = []
        for o in self.mt5.orders_get() or []:
            out.append({"ticket": o.ticket, "symbol": o.symbol, "type": o.type, "volume": o.volume_current,
                        "price": o.price_open, "sl": o.sl, "tp": o.tp, "magic": o.magic, "comment": o.comment})
        return out

    def deals_since(self, t):
        a = dt.datetime(1970, 1, 1, tzinfo=clocks.UTC) + dt.timedelta(seconds=utc_to_server_epoch(t))
        b = dt.datetime(1970, 1, 1, tzinfo=clocks.UTC) + dt.timedelta(seconds=utc_to_server_epoch(clocks.now()) + 86400)
        out = []
        for d in self.mt5.history_deals_get(a, b) or []:
            out.append({"ticket": d.ticket, "order": d.order, "position": d.position_id, "symbol": d.symbol,
                        "entry": {0: "in", 1: "out", 2: "inout", 3: "out_by"}.get(d.entry, "?"),
                        "side": "buy" if d.type == 0 else "sell" if d.type == 1 else "other", "volume": d.volume,
                        "price": d.price, "profit": d.profit + d.commission + d.swap + getattr(d, "fee", 0.0),
                        "magic": d.magic, "comment": d.comment, "reason": d.reason,
                        "time": server_epoch_to_utc(d.time)})
        return out

    def calc_margin(self, sym, side, volume, price):
        t = self.mt5.ORDER_TYPE_BUY if side == "buy" else self.mt5.ORDER_TYPE_SELL
        return self.mt5.order_calc_margin(t, sym, volume, price)

    def _filling(self, sym):
        f = self.mt5.symbol_info(sym).filling_mode
        return self.mt5.ORDER_FILLING_FOK if f & 1 else self.mt5.ORDER_FILLING_IOC if f & 2 else self.mt5.ORDER_FILLING_RETURN

    def _result(self, r):
        if r is None:
            return {"ok": False, "retcode": None, "comment": str(self.mt5.last_error())}
        ok = r.retcode in (self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_PLACED, self.mt5.TRADE_RETCODE_DONE_PARTIAL)
        return {"ok": ok, "retcode": r.retcode, "comment": r.comment, "order": r.order, "deal": r.deal,
                "price": r.price, "volume": r.volume}

    def send(self, symbol, side, volume, kind="market", price=None, sl=0.0, tp=0.0, magic=0, comment="", expire=None):
        m = self.mt5
        req = {"symbol": symbol, "volume": float(volume), "sl": float(sl or 0), "tp": float(tp or 0), "magic": int(magic),
               "comment": comment[:31], "deviation": 20, "type_time": m.ORDER_TIME_GTC}
        if kind == "market":
            t = self.tick(symbol)
            req.update(action=m.TRADE_ACTION_DEAL, type=m.ORDER_TYPE_BUY if side == "buy" else m.ORDER_TYPE_SELL,
                       price=t["ask"] if side == "buy" else t["bid"], type_filling=self._filling(symbol))
        else:
            types = {("buy", "limit"): m.ORDER_TYPE_BUY_LIMIT, ("sell", "limit"): m.ORDER_TYPE_SELL_LIMIT,
                     ("buy", "stop"): m.ORDER_TYPE_BUY_STOP, ("sell", "stop"): m.ORDER_TYPE_SELL_STOP}
            req.update(action=m.TRADE_ACTION_PENDING, type=types[(side, kind)], price=float(price),
                       type_filling=m.ORDER_FILLING_RETURN)
            if expire is not None:
                req.update(type_time=m.ORDER_TIME_SPECIFIED, expiration=utc_to_server_epoch(expire))
        r = self._result(m.order_send(req))
        if not r["ok"] and r.get("retcode") == m.TRADE_RETCODE_INVALID_FILL and kind == "market":
            req["type_filling"] = m.ORDER_FILLING_IOC if req["type_filling"] != m.ORDER_FILLING_IOC else m.ORDER_FILLING_RETURN
            r = self._result(m.order_send(req))
        return r

    def modify_position(self, ticket, sl=None, tp=None):
        p = self.mt5.positions_get(ticket=ticket)
        if not p:
            return {"ok": False, "comment": "no such position"}
        p = p[0]
        req = {"action": self.mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol,
               "sl": float(p.sl if sl is None else sl), "tp": float(p.tp if tp is None else tp)}
        return self._result(self.mt5.order_send(req))

    def close_position(self, ticket, volume=None):
        p = self.mt5.positions_get(ticket=ticket)
        if not p:
            return {"ok": False, "comment": "no such position"}
        p = p[0]
        t = self.tick(p.symbol)
        buy = p.type == 0
        req = {"action": self.mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": p.symbol,
               "volume": float(volume or p.volume), "type": self.mt5.ORDER_TYPE_SELL if buy else self.mt5.ORDER_TYPE_BUY,
               "price": t["bid"] if buy else t["ask"], "deviation": 30, "magic": p.magic,
               "type_filling": self._filling(p.symbol), "comment": "desk close"}
        return self._result(self.mt5.order_send(req))

    def cancel(self, order):
        return self._result(self.mt5.order_send({"action": self.mt5.TRADE_ACTION_REMOVE, "order": int(order)}))

    def shutdown(self):
        try:
            self.mt5.shutdown()
        except Exception:
            pass


class PaperBroker(Broker):
    """An in-memory market for tests. set_price() moves a symbol; step() fills pending orders and hits stops/targets
    (stop first when a move crosses both)."""
    mode = "paper"

    def __init__(self, balance=10000.0, kind="demo", hedging=True, specs=None):
        self.balance = balance
        self.kind = kind
        self.hedging = hedging
        self.specs = specs or {}
        self.px = {}
        self.pos = {}
        self.ords = {}
        self.deals = []
        self.next = 1000
        self.bar_frames = {}
        self.margin_per_lot = 1000.0

    def _id(self):
        self.next += 1
        return self.next

    def connected(self):
        return True

    def account(self):
        eq = self.balance + sum(self._pnl(p) for p in self.pos.values())
        used = sum(p["volume"] * self.margin_per_lot for p in self.pos.values())
        return {"balance": self.balance, "equity": eq, "margin": used, "margin_free": eq - used, "currency": "USD",
                "leverage": 100, "kind": self.kind, "hedging": self.hedging, "company": "paper",
                "trade_allowed": True, "terminal_algo": True}

    def resolve(self, canonical):
        return canonical if canonical in self.specs else None

    def spec(self, sym):
        return self.specs.get(sym)

    def set_price(self, sym, bid, ask=None, step=True):
        self.px[sym] = {"bid": bid, "ask": ask if ask is not None else bid, "time": clocks.now()}
        if step:
            self.step()

    def tick(self, sym):
        return self.px.get(sym)

    def bars(self, sym, tf, n):
        df = self.bar_frames.get((sym, tf))
        return None if df is None else df.tail(n).reset_index(drop=True)

    def _pnl(self, p, price=None):
        s = self.specs[p["symbol"]]
        t = self.px.get(p["symbol"])
        if price is None:
            if not t:
                return 0.0
            price = t["bid"] if p["side"] == "buy" else t["ask"]
        d = (price - p["price_open"]) * (1 if p["side"] == "buy" else -1)
        return d / s["tick_size"] * s["tick_value"] * p["volume"]

    def positions(self):
        out = []
        for p in self.pos.values():
            q = dict(p)
            q["profit"] = self._pnl(p)
            out.append(q)
        return out

    def orders(self):
        return [dict(o) for o in self.ords.values()]

    def deals_since(self, t):
        return [d for d in self.deals if d["time"] >= t]

    def calc_margin(self, sym, side, volume, price):
        return volume * self.margin_per_lot

    def _open(self, symbol, side, volume, price, sl, tp, magic, comment, order):
        tk = self._id()
        self.pos[tk] = {"ticket": tk, "symbol": symbol, "side": side, "volume": volume, "price_open": price,
                        "sl": sl or 0.0, "tp": tp or 0.0, "magic": magic, "comment": comment, "time": clocks.now()}
        self.deals.append({"ticket": self._id(), "order": order, "position": tk, "symbol": symbol, "entry": "in",
                           "side": side, "volume": volume, "price": price, "profit": 0.0, "magic": magic,
                           "comment": comment, "reason": 3, "time": clocks.now()})
        return tk

    def send(self, symbol, side, volume, kind="market", price=None, sl=0.0, tp=0.0, magic=0, comment="", expire=None):
        t = self.px.get(symbol)
        if t is None:
            return {"ok": False, "comment": "no price"}
        oid = self._id()
        if kind == "market":
            fill = t["ask"] if side == "buy" else t["bid"]
            self._open(symbol, side, volume, fill, sl, tp, magic, comment[:31], oid)
            return {"ok": True, "order": oid, "price": fill, "volume": volume, "retcode": 10009}
        self.ords[oid] = {"ticket": oid, "symbol": symbol, "side": side, "kind": kind, "volume": volume, "price": price,
                          "sl": sl, "tp": tp, "magic": magic, "comment": comment[:31], "expire": expire}
        return {"ok": True, "order": oid, "price": price, "volume": volume, "retcode": 10008}

    def modify_position(self, ticket, sl=None, tp=None):
        p = self.pos.get(ticket)
        if not p:
            return {"ok": False, "comment": "no such position"}
        if sl is not None:
            p["sl"] = sl
        if tp is not None:
            p["tp"] = tp
        return {"ok": True}

    def close_position(self, ticket, volume=None, price=None, reason=3):
        p = self.pos.get(ticket)
        if not p:
            return {"ok": False, "comment": "no such position"}
        t = self.px[p["symbol"]]
        price = price if price is not None else (t["bid"] if p["side"] == "buy" else t["ask"])
        vol = min(volume or p["volume"], p["volume"])
        part = dict(p, volume=vol)
        pnl = self._pnl(part, price)
        self.balance += pnl
        self.deals.append({"ticket": self._id(), "order": 0, "position": ticket, "symbol": p["symbol"], "entry": "out",
                           "side": "sell" if p["side"] == "buy" else "buy", "volume": vol, "price": price,
                           "profit": pnl, "magic": p["magic"], "comment": p["comment"], "reason": reason,
                           "time": clocks.now()})
        p["volume"] = round(p["volume"] - vol, 8)
        if p["volume"] <= 1e-9:
            del self.pos[ticket]
        return {"ok": True, "price": price}

    def cancel(self, order):
        return {"ok": self.ords.pop(order, None) is not None}

    def step(self):
        now = clocks.now()
        for oid, o in list(self.ords.items()):
            t = self.px.get(o["symbol"])
            if not t:
                continue
            if o.get("expire") and now >= o["expire"]:
                del self.ords[oid]
                continue
            px = t["ask"] if o["side"] == "buy" else t["bid"]
            hit = ((o["kind"] == "limit" and (px <= o["price"] if o["side"] == "buy" else px >= o["price"])) or
                   (o["kind"] == "stop" and (px >= o["price"] if o["side"] == "buy" else px <= o["price"])))
            if hit:
                del self.ords[oid]
                self._open(o["symbol"], o["side"], o["volume"], o["price"], o["sl"], o["tp"], o["magic"], o["comment"], oid)
        for tk, p in list(self.pos.items()):
            t = self.px.get(p["symbol"])
            if not t:
                continue
            px = t["bid"] if p["side"] == "buy" else t["ask"]
            buy = p["side"] == "buy"
            if p["sl"] and (px <= p["sl"] if buy else px >= p["sl"]):
                self.close_position(tk, price=p["sl"], reason=4)
            elif p["tp"] and (px >= p["tp"] if buy else px <= p["tp"]):
                self.close_position(tk, price=p["tp"], reason=5)


def connect(cfg=None):
    """The broker the desk trades through: the desk terminal when a demo (or allowed live) account is logged in,
    else a DryBroker that says why."""
    cfg = cfg or paths.config()
    if os.environ.get("AURUM_DESK_DRY"):
        return DryBroker("AURUM_DESK_DRY set")
    try:
        b = MT5Broker(cfg)
    except Exception as e:  # MetaTrader5 missing or crashed
        return DryBroker(f"mt5 error: {e}")
    if not b._ok:
        b.shutdown()
        return DryBroker(b.why)
    return b
