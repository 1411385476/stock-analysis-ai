import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from backtest.artifacts import export_grid_results
from backtest.grid_search import (
    build_backtest_param_grid,
    format_grid_report,
    run_portfolio_grid_backtest,
    run_single_grid_backtest,
)
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


class BacktestGridTestCase(unittest.TestCase):
    def test_build_backtest_param_grid(self) -> None:
        grid = build_backtest_param_grid(
            fee_rates=[0.001, 0.001],
            slippage_bps=[0.0, 8.0],
            min_hold_days=[1, 3],
            signal_confirm_days=[1],
            max_positions=[1],
        )
        self.assertEqual(len(grid), 4)

    def test_run_single_grid_backtest_and_format(self) -> None:
        df = add_indicators(_sample_ohlcv())
        grid = build_backtest_param_grid(
            fee_rates=[0.0, 0.002],
            slippage_bps=[0.0, 12.0],
            min_hold_days=[1],
            signal_confirm_days=[1],
            max_positions=[1],
        )
        results = run_single_grid_backtest(df=df, param_grid=grid, sort_by="annual_return")
        self.assertGreaterEqual(len(results), 1)
        text = format_grid_report(results=results, total_count=len(grid), sort_by="annual_return", top_n=3)
        self.assertIn("参数网格回测", text)
        self.assertIn("Top 3", text)

    def test_run_portfolio_grid_backtest(self) -> None:
        idx = pd.date_range("2024-01-01", periods=90, freq="B")

        def _mk_symbol(offset: float) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 120.0 + offset, len(idx)),
                    "MA20": np.full(len(idx), 2.0 + offset),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0 + offset),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_symbol(0.2), "BBB": _mk_symbol(0.5), "CCC": _mk_symbol(0.8)}
        grid = build_backtest_param_grid(
            fee_rates=[0.001],
            slippage_bps=[0.0, 8.0],
            min_hold_days=[1, 3],
            signal_confirm_days=[1],
            max_positions=[1, 2],
        )
        results = run_portfolio_grid_backtest(symbol_data=symbol_data, param_grid=grid, sort_by="annual_return")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("params", results[0])
        self.assertIn("metrics", results[0])

    def test_export_grid_results(self) -> None:
        rows = [
            {
                "params": {
                    "fee_rate": 0.001,
                    "slippage_bps": 8.0,
                    "min_hold_days": 3,
                    "signal_confirm_days": 2,
                    "max_positions": 2,
                },
                "metrics": {
                    "annual_return": 0.20,
                    "total_return": 0.15,
                    "max_drawdown": -0.12,
                    "sharpe": 1.0,
                    "calmar": 1.5,
                    "win_rate": 0.5,
                    "trades": 10,
                },
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            out = export_grid_results(
                mode="portfolio",
                symbols=["600519", "000001", "300750"],
                start="2025-02-28",
                end="2026-03-05",
                sort_by="annual_return",
                results=rows,
                output_dir=temp_dir,
            )
            self.assertTrue(os.path.exists(out["json_path"]))
            self.assertTrue(os.path.exists(out["csv_path"]))
            self.assertTrue(os.path.exists(out["md_path"]))


if __name__ == "__main__":
    unittest.main()
