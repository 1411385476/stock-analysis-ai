from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import run_portfolio_backtest

SNAPSHOT_SCHEMA_VERSION = 1

SNAPSHOT_KEYS: tuple[str, ...] = (
    "total_return",
    "annual_return",
    "benchmark_return",
    "max_drawdown",
    "sharpe",
    "calmar",
    "win_rate",
    "trades",
    "avg_active_positions",
    "max_active_positions",
    "avg_capital_utilization",
    "realized_volatility",
    "vol_control_active_days",
    "rebalance_days",
    "rebalance_event_count",
    "rebalance_signal_entries",
    "rebalance_signal_exits",
    "rebalance_risk_exits",
    "rebalance_scale_events",
    "risk_event_count",
    "drawdown_circuit_triggers",
    "industry_blocked_entries",
    "max_single_weight_used",
    "max_industry_weight_used",
)

DEFAULT_THRESHOLDS: dict[str, float] = {
    "total_return": 0.015,
    "annual_return": 0.020,
    "benchmark_return": 0.010,
    "max_drawdown": 0.015,
    "sharpe": 0.15,
    "calmar": 0.20,
    "win_rate": 0.05,
    "trades": 2.0,
    "avg_active_positions": 0.10,
    "max_active_positions": 0.50,
    "avg_capital_utilization": 0.08,
    "realized_volatility": 0.03,
    "vol_control_active_days": 15.0,
    "rebalance_days": 10.0,
    "rebalance_event_count": 10.0,
    "rebalance_signal_entries": 5.0,
    "rebalance_signal_exits": 5.0,
    "rebalance_risk_exits": 3.0,
    "rebalance_scale_events": 8.0,
    "risk_event_count": 20.0,
    "drawdown_circuit_triggers": 2.0,
    "industry_blocked_entries": 3.0,
    "max_single_weight_used": 0.08,
    "max_industry_weight_used": 0.08,
}


def _sample_signal_frame(
    rows: int,
    start_price: float,
    trend: float,
    amp: float,
    phase: int,
) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=rows, freq="B")
    linear = np.linspace(start_price, start_price + trend, rows)
    cycle = np.sin(np.linspace(0.0 + phase * 0.2, 24.0 + phase * 0.2, rows)) * amp
    close = linear + cycle

    block = ((np.arange(rows) + phase) // 18) % 2 == 0
    ma20 = np.where(block, 2.20 + phase * 0.02, 0.95 + phase * 0.01)
    ma60 = np.where(block, 1.05, 2.05)
    macd = np.where(block, 1.20 + phase * 0.03, -0.80 - phase * 0.02)
    macd_signal = np.where(block, 0.20, 0.10)
    rsi14 = np.where(block, 53.0, 82.0)

    return pd.DataFrame(
        {
            "Close": close,
            "MA20": ma20,
            "MA60": ma60,
            "MACD": macd,
            "MACD_SIGNAL": macd_signal,
            "RSI14": rsi14,
        },
        index=idx,
    )


def build_reference_symbol_data(rows: int = 300) -> dict[str, pd.DataFrame]:
    return {
        "AAA": _sample_signal_frame(rows=rows, start_price=95.0, trend=40.0, amp=2.2, phase=0),
        "BBB": _sample_signal_frame(rows=rows, start_price=70.0, trend=35.0, amp=3.0, phase=5),
        "CCC": _sample_signal_frame(rows=rows, start_price=50.0, trend=28.0, amp=2.5, phase=9),
    }


def build_reference_case() -> dict[str, Any]:
    params = {
        "fee_rate": 0.001,
        "slippage_bps": 8.0,
        "min_hold_days": 3,
        "signal_confirm_days": 2,
        "max_positions": 2,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.15,
        "drawdown_circuit_pct": 0.10,
        "circuit_cooldown_days": 5,
        "max_industry_weight": 0.60,
        "max_single_weight": 0.35,
        "target_volatility": 0.18,
        "vol_lookback_days": 20,
        "min_capital_utilization": 0.20,
        "max_capital_utilization": 0.80,
        "rebalance_frequency": "weekly",
        "rebalance_weekday": 2,
    }
    industry_map = {"AAA": "industry_a", "BBB": "industry_b", "CCC": "industry_c"}
    return {
        "name": "portfolio_regression_v1",
        "rows": 300,
        "symbols": ["AAA", "BBB", "CCC"],
        "industry_map": industry_map,
        "params": params,
    }


def run_reference_backtest(case: dict[str, Any]) -> dict[str, float]:
    symbol_data = build_reference_symbol_data(rows=int(case.get("rows", 300)))
    params = dict(case.get("params") or {})
    metrics = run_portfolio_backtest(
        symbol_data=symbol_data,
        industry_map=dict(case.get("industry_map") or {}),
        fee_rate=float(params.get("fee_rate", 0.001)),
        slippage_bps=float(params.get("slippage_bps", 0.0)),
        min_hold_days=int(params.get("min_hold_days", 1)),
        signal_confirm_days=int(params.get("signal_confirm_days", 1)),
        max_positions=int(params.get("max_positions", 1)),
        stop_loss_pct=float(params.get("stop_loss_pct", 0.0)),
        take_profit_pct=float(params.get("take_profit_pct", 0.0)),
        drawdown_circuit_pct=float(params.get("drawdown_circuit_pct", 0.0)),
        circuit_cooldown_days=int(params.get("circuit_cooldown_days", 0)),
        max_industry_weight=float(params.get("max_industry_weight", 1.0)),
        max_single_weight=float(params.get("max_single_weight", 1.0)),
        target_volatility=float(params.get("target_volatility", 0.0)),
        vol_lookback_days=int(params.get("vol_lookback_days", 20)),
        min_capital_utilization=float(params.get("min_capital_utilization", 0.0)),
        max_capital_utilization=float(params.get("max_capital_utilization", 1.0)),
        rebalance_frequency=str(params.get("rebalance_frequency", "daily")),
        rebalance_weekday=int(params.get("rebalance_weekday", 0)),
    )
    return {key: float(metrics.get(key, 0.0)) for key in SNAPSHOT_KEYS}


def build_regression_snapshot() -> dict[str, Any]:
    case = build_reference_case()
    metrics = run_reference_backtest(case)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "case": case,
        "metrics": metrics,
        "thresholds": dict(DEFAULT_THRESHOLDS),
    }


def compare_regression_snapshots(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, float | str]]:
    current_metrics = (current or {}).get("metrics") or {}
    baseline_metrics = (baseline or {}).get("metrics") or {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update((baseline or {}).get("thresholds") or {})

    drifts: list[dict[str, float | str]] = []
    for key in SNAPSHOT_KEYS:
        if key not in current_metrics or key not in baseline_metrics:
            drifts.append(
                {
                    "metric": key,
                    "current": float(current_metrics.get(key, 0.0)),
                    "baseline": float(baseline_metrics.get(key, 0.0)),
                    "delta": float(current_metrics.get(key, 0.0)) - float(baseline_metrics.get(key, 0.0)),
                    "threshold": float(thresholds.get(key, 0.0)),
                    "reason": "missing_metric",
                }
            )
            continue
        cur = float(current_metrics[key])
        base = float(baseline_metrics[key])
        delta = cur - base
        threshold = float(thresholds.get(key, 0.0))
        if abs(delta) > threshold:
            drifts.append(
                {
                    "metric": key,
                    "current": cur,
                    "baseline": base,
                    "delta": delta,
                    "threshold": threshold,
                    "reason": "delta_exceeded",
                }
            )
    return drifts
