import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from backtest.artifacts import export_grid_results
from backtest.grid_search import (
    build_backtest_param_grid,
    format_robust_range_report,
    format_grid_report,
    run_portfolio_grid_backtest,
    run_single_grid_backtest,
    summarize_grid_robust_ranges,
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

    def test_summarize_and_format_robust_ranges(self) -> None:
        rows = [
            {
                "params": {
                    "fee_rate": 0.001,
                    "slippage_bps": 4.0,
                    "min_hold_days": 2,
                    "signal_confirm_days": 2,
                    "max_positions": 1,
                },
                "metrics": {"annual_return": 0.25, "total_return": 0.19, "max_drawdown": -0.12, "sharpe": 1.1},
            },
            {
                "params": {
                    "fee_rate": 0.001,
                    "slippage_bps": 8.0,
                    "min_hold_days": 3,
                    "signal_confirm_days": 2,
                    "max_positions": 1,
                },
                "metrics": {"annual_return": 0.24, "total_return": 0.18, "max_drawdown": -0.12, "sharpe": 1.0},
            },
            {
                "params": {
                    "fee_rate": 0.0015,
                    "slippage_bps": 12.0,
                    "min_hold_days": 5,
                    "signal_confirm_days": 1,
                    "max_positions": 2,
                },
                "metrics": {"annual_return": 0.20, "total_return": 0.16, "max_drawdown": -0.13, "sharpe": 0.9},
            },
        ]
        summary = summarize_grid_robust_ranges(rows, sort_by="annual_return", top_ratio=0.67, min_top_n=1)
        self.assertEqual(summary.get("total_count"), 3)
        self.assertEqual(summary.get("selected_count"), 3)
        self.assertIn("param_stats", summary)
        text = format_robust_range_report(summary)
        self.assertIn("参数稳健区间报告", text)
        self.assertIn("手续费率", text)

    def test_export_grid_results_with_robust_summary(self) -> None:
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
        robust = summarize_grid_robust_ranges(rows, sort_by="annual_return", top_ratio=1.0, min_top_n=1)
        with tempfile.TemporaryDirectory() as temp_dir:
            out = export_grid_results(
                mode="portfolio",
                symbols=["600519", "000001", "300750"],
                start="2025-02-28",
                end="2026-03-05",
                sort_by="annual_return",
                results=rows,
                output_dir=temp_dir,
                robust_summary=robust,
            )
            with open(out["json_path"], "r", encoding="utf-8") as f:
                payload = f.read()
            with open(out["md_path"], "r", encoding="utf-8") as f:
                md_text = f.read()
            self.assertIn("robust_summary", payload)
            self.assertIn("参数稳健区间报告", md_text)


if __name__ == "__main__":
    unittest.main()
