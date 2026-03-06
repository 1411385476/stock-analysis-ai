import unittest

import numpy as np
import pandas as pd

from backtest.walk_forward import (
    build_walk_forward_windows,
    format_walk_forward_report,
    run_portfolio_walk_forward,
)


def _mk_symbol(rows: int = 320, drift: float = 0.0) -> pd.DataFrame:
    idx = pd.date_range("2023-01-02", periods=rows, freq="B")
    close = np.linspace(80.0 + drift, 140.0 + drift, rows)
    return pd.DataFrame(
        {
            "Close": close,
            "MA20": np.full(rows, 2.0 + drift / 100.0),
            "MA60": np.full(rows, 1.0),
            "MACD": np.full(rows, 1.0 + drift / 200.0),
            "MACD_SIGNAL": np.zeros(rows),
            "RSI14": np.full(rows, 50.0),
        },
        index=idx,
    )


class WalkForwardTestCase(unittest.TestCase):
    def test_build_walk_forward_windows(self) -> None:
        idx = pd.date_range("2024-01-01", periods=260, freq="B")
        windows = build_walk_forward_windows(idx, train_days=120, test_days=60, step_days=30)
        self.assertGreaterEqual(len(windows), 2)
        first = windows[0]
        self.assertIn("train_start", first)
        self.assertIn("test_end", first)

    def test_run_portfolio_walk_forward_and_format(self) -> None:
        symbol_data = {
            "AAA": _mk_symbol(drift=0.0),
            "BBB": _mk_symbol(drift=5.0),
            "CCC": _mk_symbol(drift=-3.0),
        }
        result = run_portfolio_walk_forward(
            symbol_data=symbol_data,
            base_params={
                "fee_rate": 0.001,
                "slippage_bps": 8,
                "min_hold_days": 3,
                "signal_confirm_days": 2,
                "max_positions": 2,
                "rebalance_frequency": "weekly",
                "rebalance_weekday": 2,
            },
            train_days=120,
            test_days=60,
            step_days=20,
        )
        self.assertIn("windows_total", result)
        self.assertIn("windows_valid", result)
        self.assertGreater(result.get("windows_total", 0), 0)
        self.assertGreater(result.get("windows_valid", 0), 0)
        summary = result.get("summary") or {}
        self.assertIn("avg_annual_return", summary)
        segment = result.get("segment_comparison") or {}
        self.assertIn("outperform_rate", segment)
        first_window = (result.get("windows") or [])[0]
        params = first_window.get("params") or {}
        self.assertEqual(str(params.get("rebalance_frequency", "")), "weekly")
        self.assertEqual(int(params.get("rebalance_weekday", 0)), 2)

        text = format_walk_forward_report(result)
        self.assertIn("Walk-forward评估", text)
        self.assertIn("窗口数量", text)
        self.assertIn("分段对比", text)

    def test_walk_forward_insufficient_samples_message(self) -> None:
        short_symbol_data = {
            "AAA": _mk_symbol(rows=186, drift=0.0),
            "BBB": _mk_symbol(rows=186, drift=5.0),
            "CCC": _mk_symbol(rows=186, drift=-3.0),
        }
        result = run_portfolio_walk_forward(
            symbol_data=short_symbol_data,
            base_params={"fee_rate": 0.001, "max_positions": 2},
            train_days=126,
            test_days=63,
            step_days=21,
        )
        self.assertEqual(result.get("windows_total", 0), 0)
        self.assertEqual(result.get("available_days", 0), 186)
        self.assertEqual(result.get("required_days", 0), 189)
        text = format_walk_forward_report(result)
        self.assertIn("当前=186 / 需求=189", text)
        self.assertIn("样本不足", text)


if __name__ == "__main__":
    unittest.main()
