# -*- coding: utf-8 -*-
"""72-hour entry/exit grid backtest on 15-minute candles after an Alpha listing.

Candles: [t_ms, open, high, low, close(, quote_vol)].
Entry price = close of the entry candle (the very first candle's open is a placeholder).
Each trade pays ``COST`` percent. If take-profit and stop-loss are both touched in the
same candle, the stop-loss is assumed to fill first (conservative).
"""
import statistics as st

COST = 0.5
BARS = 288   # 72 hours of 15m candles

ENTRIES = [("open15", 0, "first 15 min"), ("1h", 3, "after 1 hour"),
           ("4h", 15, "after 4 hours"), ("d1", 95, "after 24 hours")]
EXITS = [(None, None), (None, -20), (30, None), (30, -20), (50, -20), (50, -30), (100, -20), (100, -30)]


def simulate(k, i, tp=None, sl=None, cost=COST):
    """Enter at close of candle i. Returns (pnl_percent, exit_index)."""
    px = k[i][4]
    for j, b in enumerate(k[i + 1:], i + 1):
        if sl and b[3] <= px * (1 + sl / 100):
            return sl - cost, j
        if tp and b[2] >= px * (1 + tp / 100):
            return tp - cost, j
    return (k[-1][4] / px - 1) * 100 - cost, len(k) - 1


def grid(series_list):
    """Average / median / win-rate for every ENTRIES x EXITS combination."""
    out = []
    for key, i, _ in ENTRIES:
        for tp, sl in EXITS:
            r = [simulate(k, i, tp, sl)[0] for k in series_list if len(k) > i + 1]
            if not r:
                continue
            out.append({"mode": key, "tp": tp, "sl": sl, "n": len(r), "avg": round(st.mean(r), 2),
                        "med": round(st.median(r), 2), "win": round(sum(x > 0 for x in r) / len(r) * 100, 1)})
    return out


def summary(k):
    """Per-token numbers relative to the first candle close: 24h, 72h, max run-up."""
    if not k:
        return {}
    px = k[0][4]
    return {
        "px": px,
        "d1": round((k[96][4] / px - 1) * 100, 1) if len(k) > 96 else None,
        "r72": round((k[-1][4] / px - 1) * 100, 1) if len(k) >= BARS else None,
        "max": round((max([b[2] for b in k[1:]] or [px]) / px - 1) * 100, 1),
    }
