# -*- coding: utf-8 -*-
"""Binance Alpha token list + listing-price statistics.

Definitions
-----------
listing price (``ref``)
    First-day volume-weighted average price = quote volume / base volume of the
    first daily candle. The first candle's *open* is often a placeholder price,
    so it is never used.
current price
    ``price`` field of the Alpha token list.
peak
    Highest daily high since listing / listing price - 1.
drawdown (``dd``)
    Current price / highest high - 1.

If the last daily candle is older than 3 days (token moved to Binance spot and
the Alpha candles stopped) the peak is unknown, so ``peak`` / ``dd`` are left
empty instead of comparing today's price with a stale high.
"""
import datetime as dt
import time

from . import net

LIST_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
KLINE_URL = "https://www.binance.com/bapi/defi/v1/public/alpha-trade/klines"
K_GAP_MS = 3 * 86400 * 1000
DAY_MS = 86400 * 1000


def _f(v, d=None):
    try:
        x = float(v)
        return x if x == x else d
    except (TypeError, ValueError):
        return d


def fetch_tokens():
    """Full Binance Alpha token list (one request). Raises RuntimeError on failure."""
    js = net.get_json(LIST_URL)
    toks = (js or {}).get("data") or []
    if not toks:
        raise RuntimeError("failed to fetch Binance Alpha token list")
    return toks


def listing_year(t):
    return dt.datetime.fromtimestamp(int(t["listingTime"]) / 1000, dt.timezone.utc).year


def filter_year(toks, year):
    return [t for t in toks if t.get("listingTime") and t.get("alphaId") and listing_year(t) == int(year)]


def status(t):
    """live = still on Alpha; cex = moved to Binance spot; off = delisted."""
    if t.get("listingCex"):
        return "cex"
    if t.get("offline") or t.get("fullyDelisted"):
        return "off"
    return "live"


def daily_klines(alpha_id, limit=500):
    """[[t_ms, open, high, low, close, base_vol, quote_vol], ...] or None on failure."""
    js = net.get_json(KLINE_URL, {"symbol": alpha_id + "USDT", "interval": "1d", "limit": limit})
    if js is None:
        return None
    return [[int(x[0]), _f(x[1]), _f(x[2]), _f(x[3]), _f(x[4]), _f(x[5], 0), _f(x[7], 0)]
            for x in (js.get("data") or [])]


def klines_15m(alpha_id, listing_ms, limit=400):
    """15-minute candles starting from the listing day: [[t, o, h, l, c, quote_vol], ...]."""
    js = net.get_json(KLINE_URL, {"symbol": alpha_id + "USDT", "interval": "15m", "limit": limit,
                                  "startTime": listing_ms - listing_ms % DAY_MS})
    if js is None:
        return None
    return [[int(a[0]), float(a[1]), float(a[2]), float(a[3]), float(a[4]), float(a[7] or 0)]
            for a in js.get("data") or []]


def first_day_price(k):
    """Listing price from the first daily candle: VWAP if volume exists, else (H+L+C)/3."""
    if not k:
        return None
    f = k[0]
    if f[5]:
        return f[6] / f[5]
    if f[4]:
        return (f[2] + f[3] + f[4]) / 3
    return None


def listing_stats(t, k, now=None):
    """Compute one row of statistics for token ``t`` given its daily candles ``k``.

    Pure function (no network) so it can be unit tested.
    """
    now = time.time() if now is None else now
    lt = int(t["listingTime"])
    d0 = lt - lt % DAY_MS
    k = [x for x in (k or []) if x[0] >= d0 and x[2]]
    px = _f(t.get("price"))
    row = {
        "symbol": t.get("symbol"), "name": t.get("name"), "chain": t.get("chainName"),
        "address": t.get("contractAddress"), "listed_at": lt,
        "type": "stock" if t.get("stockState") else "crypto", "status": status(t),
        "price": px, "ref": None, "chg": None, "peak": None, "dd": None, "k_until": None,
    }
    ref = first_day_price(k)
    if not ref:
        return row
    row["ref"] = ref
    if px:
        row["chg"] = (px / ref - 1) * 100
    if now * 1000 - k[-1][0] > K_GAP_MS:
        row["k_until"] = k[-1][0]
        return row
    hi = max([x[2] for x in k] + ([px] if px else []))
    row["peak"] = (hi / ref - 1) * 100
    if px:
        row["dd"] = (px / hi - 1) * 100
    return row


def year_stats(year, with_klines=True, pace=0.2):
    """Fetch every Alpha token listed in ``year`` and compute listing stats (network)."""
    toks = filter_year(fetch_tokens(), year)
    rows = []
    for t in toks:
        k = daily_klines(t["alphaId"]) if with_klines else []
        rows.append(listing_stats(t, k or []))
        if with_klines and pace:
            time.sleep(pace)
    rows.sort(key=lambda r: r["listed_at"], reverse=True)
    return rows


def summarize(rows):
    """Median / share-up summary for crypto rows that have a change value."""
    import statistics as st

    vals = [r["chg"] for r in rows if r.get("type") == "crypto" and r.get("chg") is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "median_chg": round(st.median(vals), 1),
            "share_up": round(sum(v > 0 for v in vals) / len(vals) * 100, 1)}
