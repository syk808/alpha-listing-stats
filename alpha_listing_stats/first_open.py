# -*- coding: utf-8 -*-
"""Was the token's *first ever* trade on Binance Alpha?

A token only counts as a "first open" on Alpha when all of these hold:

1. The Alpha list marks it ``onlineTge`` or ``onlineAirdrop`` (launched on Alpha,
   not added later).
2. On-chain: fewer than ``PRE_TRADES`` trades earlier than 2 hours before the
   Alpha listing (Binance Wallet 1h on-chain candles, which include DEX and
   bonding-curve launchpads). For chains that endpoint does not cover, fall
   back to the earliest DexScreener pool: created more than 12 hours before
   listing -> not first open.
3. Other exchanges: none of Bybit / OKX / Gate / Bitget / MEXC / KuCoin / HTX
   traded a same-symbol USDT spot pair between 10 days and 1 hour before
   listing, at a price within 0.2x-5x of the Alpha opening price (old tokens
   that migrated to a new contract and then launched on Alpha). KuCoin / HTX
   additionally require contract address or full-name match because of
   symbol collisions.
"""
import threading
import time

from . import net
from .alpha import KLINE_URL

PRE_TRADES = 50
POOL_PRE_H = 12
DQ_URL = "https://dquery.sintral.io/u-kline/v1/k-line/candles"
DQ_PF = {"BSC": "bsc", "Base": "base", "Ethereum": "ethereum", "Arbitrum": "arbitrum", "Solana": "solana"}
DS_CHAIN = {"BSC": "bsc", "Base": "base", "Ethereum": "ethereum", "Arbitrum": "arbitrum", "Solana": "solana",
            "Sui": "sui", "Sonic": "sonic", "TRON": "tron", "Linea": "linea", "Robinhood": "robinhood"}
H_MS = 3600000


# ── on-chain ──────────────────────────────────────────────────────────────

def pool_fallback(chain, addr, lt):
    """Earliest DexScreener pool. Returns {cov: False, trades: 0, pool_pre_h}; None = request failed."""
    netw = DS_CHAIN.get(chain)
    if not netw or not addr:
        return {"cov": False, "trades": 0, "pool_pre_h": None}
    js = net.get_json(f"https://api.dexscreener.com/token-pairs/v1/{netw}/{addr}")
    if js is None:
        return None
    ts = sorted(p["pairCreatedAt"] for p in js if isinstance(p, dict) and p.get("pairCreatedAt"))
    return {"cov": False, "trades": 0, "pool_pre_h": round((lt - ts[0]) / H_MS, 1) if ts else None}


def pre_trades(chain, addr, lt):
    """On-chain trades earlier than 2h before listing.

    Returns {cov, trades[, vol, first]} or None (request failed, try later).
    cov=False means the on-chain candle endpoint has no data for this token at all.
    """
    pf = DQ_PF.get(chain)
    if not addr:
        return {"cov": False, "trades": 0, "pool_pre_h": None}
    if not pf:
        return pool_fallback(chain, addr, lt)
    cut = lt - 2 * H_MS
    js = net.get_json(DQ_URL, {"address": addr, "interval": "1h", "platform": pf, "limit": 1000, "to": cut})
    if js is None:
        return None
    pre = [k for k in js.get("data") or [] if int(k[5]) < cut and float(k[6] or 0) > 0]
    if pre:
        return {"cov": True, "trades": int(sum(float(k[6]) for k in pre)),
                "vol": round(sum(float(k[4]) * float(k[3]) for k in pre)), "first": min(int(k[5]) for k in pre)}
    after = net.get_json(DQ_URL, {"address": addr, "interval": "1h", "platform": pf, "limit": 5, "to": lt + 6 * H_MS})
    if after is None:
        return None
    if after.get("data"):
        return {"cov": True, "trades": 0}
    return pool_fallback(chain, addr, lt)


# ── other exchanges ───────────────────────────────────────────────────────

def _htx_params(S, a, b):
    """HTX only returns the latest 2000 candles: hourly if reachable (~83 days), else daily."""
    hourly = time.time() * 1000 - a < 1990 * H_MS
    return ("https://api.huobi.pro/market/history/kline",
            {"symbol": S.lower() + "usdt", "period": "60min" if hourly else "1day", "size": 2000})


CEX_SPOT = {
    "Bybit": lambda S, a, b: ("https://api.bybit.com/v5/market/kline", {"category": "spot", "symbol": S + "USDT", "interval": "60", "start": a, "end": b, "limit": 1000}),
    "OKX": lambda S, a, b: ("https://www.okx.com/api/v5/market/history-candles", {"instId": S + "-USDT", "bar": "1H", "after": b, "limit": 100}),
    "Gate": lambda S, a, b: ("https://api.gateio.ws/api/v4/spot/candlesticks", {"currency_pair": S + "_USDT", "interval": "1h", "from": a // 1000, "to": b // 1000}),
    "Bitget": lambda S, a, b: ("https://api.bitget.com/api/v2/spot/market/history-candles", {"symbol": S + "USDT", "granularity": "1h", "endTime": b, "limit": 200}),
    "MEXC": lambda S, a, b: ("https://api.mexc.com/api/v3/klines", {"symbol": S + "USDT", "interval": "60m", "startTime": a, "endTime": b, "limit": 1000}),
    "KuCoin": lambda S, a, b: ("https://api.kucoin.com/api/v1/market/candles", {"type": "1hour", "symbol": S + "-USDT", "startAt": a // 1000, "endAt": b // 1000}),
    "HTX": _htx_params,
}
CEX_IDENTITY = ("KuCoin", "HTX")
CEX_GAP = 0.2              # min seconds between two requests to the same exchange
CEX_STOP_SEC = 1800        # exchange answered 418/429 -> skip it for 30 minutes
_PACE, _STOP = {}, {}
_LOCKS = {ex: threading.Lock() for ex in CEX_SPOT}
_HTX_NAMES = {"t": 0.0, "d": None}


def _cex_get(ex, url, params):
    """(state, json): ok / fail (network, 5xx) / stop (rate limited, paused)."""
    if _STOP.get(ex, 0) > time.time():
        return "stop", None
    with _LOCKS.setdefault(ex, threading.Lock()):
        wait = _PACE.get(ex, 0) + CEX_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _PACE[ex] = time.time()
        state, js = net.fetch(url, params)
    if state == "stop":
        _STOP[ex] = time.time() + CEX_STOP_SEC
    return state, js


def cex_bars(ex, js, a, b):
    """Normalise each exchange's candles to [(t_ms, close, quote_volume)] within [a, b) with volume > 0."""
    try:
        if ex == "Bybit":
            L = [(int(x[0]), float(x[4]), float(x[6])) for x in ((js or {}).get("result") or {}).get("list") or []]
        elif ex == "OKX":
            L = [(int(x[0]), float(x[4]), float(x[7])) for x in (js or {}).get("data") or []]
        elif ex == "Bitget":
            L = [(int(x[0]), float(x[4]), float(x[6])) for x in (js or {}).get("data") or []]
        elif ex == "Gate":
            L = [(int(x[0]) * 1000, float(x[2]), float(x[1])) for x in (js if isinstance(js, list) else [])]
        elif ex == "KuCoin":
            d = js.get("data") if isinstance(js, dict) else None
            L = [(int(x[0]) * 1000, float(x[2]), float(x[6])) for x in (d if isinstance(d, list) else [])]
        elif ex == "HTX":
            d = js.get("data") if isinstance(js, dict) else None
            d = d if isinstance(d, list) else []
            ids = sorted(int(x["id"]) for x in d)
            step = (ids[1] - ids[0]) * 1000 if len(ids) > 1 else H_MS
            L = [(int(x["id"]) * 1000, float(x["close"]), float(x.get("vol") or 0)) for x in d
                 if step <= H_MS or int(x["id"]) * 1000 + step <= b]
        else:
            L = [(int(x[0]), float(x[4]), float(x[7])) for x in (js if isinstance(js, list) else [])]
    except (TypeError, ValueError, IndexError, KeyError, AttributeError):
        return []
    return [x for x in L if a <= x[0] < b and x[2] > 0]


def _norm(x):
    return "".join(c for c in str(x or "").lower() if c.isalnum())


def _cex_meta(ex, S):
    """(full_name, {contract addresses}) registered on the exchange; None = could not fetch."""
    if ex == "KuCoin":
        st_, js = _cex_get(ex, "https://api.kucoin.com/api/v3/currencies/" + S, None)
        if st_ != "ok":
            return None
        d = js.get("data") if isinstance(js, dict) else None
        if not isinstance(d, dict):
            return "", set()
        return d.get("fullName") or "", {str(c.get("contractAddress") or "").lower()
                                         for c in d.get("chains") or [] if c.get("contractAddress")}
    if ex == "HTX":
        if _HTX_NAMES["d"] is None or time.time() - _HTX_NAMES["t"] > 6 * 3600:
            st_, js = _cex_get(ex, "https://api.huobi.pro/v1/settings/common/currencys", None)
            if st_ != "ok" or not isinstance(js, dict) or not isinstance(js.get("data"), list):
                return None
            _HTX_NAMES.update(t=time.time(), d={str(x.get("name") or "").lower(): x.get("fn") or "" for x in js["data"]})
        st_, js = _cex_get(ex, "https://api.huobi.pro/v2/reference/currencies", {"currency": S.lower()})
        if st_ != "ok":
            return None
        chains = [c for x in (js or {}).get("data") or [] for c in x.get("chains") or []] if isinstance(js, dict) else []
        return _HTX_NAMES["d"].get(S.lower(), ""), {str(c.get("contractAddress") or "").lower()
                                                     for c in chains if c.get("contractAddress")}
    return None


def same_coin(t, meta):
    """Exchange-registered coin == Alpha token? Contract address match, or full-name match."""
    full, addrs = meta
    addr = str(t.get("contractAddress") or "").lower()
    if addr and addr in addrs:
        return True
    a, b, sym = _norm(t.get("name")), _norm(full), _norm(t.get("symbol"))
    if not a or not b or a == sym:
        return False
    return len(min(a, b, key=len)) >= 3 and (a in b or b in a)


def price_hit(ex, bars, alpha_px, lt):
    """[exchange, hours_earlier, price_ratio] if the pre-listing trades look like the same coin, else None."""
    if not bars or not alpha_px:
        return None
    ratio = max(bars)[1] / alpha_px
    if 0.2 < ratio < 5:
        return [ex, round((lt - min(x[0] for x in bars)) / H_MS), round(ratio, 2)]
    return None


def cex_pre_check(t, exchanges=None):
    """Check other exchanges for spot trades before the Alpha listing.

    Returns (hits, checked) or None when the Alpha opening price is unavailable.
    hits = [[exchange, hours_earlier, price_ratio], ...];
    checked = exchanges that actually answered (failed / paused ones are retried next time).
    """
    lt = int(t["listingTime"])
    k = net.get_json(KLINE_URL, {"symbol": t["alphaId"] + "USDT", "interval": "15m",
                                 "startTime": lt - lt % 86400000, "limit": 200})
    bars = [x for x in (k or {}).get("data") or [] if int(x[0]) >= lt - 15 * 60000]
    if not bars:
        return None
    px = float(bars[0][4])
    S = str(t.get("symbol") or "").upper()
    a, b = lt - 10 * 86400000, lt - H_MS
    hits, checked = [], []
    for ex in (exchanges or list(CEX_SPOT)):
        url, params = CEX_SPOT[ex](S, a, b)
        state, js = _cex_get(ex, url, params)
        if state != "ok":
            continue
        hit = price_hit(ex, cex_bars(ex, js, a, b), px, lt)
        if hit and ex in CEX_IDENTITY:
            meta = _cex_meta(ex, S)
            if meta is None:
                continue
            if not same_coin(t, meta):
                hit = None
        checked.append(ex)
        if hit:
            hits.append(hit)
    return hits, checked


# ── verdict ───────────────────────────────────────────────────────────────

def first_open(t, pre, cex=None):
    """(is_first_open, reason). ``pre`` from pre_trades(); ``cex`` = hits list from cex_pre_check()
    ([] = checked, nothing found; None = not checked yet)."""
    if not (t.get("onlineTge") or t.get("onlineAirdrop")):
        return False, "not launched on Alpha (added later)"
    if pre is None:
        return False, "on-chain history not fetched yet"
    if pre.get("cov") and pre.get("trades", 0) >= PRE_TRADES:
        days = (int(t["listingTime"]) - pre["first"]) / 86400000 if pre.get("first") else 0
        return False, f"traded on-chain {days:.0f} days before Alpha ({pre['trades']:,} trades)"
    if not pre.get("cov") and (pre.get("pool_pre_h") or 0) > POOL_PRE_H:
        return False, f"on-chain pool existed {pre['pool_pre_h'] / 24:.0f} days before Alpha"
    if cex is None:
        return False, "other exchanges not checked yet"
    if cex:
        ex, h, _ = cex[0]
        return False, f"traded on {ex} {h / 24:.0f} days before Alpha ({', '.join(x[0] for x in cex)})"
    return True, ""


def check_token(t, exchanges=None):
    """Full network check for one Alpha token dict. Returns dict with verdict and evidence."""
    lt = int(t["listingTime"])
    pre = pre_trades(t.get("chainName"), t.get("contractAddress"), lt)
    ok, why = first_open(t, pre, cex=[])
    cex = None
    if ok:
        r = cex_pre_check(t, exchanges)
        cex = None if r is None else r[0]
        ok, why = first_open(t, pre, cex)
    return {"symbol": t.get("symbol"), "first_open": ok, "reason": why, "pre": pre, "cex": cex}
