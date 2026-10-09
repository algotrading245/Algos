"""Reference model of AurumLadder's maths (spec sections 1, 2 and 4).

Mirrors mql5/Include/AurumLadder/Ladder.mqh and Signal.mqh formula for formula,
so the MQL5 code can be checked against numbers computed here. Not used for trading.
All distances are in price units; V converts lot x price into account currency.
"""
import math

EPS = 1e-9


def round_up(lot, step):
    return math.ceil(lot / step - EPS) * step


def round_down(lot, step):
    return math.floor(lot / step + EPS) * step


def side_sums(lots, n):
    """Lots on trade n's side (W) and on the opposite side (X), over trades 1..n-1.

    Trades alternate side, so trade k is on trade n's side when k and n share parity.
    n is 1-based.
    """
    w = sum(l for k, l in enumerate(lots[: n - 1], start=1) if k % 2 == n % 2)
    x = sum(l for k, l in enumerate(lots[: n - 1], start=1) if k % 2 != n % 2)
    return w, x


def ladder_lots(l1, n_max, d, t, s, c, step, vmin=0.0, vmax=math.inf):
    """Lot list for an n_max-step ladder, or None when a lot would exceed vmax."""
    pi = l1 * (t - c)
    lots = [l1]
    for n in range(2, n_max + 1):
        w, x = side_sums(lots, n)
        ln = (pi + (d + t + s) * x + c * (w + x) - t * w) / (t - c)
        ln = max(round_up(ln, step), vmin)
        if ln > vmax + EPS:
            return None
        lots.append(ln)
    return lots


def basket_profit_at_target(lots, n, d, t, s, c):
    """Lot x price profit when trade n is the latest fill and its side hits target."""
    w, x = side_sums(lots, n)
    w += lots[n - 1]
    return t * w - (d + t + s) * x - c * (w + x)


def failed_loss(lots, d, t, s, c):
    """Lot x price loss when the last trade is stopped out (positive number)."""
    n = len(lots)
    w, x = side_sums(lots, n + 1)  # trades 1..n, grouped relative to n+1
    w, x = x, w                    # swap so W is the last trade's side
    return (d + t + s) * w - t * x + c * (w + x)


def first_lot(balance, cap_frac, n_max, d, t, s, c, v, step, vmin, vmax,
              margin_per_lot=0.0, free_margin=math.inf, margin_frac=0.5):
    """Largest L1 meeting the loss cap and margin limit.

    Returns (l1, n, lots); reduces N while even vmin does not fit; (None, n, None)
    when N would fall below 3.
    """
    cap = balance * cap_frac
    for n in range(n_max, 2, -1):
        best = None
        k = round(vmin / step)
        while True:
            l1 = k * step
            if l1 > vmax + EPS:
                break
            lots = ladder_lots(l1, n, d, t, s, c, step, vmin, vmax)
            if lots is None:
                break
            loss = v * failed_loss(lots, d, t, s, c)
            margin = margin_per_lot * sum(lots)
            if loss > cap + EPS or margin > margin_frac * free_margin + EPS:
                break
            best = (l1, n, lots)
            k += 1
        if best:
            return best
    return None, 2, None


def regression_tstat(closes):
    """t-statistic of the least-squares slope of ln(close) against bar index."""
    y = [math.log(p) for p in closes]
    n = len(y)
    xm = (n - 1) / 2
    ym = sum(y) / n
    sxx = sum((i - xm) ** 2 for i in range(n))
    sxy = sum((i - xm) * (y[i] - ym) for i in range(n))
    b = sxy / sxx
    sse = sum((y[i] - ym - b * (i - xm)) ** 2 for i in range(n))
    if sse <= 1e-18:
        return math.copysign(1e9, b) if b else 0.0
    se = math.sqrt(sse / (n - 2) / sxx)
    return b / se


def efficiency_ratio(closes):
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return abs(closes[-1] - closes[0]) / path if path > 0 else 0.0


def direction(closes, t_min=3.0, er_min=0.25):
    """+1 buy, -1 sell, 0 no trade."""
    t = regression_tstat(closes)
    if abs(t) >= t_min and efficiency_ratio(closes) >= er_min:
        return 1 if t > 0 else -1
    return 0


def simulate(bids, spread, side1, lots, d, t, s):
    """Walk a bid path through the order geometry used by Cycle.mqh.

    Trade 1 fills at the first tick. Buys enter on ask at the upper edge, sells on bid
    at the lower edge; buy TP upper+t / SL lower-t-s on bid, sell TP lower-t / SL
    upper+t+s on ask. The first SL/TP hit closes the whole basket at that tick.
    Returns (lot x price result, trades filled), or None if the path never exits.
    """
    ask0 = bids[0] + spread
    upper, lower = (ask0, ask0 - d) if side1 > 0 else (bids[0] + d, bids[0])
    open_ = [(side1, lots[0], ask0 if side1 > 0 else bids[0])]
    for bid in bids[1:]:
        ask = bid + spread
        side = -open_[-1][0]
        if len(open_) < len(lots):
            if side > 0 and ask >= upper:
                open_.append((1, lots[len(open_)], ask))
            elif side < 0 and bid <= lower:
                open_.append((-1, lots[len(open_)], bid))
        hit = (bid >= upper + t or ask <= lower - t
               or any(sd > 0 for sd, _, _ in open_) and bid <= lower - t - s
               or any(sd < 0 for sd, _, _ in open_) and ask >= upper + t + s)
        if hit:
            pnl = sum(l * ((bid - px) if sd > 0 else (px - ask)) for sd, l, px in open_)
            return pnl, len(open_)
    return None
