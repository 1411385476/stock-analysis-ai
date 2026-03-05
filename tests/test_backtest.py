import unittest

import numpy as np
import pandas as pd

from backtest.engine import format_backtest_report, run_backtest
from factors.indicators import add_indicators


def _sample_ohlcv(rows: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=rows, freq="B")
    trend = np.linspace(20, 60, rows)
    cycle = np.sin(np.linspace(0, 20, rows)) * 2.5
    close = trend + cycle
    open_ = close + 0.1
    high = close + 0.8
    low = close - 0.8
    volume = np.full(rows, 2_000_000.0)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


class BacktestTestCase(unittest.TestCase):
    def test_run_backtest_returns_metrics(self) -> None:
        df = add_indicators(_sample_ohlcv())
        metrics = run_backtest(df, fee_rate=0.001)
        expected = {
            "total_return",
            "annual_return",
            "max_drawdown",
            "sharpe",
            "win_rate",
            "trades",
            "benchmark_return",
            "samples",
        }
        self.assertTrue(expected.issubset(metrics.keys()))
        self.assertGreater(metrics["samples"], 30)

    def test_format_backtest_report_empty_metrics(self) -> None:
        self.assertEqual(format_backtest_report({}), "回测结果: 数据不足或指标缺失，无法回测。")


if __name__ == "__main__":
    unittest.main()
