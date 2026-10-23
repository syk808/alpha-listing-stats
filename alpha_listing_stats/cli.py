# -*- coding: utf-8 -*-
"""Command line entry.

    python -m alpha_listing_stats year 2026 [--limit 20] [--json out.json]
    python -m alpha_listing_stats check SYMBOL [--exchanges Bybit,OKX]
"""
import argparse
import json
import sys

from . import alpha, first_open


def _fmt(v, suffix="%"):
    return "-" if v is None else f"{v:+.1f}{suffix}"


def cmd_year(args):
    rows = alpha.year_stats(args.year)
    rows = [r for r in rows if r["type"] == "crypto"]
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f"{'symbol':<12}{'chain':<10}{'status':<7}{'listing px':>14}{'now':>10}{'peak':>10}{'dd':>10}")
    for r in rows[: args.limit or None]:
        ref = "-" if r["ref"] is None else f"{r['ref']:.6g}"
        print(f"{str(r['symbol'])[:11]:<12}{str(r['chain'])[:9]:<10}{r['status']:<7}{ref:>14}"
              f"{_fmt(r['chg']):>10}{_fmt(r['peak']):>10}{_fmt(r['dd']):>10}")
    print("summary:", alpha.summarize(rows))


def cmd_check(args):
    sym = args.symbol.upper()
    toks = [t for t in alpha.fetch_tokens() if str(t.get("symbol") or "").upper() == sym and t.get("listingTime")]
    if not toks:
        print(f"{sym}: not found in Binance Alpha list")
        return 1
    exs = args.exchanges.split(",") if args.exchanges else None
    for t in toks:
        print(json.dumps(first_open.check_token(t, exs), ensure_ascii=False))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="alpha_listing_stats", description="Binance Alpha listing statistics")
    sub = p.add_subparsers(dest="cmd", required=True)
    y = sub.add_parser("year", help="listing price vs now for tokens listed in a year")
    y.add_argument("year", type=int)
    y.add_argument("--limit", type=int, default=30)
    y.add_argument("--json", help="also write rows to this JSON file")
    c = sub.add_parser("check", help="first-open check for one symbol (on-chain + 7 exchanges)")
    c.add_argument("symbol")
    c.add_argument("--exchanges", help="comma separated subset, e.g. Bybit,OKX")
    a = p.parse_args(argv)
    return (cmd_year if a.cmd == "year" else cmd_check)(a) or 0


if __name__ == "__main__":
    sys.exit(main())
