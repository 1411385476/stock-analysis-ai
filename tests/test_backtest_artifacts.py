import json
import os
import tempfile
import unittest

from backtest.artifacts import export_backtest_record


def _sample_params() -> dict[str, float]:
    return {
        "fee_rate": 0.001,
        "slippage_bps": 8.0,
        "min_hold_days": 3,
        "signal_confirm_days": 2,
        "max_positions": 2,
    }


def _sample_metrics(total_return: float) -> dict[str, float]:
    return {
        "total_return": total_return,
        "annual_return": total_return * 0.8,
        "benchmark_return": 0.03,
        "max_drawdown": -0.08,
        "rolling_drawdown_63": -0.06,
        "rolling_drawdown_126": -0.07,
        "rolling_drawdown_252": -0.08,
        "sharpe": 1.1,
        "calmar": 1.5,
        "win_rate": 0.5,
        "trades": 10,
        "samples": 180,
        "fee_rate": 0.001,
        "slippage_bps": 8.0,
        "min_hold_days": 3,
        "signal_confirm_days": 2,
        "max_positions": 2,
    }


class BacktestArtifactsTestCase(unittest.TestCase):
    def test_export_backtest_record_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_backtest_record(
                mode="portfolio",
                symbols=["600519", "000001", "300750"],
                start="2025-02-28",
                end="2026-03-05",
                params=_sample_params(),
                metrics=_sample_metrics(total_return=0.1522),
                output_dir=temp_dir,
                compare_last=False,
            )

            self.assertTrue(os.path.exists(str(result["json_path"])))
            self.assertTrue(os.path.exists(str(result["md_path"])))
            self.assertIsNone(result["baseline_path"])
            self.assertIsNone(result["compare_text"])

            with open(str(result["json_path"]), "r", encoding="utf-8") as f:
                payload = json.load(f)

            self.assertEqual(payload["mode"], "portfolio")
            self.assertEqual(payload["period"]["start"], "2025-02-28")
            self.assertEqual(payload["period"]["end"], "2026-03-05")
            self.assertIn("target_hash", payload)
            self.assertIn("params_hash", payload)

    def test_export_backtest_record_compare_last(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = export_backtest_record(
                mode="single",
                symbols=["600519"],
                start="2025-02-28",
                end="2026-03-05",
                params=_sample_params(),
                metrics=_sample_metrics(total_return=0.10),
                output_dir=temp_dir,
                compare_last=True,
            )
            second = export_backtest_record(
                mode="single",
                symbols=["600519"],
                start="2025-02-28",
                end="2026-03-05",
                params=_sample_params(),
                metrics=_sample_metrics(total_return=0.12),
                output_dir=temp_dir,
                compare_last=True,
            )

            self.assertIsNone(first["baseline_path"])
            self.assertIsNotNone(second["baseline_path"])
            self.assertTrue(os.path.exists(str(second["baseline_path"])))
            self.assertIsNotNone(second["compare_text"])
            self.assertIn("策略总收益", str(second["compare_text"]))


if __name__ == "__main__":
    unittest.main()
