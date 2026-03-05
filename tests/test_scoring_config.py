import unittest

from app.config import AppConfig


class ScoringConfigTestCase(unittest.TestCase):
    def test_score_weights_normalized(self) -> None:
        cfg = AppConfig(
            score_weight_trend=2.0,
            score_weight_volume_price=2.0,
            score_weight_volatility=1.0,
            score_weight_turnover=1.0,
        )
        weights = cfg.score_weights
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)
        self.assertAlmostEqual(weights["trend"], 2 / 6, places=9)
        self.assertAlmostEqual(weights["volume_price"], 2 / 6, places=9)
        self.assertAlmostEqual(weights["volatility"], 1 / 6, places=9)
        self.assertAlmostEqual(weights["turnover"], 1 / 6, places=9)

    def test_score_weights_fallback_when_all_non_positive(self) -> None:
        cfg = AppConfig(
            score_weight_trend=-1.0,
            score_weight_volume_price=0.0,
            score_weight_volatility=-3.0,
            score_weight_turnover=0.0,
        )
        weights = cfg.score_weights
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)
        self.assertEqual(weights, {"trend": 0.35, "volume_price": 0.30, "volatility": 0.15, "turnover": 0.20})


if __name__ == "__main__":
    unittest.main()
