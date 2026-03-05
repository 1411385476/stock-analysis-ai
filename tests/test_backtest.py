import unittest

import numpy as np
import pandas as pd

from backtest.engine import (
    format_backtest_report,
    format_portfolio_backtest_report,
    run_backtest,
    run_portfolio_backtest,
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


class BacktestTestCase(unittest.TestCase):
    def test_run_backtest_returns_metrics(self) -> None:
        df = add_indicators(_sample_ohlcv())
        metrics = run_backtest(df, fee_rate=0.001)
        expected = {
            "total_return",
            "annual_return",
            "max_drawdown",
            "calmar",
            "sharpe",
            "win_rate",
            "trades",
            "benchmark_return",
            "samples",
            "fee_rate",
            "slippage_bps",
            "min_hold_days",
            "signal_confirm_days",
            "rolling_drawdown_63",
            "rolling_drawdown_126",
            "rolling_drawdown_252",
            "year_count",
        }
        self.assertTrue(expected.issubset(metrics.keys()))
        self.assertGreater(metrics["samples"], 30)

    def test_slippage_reduces_total_return(self) -> None:
        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        df = pd.DataFrame(
            {
                "Close": np.linspace(100.0, 140.0, len(idx)),
                "MA20": np.full(len(idx), 2.0),
                "MA60": np.full(len(idx), 1.0),
                "MACD": np.full(len(idx), 1.0),
                "MACD_SIGNAL": np.zeros(len(idx)),
                "RSI14": np.full(len(idx), 50.0),
            },
            index=idx,
        )
        base = run_backtest(df, fee_rate=0.0, slippage_bps=0.0)
        with_slippage = run_backtest(df, fee_rate=0.0, slippage_bps=20.0)
        self.assertGreater(base["trades"], 0)
        self.assertGreater(base["total_return"], with_slippage["total_return"])

    def test_min_hold_days_reduces_trade_count(self) -> None:
        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        alternating = np.arange(len(idx)) % 2 == 0
        df = pd.DataFrame(
            {
                "Close": 100.0 + np.sin(np.linspace(0, 20, len(idx))),
                "MA20": np.where(alternating, 2.0, 1.0),
                "MA60": np.where(alternating, 1.0, 2.0),
                "MACD": np.where(alternating, 1.0, -1.0),
                "MACD_SIGNAL": np.zeros(len(idx)),
                "RSI14": np.where(alternating, 50.0, 80.0),
            },
            index=idx,
        )
        base = run_backtest(df, min_hold_days=1, signal_confirm_days=1, fee_rate=0.0)
        constrained = run_backtest(df, min_hold_days=5, signal_confirm_days=1, fee_rate=0.0)
        self.assertGreater(base["trades"], constrained["trades"])

    def test_signal_confirm_days_filters_noise(self) -> None:
        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        alternating = np.arange(len(idx)) % 2 == 0
        df = pd.DataFrame(
            {
                "Close": 100.0 + np.sin(np.linspace(0, 20, len(idx))),
                "MA20": np.where(alternating, 2.0, 1.0),
                "MA60": np.where(alternating, 1.0, 2.0),
                "MACD": np.where(alternating, 1.0, -1.0),
                "MACD_SIGNAL": np.zeros(len(idx)),
                "RSI14": np.where(alternating, 50.0, 80.0),
            },
            index=idx,
        )
        base = run_backtest(df, min_hold_days=1, signal_confirm_days=1, fee_rate=0.0)
        confirmed = run_backtest(df, min_hold_days=1, signal_confirm_days=2, fee_rate=0.0)
        self.assertGreater(base["trades"], confirmed["trades"])

    def test_format_backtest_report_empty_metrics(self) -> None:
        self.assertEqual(format_backtest_report({}), "回测结果: 数据不足或指标缺失，无法回测。")

    def test_format_backtest_report_contains_extended_metrics(self) -> None:
        df = add_indicators(_sample_ohlcv())
        metrics = run_backtest(df, fee_rate=0.001)
        text = format_backtest_report(metrics)
        self.assertIn("卡玛比率", text)
        self.assertIn("滚动回撤", text)
        self.assertIn("年度分解", text)

    def test_portfolio_backtest_enforces_max_positions(self) -> None:
        idx = pd.date_range("2024-01-01", periods=90, freq="B")

        def _mk_symbol(strength: float) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 120.0 + strength, len(idx)),
                    "MA20": np.full(len(idx), 2.0 + strength),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0 + strength),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {
            "AAA": _mk_symbol(0.8),
            "BBB": _mk_symbol(0.5),
            "CCC": _mk_symbol(0.2),
        }
        m1 = run_portfolio_backtest(symbol_data, max_positions=1, fee_rate=0.0)
        m2 = run_portfolio_backtest(symbol_data, max_positions=2, fee_rate=0.0)

        self.assertGreater(m1["symbols"], 1)
        self.assertLessEqual(m1["max_active_positions"], 1.0)
        self.assertLessEqual(m2["max_active_positions"], 2.0)
        self.assertGreater(m2["avg_active_positions"], m1["avg_active_positions"])

    def test_portfolio_backtest_respects_costs(self) -> None:
        idx = pd.date_range("2024-01-01", periods=90, freq="B")
        alternating = np.arange(len(idx)) % 2 == 0

        def _mk_choppy() -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": 100.0 + np.sin(np.linspace(0, 18, len(idx))),
                    "MA20": np.where(alternating, 2.0, 1.0),
                    "MA60": np.where(alternating, 1.0, 2.0),
                    "MACD": np.where(alternating, 1.0, -1.0),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.where(alternating, 50.0, 80.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_choppy(), "BBB": _mk_choppy()}
        base = run_portfolio_backtest(symbol_data, fee_rate=0.0, slippage_bps=0.0, max_positions=1)
        costly = run_portfolio_backtest(symbol_data, fee_rate=0.002, slippage_bps=15.0, max_positions=1)
        self.assertGreater(base["trades"], 0)
        self.assertGreater(base["total_return"], costly["total_return"])

    def test_format_portfolio_backtest_report_empty_metrics(self) -> None:
        self.assertEqual(
            format_portfolio_backtest_report({}),
            "组合回测结果: 数据不足或指标缺失，无法回测。",
        )

    def test_format_portfolio_backtest_report_contains_extended_metrics(self) -> None:
        idx = pd.date_range("2024-01-01", periods=90, freq="B")

        def _mk_symbol() -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 130.0, len(idx)),
                    "MA20": np.full(len(idx), 2.0),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        metrics = run_portfolio_backtest({"AAA": _mk_symbol(), "BBB": _mk_symbol()}, max_positions=1)
        text = format_portfolio_backtest_report(metrics)
        self.assertIn("卡玛比率", text)
        self.assertIn("滚动回撤", text)
        self.assertIn("年度分解", text)


if __name__ == "__main__":
    unittest.main()
