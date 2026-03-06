from itertools import product
from math import ceil
from typing import Any, Callable, Optional

from backtest.engine import run_backtest, run_portfolio_backtest


def parse_float_list(raw: Optional[str], fallback: float) -> list[float]:
    if raw is None or not str(raw).strip():
        return [float(fallback)]
    out: list[float] = []
    for item in str(raw).split(","):
        token = item.strip()
        if not token:
            continue
        out.append(float(token))
    return out or [float(fallback)]


def parse_int_list(raw: Optional[str], fallback: int, min_value: int = 1) -> list[int]:
    if raw is None or not str(raw).strip():
        return [max(int(fallback), min_value)]
    out: list[int] = []
    for item in str(raw).split(","):
        token = item.strip()
        if not token:
            continue
        out.append(max(int(token), min_value))
    return out or [max(int(fallback), min_value)]


def build_backtest_param_grid(
    fee_rates: list[float],
    slippage_bps: list[float],
    min_hold_days: list[int],
    signal_confirm_days: list[int],
    max_positions: list[int],
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[float, float, int, int, int]] = set()

    for fee, slip, hold, confirm, max_pos in product(
        fee_rates,
        slippage_bps,
        min_hold_days,
        signal_confirm_days,
        max_positions,
    ):
        key = (
            max(float(fee), 0.0),
            max(float(slip), 0.0),
            max(int(hold), 1),
            max(int(confirm), 1),
            max(int(max_pos), 1),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "fee_rate": key[0],
                "slippage_bps": key[1],
                "min_hold_days": key[2],
                "signal_confirm_days": key[3],
                "max_positions": key[4],
            }
        )
    return deduped


def _rank_key(sort_by: str) -> Callable[[dict[str, Any]], float]:
    key = str(sort_by or "annual_return").strip()

    def _extract(item: dict[str, Any]) -> float:
        metrics = item.get("metrics") or {}
        try:
            return float(metrics.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    return _extract


def sort_grid_results(
    results: list[dict[str, Any]],
    sort_by: str = "annual_return",
) -> list[dict[str, Any]]:
    ranked = sorted(results, key=_rank_key(sort_by), reverse=True)
    return ranked


def run_single_grid_backtest(
    df,
    param_grid: list[dict[str, Any]],
    sort_by: str = "annual_return",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for params in param_grid:
        metrics = run_backtest(
            df,
            fee_rate=float(params.get("fee_rate", 0.0)),
            slippage_bps=float(params.get("slippage_bps", 0.0)),
            min_hold_days=int(params.get("min_hold_days", 1)),
            signal_confirm_days=int(params.get("signal_confirm_days", 1)),
            max_positions=int(params.get("max_positions", 1)),
            stop_loss_pct=float(params.get("stop_loss_pct", 0.0)),
            take_profit_pct=float(params.get("take_profit_pct", 0.0)),
        )
        if not metrics:
            continue
        rows.append({"params": params, "metrics": metrics})
    return sort_grid_results(rows, sort_by=sort_by)


def run_portfolio_grid_backtest(
    symbol_data,
    param_grid: list[dict[str, Any]],
    sort_by: str = "annual_return",
    industry_map: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for params in param_grid:
        metrics = run_portfolio_backtest(
            symbol_data=symbol_data,
            fee_rate=float(params.get("fee_rate", 0.0)),
            slippage_bps=float(params.get("slippage_bps", 0.0)),
            min_hold_days=int(params.get("min_hold_days", 1)),
            signal_confirm_days=int(params.get("signal_confirm_days", 1)),
            max_positions=int(params.get("max_positions", 1)),
            stop_loss_pct=float(params.get("stop_loss_pct", 0.0)),
            take_profit_pct=float(params.get("take_profit_pct", 0.0)),
            industry_map=industry_map,
            max_industry_weight=float(params.get("max_industry_weight", 1.0)),
            max_single_weight=float(params.get("max_single_weight", 1.0)),
            drawdown_circuit_pct=float(params.get("drawdown_circuit_pct", 0.0)),
            circuit_cooldown_days=int(params.get("circuit_cooldown_days", 0)),
        )
        if not metrics:
            continue
        rows.append({"params": params, "metrics": metrics})
    return sort_grid_results(rows, sort_by=sort_by)


def _param_text(params: dict[str, Any]) -> str:
    parts = [
        f"fee={float(params.get('fee_rate', 0.0)):.4f}, "
        f"slip={float(params.get('slippage_bps', 0.0)):.1f}bps, "
        f"hold={int(params.get('min_hold_days', 1))}, "
        f"confirm={int(params.get('signal_confirm_days', 1))}, "
        f"max_pos={int(params.get('max_positions', 1))}"
    ]
    stop_loss_pct = float(params.get("stop_loss_pct", 0.0))
    take_profit_pct = float(params.get("take_profit_pct", 0.0))
    if stop_loss_pct > 0:
        parts.append(f", stop={stop_loss_pct * 100:.2f}%")
    if take_profit_pct > 0:
        parts.append(f", take={take_profit_pct * 100:.2f}%")
    drawdown_circuit_pct = float(params.get("drawdown_circuit_pct", 0.0))
    if drawdown_circuit_pct > 0:
        parts.append(f", dd_circuit={drawdown_circuit_pct * 100:.2f}%")
    cooldown_days = int(params.get("circuit_cooldown_days", 0))
    if cooldown_days > 0:
        parts.append(f", cooldown={cooldown_days}d")
    max_industry_weight = float(params.get("max_industry_weight", 1.0))
    if max_industry_weight < 1.0:
        parts.append(f", industry_cap={max_industry_weight * 100:.2f}%")
    max_single_weight = float(params.get("max_single_weight", 1.0))
    if max_single_weight < 1.0:
        parts.append(f", single_cap={max_single_weight * 100:.2f}%")
    return "".join(parts)


def format_grid_report(
    results: list[dict[str, Any]],
    total_count: int,
    sort_by: str = "annual_return",
    top_n: int = 10,
) -> str:
    if not results:
        return "参数网格回测结果: 无有效结果。"

    keep = max(int(top_n), 1)
    lines = [
        f"参数网格回测: 共 {int(total_count)} 组，成功 {len(results)} 组，按 {sort_by} 排序（Top {keep}）",
    ]
    for idx, row in enumerate(results[:keep], start=1):
        metrics = row.get("metrics") or {}
        params = row.get("params") or {}
        lines.append(
            (
                f"{idx}. 年化={float(metrics.get('annual_return', 0.0)) * 100:.2f}% | "
                f"总收益={float(metrics.get('total_return', 0.0)) * 100:.2f}% | "
                f"回撤={float(metrics.get('max_drawdown', 0.0)) * 100:.2f}% | "
                f"夏普={float(metrics.get('sharpe', 0.0)):.2f} | "
                f"{_param_text(params)}"
            )
        )
    return "\n".join(lines)


_PARAM_LABELS = {
    "fee_rate": "手续费率",
    "slippage_bps": "滑点",
    "min_hold_days": "最小持仓天数",
    "signal_confirm_days": "信号确认天数",
    "max_positions": "最大持仓数",
    "stop_loss_pct": "止损比例",
    "take_profit_pct": "止盈比例",
    "drawdown_circuit_pct": "回撤熔断阈值",
    "circuit_cooldown_days": "熔断冷却天数",
    "max_industry_weight": "行业权重上限",
    "max_single_weight": "单票权重上限",
}

_PARAM_ORDER = [
    "fee_rate",
    "slippage_bps",
    "min_hold_days",
    "signal_confirm_days",
    "max_positions",
    "stop_loss_pct",
    "take_profit_pct",
    "drawdown_circuit_pct",
    "circuit_cooldown_days",
    "max_industry_weight",
    "max_single_weight",
]


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_param_value(key: str, value: float) -> str:
    int_keys = {"min_hold_days", "signal_confirm_days", "max_positions", "circuit_cooldown_days"}
    pct_keys = {
        "fee_rate",
        "stop_loss_pct",
        "take_profit_pct",
        "drawdown_circuit_pct",
        "max_industry_weight",
        "max_single_weight",
    }
    if key in int_keys:
        return f"{int(round(value))}"
    if key == "slippage_bps":
        return f"{value:.1f}bps"
    if key in pct_keys:
        return f"{value * 100:.2f}%"
    return f"{value:.4f}"


def _format_metric_value(metric: str, value: float) -> str:
    pct_metrics = {"annual_return", "total_return", "benchmark_return", "max_drawdown", "win_rate"}
    if metric in pct_metrics:
        return f"{value * 100:.2f}%"
    return f"{value:.4f}"


def summarize_grid_robust_ranges(
    results: list[dict[str, Any]],
    sort_by: str = "annual_return",
    top_ratio: float = 0.2,
    min_top_n: int = 10,
) -> dict[str, Any]:
    if not results:
        return {}

    ranked = sort_grid_results(list(results), sort_by=sort_by)
    total = len(ranked)
    ratio = min(max(float(top_ratio), 0.01), 1.0)
    top_n = max(int(min_top_n), int(ceil(total * ratio)))
    top_n = min(top_n, total)
    selected = ranked[:top_n]
    threshold = float((selected[-1].get("metrics") or {}).get(sort_by, 0.0))

    key_sequence: list[str] = []
    seen_keys: set[str] = set()
    for key in _PARAM_ORDER:
        key_sequence.append(key)
        seen_keys.add(key)
    for row in selected:
        for key in (row.get("params") or {}).keys():
            if key in seen_keys:
                continue
            seen_keys.add(key)
            key_sequence.append(key)

    stats: list[dict[str, Any]] = []
    for key in key_sequence:
        values: list[float] = []
        for row in selected:
            params = row.get("params") or {}
            value = _safe_float(params.get(key))
            if value is None:
                continue
            values.append(value)
        if not values:
            continue

        freq: dict[float, int] = {}
        for value in values:
            freq[value] = freq.get(value, 0) + 1
        mode_value, mode_count = max(freq.items(), key=lambda item: (item[1], -item[0]))
        stats.append(
            {
                "key": key,
                "label": _PARAM_LABELS.get(key, key),
                "min": float(min(values)),
                "max": float(max(values)),
                "mode": float(mode_value),
                "mode_coverage": float(mode_count / len(values)),
                "unique_count": int(len(freq)),
            }
        )

    return {
        "sort_by": str(sort_by),
        "top_ratio": float(ratio),
        "total_count": int(total),
        "selected_count": int(top_n),
        "threshold": float(threshold),
        "param_stats": stats,
    }


def format_robust_range_report(summary: dict[str, Any]) -> str:
    if not summary:
        return "参数稳健区间报告: 数据不足。"

    sort_by = str(summary.get("sort_by", "annual_return"))
    total = int(summary.get("total_count", 0))
    selected = int(summary.get("selected_count", 0))
    ratio = float(summary.get("top_ratio", 0.0))
    threshold = float(summary.get("threshold", 0.0))
    stats = list(summary.get("param_stats") or [])

    lines = [
        "参数稳健区间报告:",
        f"- 取样范围: Top {ratio * 100:.1f}% => {selected}/{total}（按 {sort_by}）",
        f"- 入选门槛: {sort_by} >= {_format_metric_value(sort_by, threshold)}",
    ]
    if not stats:
        lines.append("- 参数统计: N/A")
        return "\n".join(lines)

    lines.append("- 参数区间与众数:")
    for item in stats:
        key = str(item.get("key", ""))
        min_v = float(item.get("min", 0.0))
        max_v = float(item.get("max", 0.0))
        mode_v = float(item.get("mode", 0.0))
        if abs(max_v - min_v) < 1e-12:
            interval = _format_param_value(key, min_v)
        else:
            interval = f"{_format_param_value(key, min_v)} ~ {_format_param_value(key, max_v)}"
        lines.append(
            f"  - {item.get('label', key)}: 区间={interval} | 众数={_format_param_value(key, mode_v)} "
            f"(覆盖={float(item.get('mode_coverage', 0.0)) * 100:.1f}%, 去重={int(item.get('unique_count', 0))})"
        )
    return "\n".join(lines)
