from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from backtest.engine import REQUIRED_SIGNAL_COLS, run_portfolio_backtest
from backtest.grid_search import run_portfolio_grid_backtest


def _safe_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(number, minimum)


def _safe_float(value: Any, default: float, minimum: float = 0.0, maximum: Optional[float] = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


def _normalize_backtest_params(params: Optional[dict[str, Any]]) -> dict[str, Any]:
    raw = dict(params or {})
    return {
        "fee_rate": _safe_float(raw.get("fee_rate"), 0.001),
        "slippage_bps": _safe_float(raw.get("slippage_bps"), 0.0),
        "min_hold_days": _safe_int(raw.get("min_hold_days"), 1, minimum=1),
        "signal_confirm_days": _safe_int(raw.get("signal_confirm_days"), 1, minimum=1),
        "max_positions": _safe_int(raw.get("max_positions"), 1, minimum=1),
        "stop_loss_pct": _safe_float(raw.get("stop_loss_pct"), 0.0),
        "take_profit_pct": _safe_float(raw.get("take_profit_pct"), 0.0),
        "drawdown_circuit_pct": _safe_float(raw.get("drawdown_circuit_pct"), 0.0),
        "circuit_cooldown_days": _safe_int(raw.get("circuit_cooldown_days"), 0, minimum=0),
        "max_industry_weight": _safe_float(raw.get("max_industry_weight"), 1.0, maximum=1.0),
        "max_single_weight": _safe_float(raw.get("max_single_weight"), 1.0, maximum=1.0),
        "target_volatility": _safe_float(raw.get("target_volatility"), 0.0),
        "vol_lookback_days": _safe_int(raw.get("vol_lookback_days"), 20, minimum=5),
        "min_capital_utilization": _safe_float(raw.get("min_capital_utilization"), 0.0, maximum=1.0),
        "max_capital_utilization": _safe_float(raw.get("max_capital_utilization"), 1.0, maximum=1.0),
        "rebalance_frequency": str(raw.get("rebalance_frequency", "daily")).strip().lower() or "daily",
        "rebalance_weekday": _safe_int(raw.get("rebalance_weekday"), 0, minimum=0),
    }


def _prepare_symbol_data(symbol_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    prepared: dict[str, pd.DataFrame] = {}
    for symbol, frame in symbol_data.items():
        if frame is None or frame.empty:
            continue
        local = frame.copy()
        if not isinstance(local.index, pd.DatetimeIndex):
            try:
                local.index = pd.to_datetime(local.index)
            except Exception:
                continue
        if any(col not in local.columns for col in REQUIRED_SIGNAL_COLS):
            continue
        local = local.sort_index().dropna(subset=REQUIRED_SIGNAL_COLS)
        if local.empty:
            continue
        prepared[symbol] = local
    return prepared


def _slice_symbol_data(symbol_data: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    sliced: dict[str, pd.DataFrame] = {}
    for symbol, frame in symbol_data.items():
        piece = frame.loc[(frame.index >= start) & (frame.index <= end)].copy()
        if len(piece) < 30:
            continue
        sliced[symbol] = piece
    return sliced


def build_walk_forward_windows(
    index: pd.DatetimeIndex,
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[dict[str, Any]]:
    if not isinstance(index, pd.DatetimeIndex):
        try:
            index = pd.DatetimeIndex(index)
        except Exception:
            return []
    ordered = index.sort_values().unique()
    train_days = _safe_int(train_days, 126, minimum=30)
    test_days = _safe_int(test_days, 63, minimum=30)
    step_days = _safe_int(step_days, 21, minimum=1)
    if len(ordered) < train_days + test_days:
        return []

    windows: list[dict[str, Any]] = []
    offset = 0
    while offset + train_days + test_days <= len(ordered):
        train_start_ts = ordered[offset]
        train_end_ts = ordered[offset + train_days - 1]
        test_start_ts = ordered[offset + train_days]
        test_end_ts = ordered[offset + train_days + test_days - 1]
        windows.append(
            {
                "window_id": len(windows) + 1,
                "train_start": train_start_ts.strftime("%Y-%m-%d"),
                "train_end": train_end_ts.strftime("%Y-%m-%d"),
                "test_start": test_start_ts.strftime("%Y-%m-%d"),
                "test_end": test_end_ts.strftime("%Y-%m-%d"),
                "_train_start_ts": train_start_ts,
                "_train_end_ts": train_end_ts,
                "_test_start_ts": test_start_ts,
                "_test_end_ts": test_end_ts,
            }
        )
        offset += step_days
    return windows


def _summarize_windows(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {
            "window_win_rate": 0.0,
            "avg_total_return": 0.0,
            "avg_annual_return": 0.0,
            "avg_sharpe": 0.0,
            "worst_drawdown": 0.0,
            "best_window_id": 0,
            "worst_window_id": 0,
        }
    totals = np.array([float(item["metrics"].get("total_return", 0.0)) for item in windows], dtype=float)
    annuals = np.array([float(item["metrics"].get("annual_return", 0.0)) for item in windows], dtype=float)
    sharpes = np.array([float(item["metrics"].get("sharpe", 0.0)) for item in windows], dtype=float)
    drawdowns = np.array([float(item["metrics"].get("max_drawdown", 0.0)) for item in windows], dtype=float)
    win_count = int(np.sum(totals > 0.0))
    best_idx = int(np.argmax(annuals))
    worst_idx = int(np.argmin(annuals))
    return {
        "window_win_rate": float(win_count / len(windows)),
        "avg_total_return": float(np.mean(totals)),
        "avg_annual_return": float(np.mean(annuals)),
        "avg_sharpe": float(np.mean(sharpes)),
        "worst_drawdown": float(np.min(drawdowns)),
        "best_window_id": int(windows[best_idx]["window_id"]),
        "worst_window_id": int(windows[worst_idx]["window_id"]),
    }


def _build_segment_comparison(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {
            "outperform_rate": 0.0,
            "avg_strategy_total_return": 0.0,
            "avg_benchmark_total_return": 0.0,
            "avg_excess_total_return": 0.0,
            "positive_excess_windows": 0,
            "best_excess_window_id": 0,
            "worst_excess_window_id": 0,
        }

    strategy_returns = np.array([float((row.get("metrics") or {}).get("total_return", 0.0)) for row in windows], dtype=float)
    benchmark_returns = np.array([float((row.get("metrics") or {}).get("benchmark_return", 0.0)) for row in windows], dtype=float)
    excess_returns = strategy_returns - benchmark_returns
    positive_count = int(np.sum(excess_returns > 0.0))
    best_idx = int(np.argmax(excess_returns))
    worst_idx = int(np.argmin(excess_returns))
    return {
        "outperform_rate": float(positive_count / len(windows)),
        "avg_strategy_total_return": float(np.mean(strategy_returns)),
        "avg_benchmark_total_return": float(np.mean(benchmark_returns)),
        "avg_excess_total_return": float(np.mean(excess_returns)),
        "positive_excess_windows": positive_count,
        "best_excess_window_id": int(windows[best_idx]["window_id"]),
        "worst_excess_window_id": int(windows[worst_idx]["window_id"]),
    }


def run_portfolio_walk_forward(
    symbol_data: dict[str, pd.DataFrame],
    base_params: Optional[dict[str, Any]] = None,
    param_grid: Optional[list[dict[str, Any]]] = None,
    train_days: int = 126,
    test_days: int = 63,
    step_days: int = 21,
    sort_by: str = "annual_return",
    industry_map: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    prepared = _prepare_symbol_data(symbol_data)
    if not prepared:
        return {}

    common_index: Optional[pd.DatetimeIndex] = None
    for frame in prepared.values():
        common_index = frame.index if common_index is None else common_index.intersection(frame.index)
    if common_index is None:
        return {}
    common_index = common_index.sort_values()

    train_days = _safe_int(train_days, 126, minimum=30)
    test_days = _safe_int(test_days, 63, minimum=30)
    step_days = _safe_int(step_days, 21, minimum=1)
    available_days = int(len(common_index))
    required_days = int(train_days + test_days)
    windows = build_walk_forward_windows(common_index, train_days=train_days, test_days=test_days, step_days=step_days)
    if not windows:
        return {
            "schema_version": 1,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": {"train_days": train_days, "test_days": test_days, "step_days": step_days, "sort_by": sort_by},
            "available_days": available_days,
            "required_days": required_days,
            "windows_total": 0,
            "windows_valid": 0,
            "summary": _summarize_windows([]),
            "segment_comparison": _build_segment_comparison([]),
            "windows": [],
        }

    base_kwargs = _normalize_backtest_params(base_params)
    normalized_grid = [_normalize_backtest_params(item) for item in (param_grid or [])]

    rows: list[dict[str, Any]] = []
    for item in windows:
        train_data = _slice_symbol_data(
            prepared,
            start=item["_train_start_ts"],
            end=item["_train_end_ts"],
        )
        test_data = _slice_symbol_data(
            prepared,
            start=item["_test_start_ts"],
            end=item["_test_end_ts"],
        )
        if not train_data or not test_data:
            continue

        chosen_params = dict(base_kwargs)
        if normalized_grid:
            grid_rows = run_portfolio_grid_backtest(
                symbol_data=train_data,
                param_grid=normalized_grid,
                sort_by=sort_by,
                industry_map=industry_map,
            )
            if grid_rows:
                chosen_params = _normalize_backtest_params(grid_rows[0].get("params") or base_kwargs)

        metrics = run_portfolio_backtest(
            symbol_data=test_data,
            fee_rate=chosen_params["fee_rate"],
            slippage_bps=chosen_params["slippage_bps"],
            min_hold_days=chosen_params["min_hold_days"],
            signal_confirm_days=chosen_params["signal_confirm_days"],
            max_positions=chosen_params["max_positions"],
            stop_loss_pct=chosen_params["stop_loss_pct"],
            take_profit_pct=chosen_params["take_profit_pct"],
            industry_map=industry_map,
            max_industry_weight=chosen_params["max_industry_weight"],
            max_single_weight=chosen_params["max_single_weight"],
            drawdown_circuit_pct=chosen_params["drawdown_circuit_pct"],
            circuit_cooldown_days=chosen_params["circuit_cooldown_days"],
            target_volatility=chosen_params["target_volatility"],
            vol_lookback_days=chosen_params["vol_lookback_days"],
            min_capital_utilization=chosen_params["min_capital_utilization"],
            max_capital_utilization=chosen_params["max_capital_utilization"],
            rebalance_frequency=chosen_params["rebalance_frequency"],
            rebalance_weekday=min(max(int(chosen_params["rebalance_weekday"]), 0), 4),
        )
        if not metrics:
            continue

        rows.append(
            {
                "window_id": int(item["window_id"]),
                "train_start": item["train_start"],
                "train_end": item["train_end"],
                "test_start": item["test_start"],
                "test_end": item["test_end"],
                "params": chosen_params,
                "metrics": metrics,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {"train_days": train_days, "test_days": test_days, "step_days": step_days, "sort_by": sort_by},
        "available_days": available_days,
        "required_days": required_days,
        "windows_total": len(windows),
        "windows_valid": len(rows),
        "summary": _summarize_windows(rows),
        "segment_comparison": _build_segment_comparison(rows),
        "windows": rows,
    }


def format_walk_forward_report(result: dict[str, Any]) -> str:
    if not result:
        return "Walk-forward评估: 数据不足，无法评估。"
    total = int(result.get("windows_total", 0))
    valid = int(result.get("windows_valid", 0))
    config = result.get("config") or {}
    available_days = int(result.get("available_days", 0))
    required_days = int(result.get("required_days", 0))
    summary = result.get("summary") or {}
    segment = result.get("segment_comparison") or {}
    if valid <= 0:
        reason = "样本不足或窗口内无有效回测结果。"
        if required_days > 0 and available_days > 0 and available_days < required_days:
            reason = f"样本不足（需要至少 {required_days} 天，当前 {available_days} 天）。"
        return (
            "Walk-forward评估:\n"
            f"- 窗口数量: {total}（有效 0）\n"
            f"- 配置: 训练={int(config.get('train_days', 0))}天 / "
            f"测试={int(config.get('test_days', 0))}天 / 步长={int(config.get('step_days', 0))}天\n"
            f"- 样本天数: 当前={available_days} / 需求={required_days}\n"
            f"- 结论: {reason}"
        )

    lines = [
        "Walk-forward评估:",
        f"- 窗口数量: {total}（有效 {valid}）",
        f"- 配置: 训练={int(config.get('train_days', 0))}天 / 测试={int(config.get('test_days', 0))}天 / 步长={int(config.get('step_days', 0))}天",
        f"- 窗口胜率: {float(summary.get('window_win_rate', 0.0)) * 100:.2f}%",
        f"- 平均总收益: {float(summary.get('avg_total_return', 0.0)) * 100:.2f}%",
        f"- 平均年化收益: {float(summary.get('avg_annual_return', 0.0)) * 100:.2f}%",
        f"- 平均夏普: {float(summary.get('avg_sharpe', 0.0)):.2f}",
        f"- 最差回撤: {float(summary.get('worst_drawdown', 0.0)) * 100:.2f}%",
        f"- 最佳窗口: #{int(summary.get('best_window_id', 0))}",
        f"- 最弱窗口: #{int(summary.get('worst_window_id', 0))}",
        "- 分段对比(策略 vs 基准):",
        (
            f"  超额为正窗口: {int(segment.get('positive_excess_windows', 0))}/{valid} "
            f"({float(segment.get('outperform_rate', 0.0)) * 100:.2f}%)"
        ),
        (
            f"  平均策略/基准/超额收益: "
            f"{float(segment.get('avg_strategy_total_return', 0.0)) * 100:.2f}% / "
            f"{float(segment.get('avg_benchmark_total_return', 0.0)) * 100:.2f}% / "
            f"{float(segment.get('avg_excess_total_return', 0.0)) * 100:.2f}%"
        ),
        (
            f"  超额最佳/最弱窗口: "
            f"#{int(segment.get('best_excess_window_id', 0))} / "
            f"#{int(segment.get('worst_excess_window_id', 0))}"
        ),
    ]
    rows = list(result.get("windows") or [])
    if rows:
        top_rows = sorted(rows, key=lambda item: float((item.get("metrics") or {}).get("annual_return", 0.0),), reverse=True)[:3]
        lines.append("- Top窗口(按年化):")
        for row in top_rows:
            metrics = row.get("metrics") or {}
            lines.append(
                "  "
                + (
                    f"#{int(row.get('window_id', 0))} "
                    f"{row.get('test_start', 'N/A')}~{row.get('test_end', 'N/A')} "
                    f"年化={float(metrics.get('annual_return', 0.0)) * 100:.2f}% "
                    f"回撤={float(metrics.get('max_drawdown', 0.0)) * 100:.2f}% "
                    f"夏普={float(metrics.get('sharpe', 0.0)):.2f}"
                )
            )
    return "\n".join(lines)
