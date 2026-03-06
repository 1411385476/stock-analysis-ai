import json
import os
import tempfile
import unittest

from backtest.artifacts import export_backtest_record, export_rebalance_log, export_walk_forward_record


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

    def test_export_walk_forward_record_compare_last(self) -> None:
        wf_result_a = {
            "windows_total": 3,
            "windows_valid": 3,
            "summary": {
                "avg_total_return": 0.08,
                "avg_annual_return": 0.12,
                "worst_drawdown": -0.10,
            },
            "segment_comparison": {
                "outperform_rate": 0.66,
                "avg_excess_total_return": 0.03,
            },
            "windows": [],
        }
        wf_result_b = {
            "windows_total": 3,
            "windows_valid": 3,
            "summary": {
                "avg_total_return": 0.10,
                "avg_annual_return": 0.15,
                "worst_drawdown": -0.09,
            },
            "segment_comparison": {
                "outperform_rate": 1.0,
                "avg_excess_total_return": 0.05,
            },
            "windows": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            first = export_walk_forward_record(
                symbols=["600519", "000001", "300750"],
                start="2025-02-28",
                end="2026-03-05",
                config={"train_days": 126, "test_days": 63, "step_days": 21, "sort_by": "annual_return"},
                result=wf_result_a,
                output_dir=temp_dir,
                compare_last=True,
            )
            second = export_walk_forward_record(
                symbols=["600519", "000001", "300750"],
                start="2025-02-28",
                end="2026-03-05",
                config={"train_days": 126, "test_days": 63, "step_days": 21, "sort_by": "annual_return"},
                result=wf_result_b,
                output_dir=temp_dir,
                compare_last=True,
            )

            self.assertIsNone(first["baseline_path"])
            self.assertIsNotNone(second["baseline_path"])
            self.assertTrue(os.path.exists(str(second["baseline_path"])))
            self.assertIsNotNone(second["compare_text"])
            self.assertIn("Walk-forward 对比", str(second["compare_text"]))
            self.assertTrue(os.path.exists(str(second["json_path"])))
            self.assertTrue(os.path.exists(str(second["md_path"])))

    def test_export_rebalance_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = export_rebalance_log(
                mode="portfolio",
                symbols=["600519", "000001"],
                start="2025-03-01",
                end="2026-03-06",
                params={"fee_rate": 0.001},
                records=[
                    {
                        "date": "2026-03-03",
                        "symbol": "600519",
                        "action": "buy",
                        "reason": "signal_entry",
                        "from_weight": 0.0,
                        "to_weight": 0.5,
                        "delta_weight": 0.5,
                        "price": 1399.0,
                        "rebalance_frequency": "weekly",
                        "is_rebalance_day": "1",
                    }
                ],
                output_dir=temp_dir,
            )
            self.assertTrue(os.path.exists(out["csv_path"]))
            self.assertTrue(os.path.exists(out["md_path"]))
            with open(out["md_path"], "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("signal_entry", content)


if __name__ == "__main__":
    unittest.main()
