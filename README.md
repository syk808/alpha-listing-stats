# alpha-listing-stats

Statistics for tokens listed on **Binance Alpha**: listing price vs. now, peak run-up,
whether the token's *first ever* trade really happened on Alpha, and a 72-hour
entry/exit backtest grid.

币安 Alpha 上新代币统计小工具：算上线价（首日成交均价）、至今涨跌、最高涨幅和回撤；
核查一个币是不是**首开在 Alpha**（上线前链上和 7 家交易所有没有先成交）；
以及上线后 72 小时 15 分钟 K 线的买卖时点回测。

## Features / 功能

| Module | What it does | 说明 |
| --- | --- | --- |
| `alpha.py` | Fetch the Alpha token list, daily candles, compute listing price / change / peak / drawdown | 上线价 = 首日成交额 ÷ 成交量（首根开盘是占位价，不用） |
| `first_open.py` | First-open check: on-chain trades before listing + spot trades on Bybit, OKX, Gate, Bitget, MEXC, KuCoin, HTX | 上线前 2 小时以外链上成交 ≥ 50 笔、或别家交易所先有同价位成交 → 不算首开 |
| `backtest.py` | 72h grid backtest on 15m candles (4 entry times x 8 take-profit / stop-loss pairs, 0.5% cost per trade) | 同一根 K 线里止盈止损都碰到，按先止损算（保守） |
| `cli.py` | Command line | 命令行 |

## Install / 安装

```bash
git clone https://github.com/syk808/alpha-listing-stats.git
cd alpha-listing-stats
pip install -r requirements.txt
```

Python 3.8+. Only dependency: `requests`.

Optional proxy (see `.env.example`):

```bash
export ALPHA_STATS_PROXY=http://host:port   # optional
```

## Usage / 用法

Offline demo (no network):

```bash
python examples/offline_demo.py
```

Listing stats for every Alpha token listed in a year:

```bash
python -m alpha_listing_stats year 2026 --limit 20 --json rows.json
```

First-open check for one symbol:

```bash
python -m alpha_listing_stats check ABC
python -m alpha_listing_stats check ABC --exchanges Bybit,OKX,Gate
```

As a library:

```python
from alpha_listing_stats import alpha, first_open, backtest

toks = alpha.filter_year(alpha.fetch_tokens(), 2026)
t = toks[0]
row = alpha.listing_stats(t, alpha.daily_klines(t["alphaId"]))
print(row["symbol"], row["ref"], row["chg"], row["peak"])

print(first_open.check_token(t))

k = alpha.klines_15m(t["alphaId"], int(t["listingTime"]))
print(backtest.summary(k), backtest.grid([k])[:3])
```

## Data sources / 数据来源

All public endpoints, no API key required. 全部是公开接口，不需要任何密钥。

- Binance Alpha token list and candles (`www.binance.com/bapi/defi/...`)
- Binance Wallet on-chain 1h candles (`dquery.sintral.io`) for pre-listing on-chain trades
- DexScreener token pairs (fallback for chains without on-chain candles)
- Public spot kline endpoints of Bybit, OKX, Gate, Bitget, MEXC, KuCoin, HTX

These are unofficial / undocumented in some cases and may change or rate-limit
without notice. An exchange that answers 418/429 is skipped for 30 minutes.
部分接口不是官方文档接口，随时可能变更或限频；某家回 418/429 会暂停 30 分钟。

## Tests / 测试

```bash
python -m unittest -v
```

Tests run offline (network calls are replaced with a fake fetcher).

## Disclaimer / 免责声明

This project is for research and education only. **It is not investment advice.**
Data may be incomplete or wrong. Crypto assets are highly volatile; do your own research.

本项目仅用于研究和学习，**不构成任何投资建议**。数据可能不完整或有误，
加密资产波动极大，请自行判断、自担风险。

## License

MIT
