import unittest

import pandas as pd

from value.investing import build_value_scores, build_value_thesis


class ValueInvestingTestCase(unittest.TestCase):
    def test_build_value_scores_ranks_low_valuation_higher(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "symbol": "600000",
                    "name": "A",
                    "pe_ttm": 8.0,
                    "pb": 1.2,
                    "total_market_cap": 300_000_000_000,
                    "pct_change_60d": 2.0,
                },
                {
                    "symbol": "600001",
                    "name": "B",
                    "pe_ttm": 40.0,
                    "pb": 9.0,
                    "total_market_cap": 100_000_000_000,
                    "pct_change_60d": 25.0,
                },
            ]
        )
        out = build_value_scores(df)
        self.assertIn("value_score_total", out.columns)
        self.assertIn("value_reason", out.columns)
        self.assertEqual(str(out.iloc[0]["symbol"]), "600000")
        self.assertGreater(float(out.iloc[0]["value_score_total"]), float(out.iloc[1]["value_score_total"]))

    def test_build_value_thesis_contains_forecast(self) -> None:
        profile = {
            "pe": 16.0,
            "pb": 2.2,
            "roe": 0.22,
            "gross_margin": 0.48,
            "dividend_yield": 0.03,
            "debt_to_equity": 40.0,
            "free_cashflow": 1_000_000.0,
            "ret_1y": 0.20,
            "realized_vol": 0.22,
            "max_drawdown": -0.18,
            "news": [{"title": "公司分红提升"}],
        }
        thesis = build_value_thesis(profile)
        self.assertIn("score_total", thesis)
        self.assertIn("conclusion", thesis)
        self.assertIn("forecast", thesis)
        forecast = thesis["forecast"]
        total_prob = int(forecast["bull_pct"]) + int(forecast["base_pct"]) + int(forecast["bear_pct"])
        self.assertEqual(total_prob, 100)
        self.assertTrue((thesis.get("reasons") or []))


if __name__ == "__main__":
    unittest.main()
