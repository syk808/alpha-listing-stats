import unittest

from alpha_listing_stats import alpha, backtest, first_open, net

DAY = 86400000
LT = 1767225600000 + 10 * 3600000   # 2026-01-01 10:00 UTC


def tok(**kw):
    t = {"alphaId": "ALPHA_1", "symbol": "ABC", "name": "Abc Protocol", "chainName": "BSC",
         "contractAddress": "0xabc", "listingTime": LT, "price": 2.0, "onlineTge": True}
    t.update(kw)
    return t


class TestListingStats(unittest.TestCase):
    def test_vwap_listing_price(self):
        k = [[LT - LT % DAY, 0.01, 1.5, 0.5, 1.2, 100.0, 100.0]]   # quote/base = 1.0
        self.assertAlmostEqual(alpha.first_day_price(k), 1.0)

    def test_hlc_fallback_without_volume(self):
        k = [[0, 1, 3, 1, 2, 0, 0]]
        self.assertAlmostEqual(alpha.first_day_price(k), 2.0)

    def test_row_peak_and_drawdown(self):
        d0 = LT - LT % DAY
        k = [[d0, 0.01, 1.5, 0.5, 1.2, 100.0, 100.0], [d0 + DAY, 1.2, 4.0, 1.1, 2.0, 1, 1]]
        r = alpha.listing_stats(tok(), k, now=(d0 + 2 * DAY) / 1000)
        self.assertAlmostEqual(r["ref"], 1.0)
        self.assertAlmostEqual(r["chg"], 100.0)
        self.assertAlmostEqual(r["peak"], 300.0)
        self.assertAlmostEqual(r["dd"], -50.0)

    def test_stale_klines_no_peak(self):
        d0 = LT - LT % DAY
        k = [[d0, 0.01, 1.5, 0.5, 1.2, 100.0, 100.0]]
        r = alpha.listing_stats(tok(listingCex=True), k, now=(d0 + 30 * DAY) / 1000)
        self.assertIsNone(r["peak"])
        self.assertEqual(r["status"], "cex")
        self.assertEqual(r["k_until"], d0)

    def test_summarize(self):
        rows = [{"type": "crypto", "chg": 10}, {"type": "crypto", "chg": -30}, {"type": "stock", "chg": 99}]
        self.assertEqual(alpha.summarize(rows), {"n": 2, "median_chg": -10.0, "share_up": 50.0})


class TestFirstOpen(unittest.TestCase):
    def test_not_launched_on_alpha(self):
        self.assertFalse(first_open.first_open(tok(onlineTge=False), {"cov": True, "trades": 0}, [])[0])

    def test_onchain_trades_before(self):
        pre = {"cov": True, "trades": 500, "first": LT - 5 * DAY}
        ok, why = first_open.first_open(tok(), pre, [])
        self.assertFalse(ok)
        self.assertIn("5 days", why)

    def test_old_pool_fallback(self):
        self.assertFalse(first_open.first_open(tok(), {"cov": False, "trades": 0, "pool_pre_h": 48}, [])[0])

    def test_cex_hit(self):
        ok, why = first_open.first_open(tok(), {"cov": True, "trades": 0}, [["Gate", 72, 1.1]])
        self.assertFalse(ok)
        self.assertIn("Gate", why)

    def test_clean(self):
        self.assertEqual(first_open.first_open(tok(), {"cov": True, "trades": 0}, []), (True, ""))

    def test_price_hit_ratio_window(self):
        bars = [(LT - 48 * 3600000, 1.0, 10.0)]
        self.assertEqual(first_open.price_hit("OKX", bars, 1.0, LT), ["OKX", 48, 1.0])
        self.assertIsNone(first_open.price_hit("OKX", bars, 100.0, LT))   # different coin, same symbol

    def test_cex_bars_gate_format(self):
        a, b = LT - 10 * DAY, LT - 3600000
        js = [[str((LT - DAY) // 1000), "500", "1.0", "1.1", "0.9", "1.0"]]
        self.assertEqual(first_open.cex_bars("Gate", js, a, b), [(LT - DAY, 1.0, 500.0)])

    def test_same_coin(self):
        self.assertTrue(first_open.same_coin(tok(), ("", {"0xabc"})))
        self.assertTrue(first_open.same_coin(tok(), ("Abc Protocol", set())))
        self.assertFalse(first_open.same_coin(tok(name="ABC"), ("Abc Protocol", set())))

    def test_pre_trades_with_fake_fetcher(self):
        cut = LT - 2 * 3600000
        rows = [[0, 0, 0, 1.0, 2.0, cut - 3600000, 80]]   # 80 trades before the cut

        net.set_fetcher(lambda url, params=None: ("ok", {"data": rows}))
        try:
            r = first_open.pre_trades("BSC", "0xabc", LT)
        finally:
            net.set_fetcher(None)
        self.assertEqual(r["trades"], 80)
        self.assertTrue(r["cov"])


class TestBacktest(unittest.TestCase):
    def series(self, closes):
        return [[i, c, c * 1.01, c * 0.99, c] for i, c in enumerate(closes)]

    def test_take_profit(self):
        k = self.series([1.0, 1.1, 1.6])
        pnl, j = backtest.simulate(k, 0, tp=50, sl=-20)
        self.assertAlmostEqual(pnl, 49.5)
        self.assertEqual(j, 2)

    def test_stop_loss_first(self):
        k = [[0, 1, 1, 1, 1], [1, 1, 2.0, 0.5, 1]]   # both touched in one candle
        self.assertAlmostEqual(backtest.simulate(k, 0, tp=50, sl=-20)[0], -20.5)

    def test_hold_to_end(self):
        k = self.series([1.0, 1.0, 1.2])
        self.assertAlmostEqual(backtest.simulate(k, 0)[0], 19.5)

    def test_grid_shape(self):
        g = backtest.grid([self.series([1.0] * 120)])
        self.assertEqual(len(g), len(backtest.ENTRIES) * len(backtest.EXITS))


if __name__ == "__main__":
    unittest.main()
