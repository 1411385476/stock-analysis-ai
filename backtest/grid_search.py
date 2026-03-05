from itertools import product
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
        )
        if not metrics:
            continue
        rows.append({"params": params, "metrics": metrics})
    return sort_grid_results(rows, sort_by=sort_by)


def run_portfolio_grid_backtest(
    symbol_data,
    param_grid: list[dict[str, Any]],
    sort_by: str = "annual_return",
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
        )
        if not metrics:
            continue
        rows.append({"params": params, "metrics": metrics})
    return sort_grid_results(rows, sort_by=sort_by)


def _param_text(params: dict[str, Any]) -> str:
    return (
        f"fee={float(params.get('fee_rate', 0.0)):.4f}, "
        f"slip={float(params.get('slippage_bps', 0.0)):.1f}bps, "
        f"hold={int(params.get('min_hold_days', 1))}, "
        f"confirm={int(params.get('signal_confirm_days', 1))}, "
        f"max_pos={int(params.get('max_positions', 1))}"
    )


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
