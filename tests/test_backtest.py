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

    def test_portfolio_backtest_stop_loss_triggers_risk_exits(self) -> None:
        idx = pd.date_range("2024-01-01", periods=90, freq="B")

        def _mk_downtrend() -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 70.0, len(idx)),
                    "MA20": np.full(len(idx), 2.0),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_downtrend()}
        no_risk = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1, stop_loss_pct=0.0)
        with_stop = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1, stop_loss_pct=0.05)
        self.assertEqual(no_risk.get("risk_exits", 0.0), 0.0)
        self.assertGreater(with_stop.get("risk_exits", 0.0), 0.0)

    def test_portfolio_backtest_drawdown_circuit_triggers(self) -> None:
        idx = pd.date_range("2024-01-01", periods=120, freq="B")

        def _mk_sharp_drawdown() -> pd.DataFrame:
            close = np.concatenate([np.linspace(100.0, 120.0, 40), np.linspace(120.0, 70.0, 80)])
            return pd.DataFrame(
                {
                    "Close": close,
                    "MA20": np.full(len(idx), 2.0),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_sharp_drawdown()}
        no_circuit = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1)
        with_circuit = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            drawdown_circuit_pct=0.08,
            circuit_cooldown_days=5,
        )
        self.assertGreater(with_circuit.get("drawdown_circuit_triggers", 0.0), 0.0)
        self.assertGreater(with_circuit.get("circuit_active_days", 0.0), 0.0)
        self.assertGreater(with_circuit["total_return"], no_circuit["total_return"])
        self.assertGreater(with_circuit.get("risk_event_count", 0.0), 0.0)
        trigger_set = {
            str(item.get("trigger", ""))
            for item in (with_circuit.get("risk_event_log") or [])
            if isinstance(item, dict)
        }
        self.assertIn("drawdown_circuit_trigger", trigger_set)

    def test_portfolio_backtest_industry_limit_blocks_entries(self) -> None:
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

        symbol_data = {"AAA": _mk_symbol(), "BBB": _mk_symbol(), "CCC": _mk_symbol()}
        industry_map = {"AAA": "A", "BBB": "A", "CCC": "A"}
        unconstrained = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=2,
            max_industry_weight=1.0,
            industry_map=industry_map,
        )
        constrained = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=2,
            max_industry_weight=0.5,
            industry_map=industry_map,
        )
        self.assertGreater(constrained.get("industry_blocked_entries", 0.0), 0.0)
        self.assertGreaterEqual(constrained.get("max_industry_weight_used", 0.0), 0.0)
        self.assertLessEqual(constrained.get("max_industry_weight_used", 0.0), 0.5)
        self.assertGreater(unconstrained.get("max_industry_weight_used", 0.0), 0.5)
        trigger_set = {
            str(item.get("trigger", ""))
            for item in (constrained.get("risk_event_log") or [])
            if isinstance(item, dict)
        }
        self.assertIn("industry_weight_limit", trigger_set)

    def test_portfolio_backtest_single_weight_cap(self) -> None:
        idx = pd.date_range("2024-01-01", periods=100, freq="B")

        def _mk_symbol(offset: float) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 140.0 + offset, len(idx)),
                    "MA20": np.full(len(idx), 2.0 + offset),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0 + offset),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_symbol(0.1), "BBB": _mk_symbol(0.2)}
        uncapped = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1, max_single_weight=1.0)
        capped = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1, max_single_weight=0.35)

        self.assertGreaterEqual(capped.get("max_single_weight_used", 0.0), 0.0)
        self.assertLessEqual(capped.get("max_single_weight_used", 0.0), 0.35 + 1e-9)
        self.assertLess(capped.get("avg_capital_utilization", 1.0), uncapped.get("avg_capital_utilization", 0.0))

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
        self.assertIn("波动率控制", text)
        self.assertIn("资金利用率约束", text)
        self.assertIn("风控事件数", text)

    def test_portfolio_backtest_target_volatility_controls_exposure(self) -> None:
        idx = pd.date_range("2024-01-01", periods=140, freq="B")
        close = 100.0 + np.sin(np.linspace(0, 60, len(idx))) * 30.0
        frame = pd.DataFrame(
            {
                "Close": close,
                "MA20": np.full(len(idx), 2.0),
                "MA60": np.full(len(idx), 1.0),
                "MACD": np.full(len(idx), 1.0),
                "MACD_SIGNAL": np.zeros(len(idx)),
                "RSI14": np.full(len(idx), 50.0),
            },
            index=idx,
        )
        symbol_data = {"AAA": frame, "BBB": frame}
        base = run_portfolio_backtest(symbol_data, fee_rate=0.0, max_positions=1)
        controlled = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            target_volatility=0.10,
            vol_lookback_days=20,
        )
        self.assertGreater(base.get("realized_volatility", 0.0), 0.0)
        self.assertGreater(controlled.get("vol_control_active_days", 0.0), 0.0)
        self.assertLess(controlled.get("avg_exposure_scale", 1.0), 1.0)
        self.assertLess(controlled.get("realized_volatility", 0.0), base.get("realized_volatility", 0.0))

    def test_portfolio_backtest_capital_utilization_constraints(self) -> None:
        idx = pd.date_range("2024-01-01", periods=120, freq="B")

        def _mk_symbol(offset: float) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Close": np.linspace(100.0, 130.0 + offset, len(idx)),
                    "MA20": np.full(len(idx), 2.0 + offset),
                    "MA60": np.full(len(idx), 1.0),
                    "MACD": np.full(len(idx), 1.0 + offset),
                    "MACD_SIGNAL": np.zeros(len(idx)),
                    "RSI14": np.full(len(idx), 50.0),
                },
                index=idx,
            )

        symbol_data = {"AAA": _mk_symbol(0.0), "BBB": _mk_symbol(0.2)}
        capped = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            max_capital_utilization=0.25,
        )
        self.assertGreater(capped.get("capital_util_cap_hits", 0.0), 0.0)
        self.assertLessEqual(capped.get("avg_capital_utilization", 1.0), 0.25 + 1e-9)

        floor_breach = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            max_single_weight=0.35,
            min_capital_utilization=0.60,
        )
        self.assertGreater(floor_breach.get("capital_util_floor_breaches", 0.0), 0.0)

    def test_portfolio_backtest_rebalance_frequency_changes_rebalance_days(self) -> None:
        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        frame = pd.DataFrame(
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
        symbol_data = {"AAA": frame}

        daily = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            rebalance_frequency="daily",
        )
        weekly = run_portfolio_backtest(
            symbol_data,
            fee_rate=0.0,
            max_positions=1,
            rebalance_frequency="weekly",
            rebalance_weekday=0,
        )

        self.assertGreater(daily.get("rebalance_days", 0.0), weekly.get("rebalance_days", 0.0))
        self.assertEqual(str(weekly.get("rebalance_frequency", "")), "weekly")
        self.assertIsInstance(weekly.get("rebalance_log"), list)
        self.assertGreater(len(weekly.get("rebalance_log", [])), 0)

    def test_format_portfolio_backtest_report_contains_rebalance_section(self) -> None:
        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        frame = pd.DataFrame(
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
        metrics = run_portfolio_backtest(
            {"AAA": frame},
            max_positions=1,
            rebalance_frequency="weekly",
            rebalance_weekday=2,
        )
        text = format_portfolio_backtest_report(metrics)
        self.assertIn("调仓模式", text)
        self.assertIn("weekly(", text)
        self.assertIn("调仓分解", text)


if __name__ == "__main__":
    unittest.main()
