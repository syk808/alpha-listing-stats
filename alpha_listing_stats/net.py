# -*- coding: utf-8 -*-
"""Tiny HTTP layer.

Proxy: optional, read from the ALPHA_STATS_PROXY environment variable
(e.g. ``http://host:port``). ``requests`` also honours the standard
HTTPS_PROXY / HTTP_PROXY variables on its own.

Every function that talks to the network goes through ``get_json`` so tests
can swap it out (see ``set_fetcher``).
"""
import os
import time

UA = {"User-Agent": "Mozilla/5.0 (alpha-listing-stats)"}
TIMEOUT = 20


def _proxies():
    p = os.environ.get("ALPHA_STATS_PROXY", "").strip()
    return {"http": p, "https": p} if p else None


def _requests_get(url, params=None, retries=2):
    """Return (status, json_or_None). status: 'ok' | 'fail' | 'stop' (rate limited)."""
    import requests

    for i in range(retries):
        try:
            r = requests.get(url, params=params, proxies=_proxies(), headers=UA, timeout=TIMEOUT)
        except Exception:
            time.sleep(1 + i)
            continue
        if r.status_code in (418, 429):
            return "stop", None
        if r.status_code >= 500:
            time.sleep(1 + i)
            continue
        try:
            return "ok", r.json()
        except ValueError:
            return "ok", None
    return "fail", None


_FETCHER = _requests_get


def set_fetcher(fn):
    """Replace the network function (tests / custom caching). fn(url, params) -> (status, json)."""
    global _FETCHER
    _FETCHER = fn or _requests_get


def fetch(url, params=None):
    """(status, json). 4xx responses count as 'ok' with whatever JSON came back."""
    return _FETCHER(url, params)


def get_json(url, params=None):
    """JSON on success, None otherwise."""
    st, js = fetch(url, params)
    return js if st == "ok" else None
