"""Offline demo: no network needed. Run from the repo root:

    python examples/offline_demo.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpha_listing_stats import alpha, backtest, first_open  # noqa: E402

DAY = 86400000
LT = 1767225600000 + 10 * 3600000

token = {"alphaId": "ALPHA_DEMO", "symbol": "DEMO", "name": "Demo Token", "chainName": "BSC",
         "contractAddress": "0x0000000000000000000000000000000000000001", "listingTime": LT,
         "price": 0.18, "onlineTge": True}

# 1) listing price & peak from daily candles [t, o, h, l, c, base_vol, quote_vol]
d0 = LT - LT % DAY
daily = [[d0, 0.001, 0.15, 0.08, 0.12, 1_000_000, 110_000],
         [d0 + DAY, 0.12, 0.30, 0.11, 0.25, 900_000, 200_000],
         [d0 + 2 * DAY, 0.25, 0.26, 0.17, 0.18, 800_000, 150_000]]
row = alpha.listing_stats(token, daily, now=(d0 + 3 * DAY) / 1000)
print("listing price %.4f | now %+.1f%% | peak %+.1f%% | drawdown %+.1f%%"
      % (row["ref"], row["chg"], row["peak"], row["dd"]))

# 2) first-open verdict from already collected evidence
print("first open:", first_open.first_open(token, {"cov": True, "trades": 3}, cex=[]))
print("first open:", first_open.first_open(token, {"cov": True, "trades": 0}, cex=[["Gate", 96, 1.05]]))

# 3) 72h backtest grid on synthetic 15m candles
random.seed(7)
px, k = 0.1, []
for i in range(backtest.BARS):
    o = px
    px *= 1 + random.gauss(0.001, 0.03)
    k.append([i, o, max(o, px) * 1.01, min(o, px) * 0.99, px])
print("summary:", backtest.summary(k))
for g in backtest.grid([k])[:4]:
    print(g)
