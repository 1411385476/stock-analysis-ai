from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.config import CONFIG
from app.errors import ErrorCode, format_error
from app.logging_config import get_logger
from app.utils import detect_network_restriction_hint, normalize_symbol
from backtest.artifacts import export_backtest_record, export_grid_results
from backtest.engine import (
    format_backtest_report,
    format_portfolio_backtest_report,
    run_backtest,
    run_portfolio_backtest,
)
from backtest.grid_search import (
    build_backtest_param_grid,
    format_grid_report,
    parse_float_list,
    parse_int_list,
    run_portfolio_grid_backtest,
    run_single_grid_backtest,
)
from data.providers.market_data import fetch_a_share_history, get_last_fetch_error
from factors.indicators import add_indicators
from llm.qwen_client import call_local_qwen
from report.charting import generate_chart
from report.renderer import build_report
from strategy.signal_engine import strategy_signals

logger = get_logger(__name__)


def analyze_stock(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    with_llm: bool = True,
    run_bt: bool = False,
    bt_fee_rate: float = 0.001,
    bt_slippage_bps: float = 0.0,
    bt_min_hold_days: int = 1,
    bt_signal_confirm_days: int = 1,
    bt_max_positions: int = 1,
    bt_grid: bool = False,
    bt_grid_fee_rates: Optional[str] = None,
    bt_grid_slippage_bps: Optional[str] = None,
    bt_grid_min_hold_days: Optional[str] = None,
    bt_grid_signal_confirm_days: Optional[str] = None,
    bt_grid_max_positions: Optional[str] = None,
    bt_grid_sort_by: str = "annual_return",
    bt_grid_top: int = 10,
    bt_save: bool = False,
    bt_output_dir: Optional[str] = None,
    bt_compare_last: bool = False,
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    symbol = normalize_symbol(symbol)
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start is None:
        start = (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d")

    logger.info("开始分析: symbol=%s, start=%s, end=%s", symbol, start, end)
    df = fetch_a_share_history(symbol=symbol, start=start, end=end)
    if df.empty:
        net_hint = detect_network_restriction_hint()
        if net_hint:
            return (
                format_error(ErrorCode.NETWORK_RESTRICTED, f"无法获取 {symbol} 的历史行情。{net_hint}"),
                None,
                None,
                None,
            )
        detail = get_last_fetch_error()
        if detail:
            return (
                format_error(
                    ErrorCode.DATA_FETCH,
                    f"无法获取 {symbol} 的历史行情，请检查代码、网络或时间区间。\n详细原因: {detail}",
                ),
                None,
                None,
                None,
            )
        return (
            format_error(
                ErrorCode.DATA_FETCH,
                f"无法获取 {symbol} 的历史行情，请检查代码、网络或时间区间。",
            ),
            None,
            None,
            None,
        )

    df = add_indicators(df)
    signals = strategy_signals(df)
    report = build_report(symbol, df, signals)
    chart_path = generate_chart(df, symbol)
    backtest_text = None

    if run_bt:
        if bt_grid:
            fee_rates = parse_float_list(bt_grid_fee_rates, bt_fee_rate)
            slippage_bps = parse_float_list(bt_grid_slippage_bps, bt_slippage_bps)
            min_hold_days = parse_int_list(bt_grid_min_hold_days, bt_min_hold_days, min_value=1)
            signal_confirm_days = parse_int_list(
                bt_grid_signal_confirm_days,
                bt_signal_confirm_days,
                min_value=1,
            )
            max_positions = parse_int_list(bt_grid_max_positions, bt_max_positions, min_value=1)
            param_grid = build_backtest_param_grid(
                fee_rates=fee_rates,
                slippage_bps=slippage_bps,
                min_hold_days=min_hold_days,
                signal_confirm_days=signal_confirm_days,
                max_positions=max_positions,
            )
            grid_results = run_single_grid_backtest(df=df, param_grid=param_grid, sort_by=bt_grid_sort_by)
            if not grid_results:
                backtest_text = "参数网格回测结果: 无有效结果。"
            else:
                best = grid_results[0]
                best_metrics = best.get("metrics") or {}
                best_params = best.get("params") or {}
                bt_lines = [
                    "参数网格最佳组合:",
                    format_backtest_report(best_metrics),
                    "",
                    "最佳参数:",
                    f"- 手续费率: {float(best_params.get('fee_rate', 0.0)):.4f}",
                    f"- 滑点: {float(best_params.get('slippage_bps', 0.0)):.1f}bps",
                    f"- 最小持仓天数: {int(best_params.get('min_hold_days', 1))}",
                    f"- 信号确认天数: {int(best_params.get('signal_confirm_days', 1))}",
                    f"- 最大持仓数: {int(best_params.get('max_positions', 1))}",
                    "",
                    format_grid_report(
                        results=grid_results,
                        total_count=len(param_grid),
                        sort_by=bt_grid_sort_by,
                        top_n=bt_grid_top,
                    ),
                ]
                if bt_save:
                    output_dir = bt_output_dir or CONFIG.backtest_output_dir
                    export_result = export_backtest_record(
                        mode="single",
                        symbols=[symbol],
                        start=start,
                        end=end,
                        params=best_params,
                        metrics=best_metrics,
                        output_dir=output_dir,
                        compare_last=bt_compare_last,
                        extra={
                            "grid_enabled": True,
                            "grid_sort_by": bt_grid_sort_by,
                            "grid_total_count": len(param_grid),
                        },
                    )
                    grid_export = export_grid_results(
                        mode="single",
                        symbols=[symbol],
                        start=start,
                        end=end,
                        sort_by=bt_grid_sort_by,
                        results=grid_results,
                        output_dir=output_dir,
                    )
                    bt_lines.extend(
                        [
                            "",
                            "回测文件已导出:",
                            f"- 最优JSON: {export_result['json_path']}",
                            f"- 最优Markdown: {export_result['md_path']}",
                            f"- 网格JSON: {grid_export['json_path']}",
                            f"- 网格CSV: {grid_export['csv_path']}",
                            f"- 网格Markdown: {grid_export['md_path']}",
                        ]
                    )
                    if export_result.get("baseline_path"):
                        bt_lines.append(f"- 对比基线: {export_result['baseline_path']}")
                    if export_result.get("compare_text"):
                        bt_lines.append(str(export_result["compare_text"]))
                backtest_text = "\n".join(bt_lines)
        else:
            metrics = run_backtest(
                df,
                fee_rate=bt_fee_rate,
                slippage_bps=bt_slippage_bps,
                min_hold_days=bt_min_hold_days,
                signal_confirm_days=bt_signal_confirm_days,
                max_positions=bt_max_positions,
            )
            backtest_text = format_backtest_report(metrics)
            if bt_save and metrics:
                params = {
                    "fee_rate": bt_fee_rate,
                    "slippage_bps": bt_slippage_bps,
                    "min_hold_days": bt_min_hold_days,
                    "signal_confirm_days": bt_signal_confirm_days,
                    "max_positions": bt_max_positions,
                }
                export_result = export_backtest_record(
                    mode="single",
                    symbols=[symbol],
                    start=start,
                    end=end,
                    params=params,
                    metrics=metrics,
                    output_dir=bt_output_dir or CONFIG.backtest_output_dir,
                    compare_last=bt_compare_last,
                )
                bt_lines = [
                    backtest_text,
                    "",
                    "回测文件已导出:",
                    f"- JSON: {export_result['json_path']}",
                    f"- Markdown: {export_result['md_path']}",
                ]
                if export_result.get("baseline_path"):
                    bt_lines.append(f"- 对比基线: {export_result['baseline_path']}")
                if export_result.get("compare_text"):
                    bt_lines.append(str(export_result["compare_text"]))
                backtest_text = "\n".join(bt_lines)

    llm_text = None
    if with_llm:
        llm_text = call_local_qwen(symbol, report, signals)

    return report, chart_path, llm_text, backtest_text


def analyze_portfolio(
    symbols: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    bt_fee_rate: float = 0.001,
    bt_slippage_bps: float = 0.0,
    bt_min_hold_days: int = 1,
    bt_signal_confirm_days: int = 1,
    bt_max_positions: int = 5,
    bt_grid: bool = False,
    bt_grid_fee_rates: Optional[str] = None,
    bt_grid_slippage_bps: Optional[str] = None,
    bt_grid_min_hold_days: Optional[str] = None,
    bt_grid_signal_confirm_days: Optional[str] = None,
    bt_grid_max_positions: Optional[str] = None,
    bt_grid_sort_by: str = "annual_return",
    bt_grid_top: int = 10,
    bt_save: bool = False,
    bt_output_dir: Optional[str] = None,
    bt_compare_last: bool = False,
) -> str:
    normalized_symbols = [normalize_symbol(s) for s in symbols if str(s).strip()]
    if not normalized_symbols:
        return format_error(ErrorCode.INPUT, "组合回测需要至少一个有效股票代码。")

    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start is None:
        start = (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d")

    prepared: dict[str, object] = {}
    failed: list[str] = []
    for symbol in normalized_symbols:
        logger.info("组合回测拉取行情: symbol=%s, start=%s, end=%s", symbol, start, end)
        df = fetch_a_share_history(symbol=symbol, start=start, end=end)
        if df.empty:
            detail = get_last_fetch_error() or "未知错误"
            failed.append(f"{symbol} ({detail})")
            continue
        prepared[symbol] = add_indicators(df)

    if not prepared:
        return format_error(
            ErrorCode.DATA_FETCH,
            "组合回测未获取到任何有效行情数据。"
            + (f"\n失败明细: {'; '.join(failed)}" if failed else ""),
        )

    best_metrics = {}
    best_params = {}
    grid_results: list[dict[str, object]] = []
    grid_total_count = 0

    if bt_grid:
        fee_rates = parse_float_list(bt_grid_fee_rates, bt_fee_rate)
        slippage_bps = parse_float_list(bt_grid_slippage_bps, bt_slippage_bps)
        min_hold_days = parse_int_list(bt_grid_min_hold_days, bt_min_hold_days, min_value=1)
        signal_confirm_days = parse_int_list(
            bt_grid_signal_confirm_days,
            bt_signal_confirm_days,
            min_value=1,
        )
        max_positions = parse_int_list(bt_grid_max_positions, bt_max_positions, min_value=1)
        param_grid = build_backtest_param_grid(
            fee_rates=fee_rates,
            slippage_bps=slippage_bps,
            min_hold_days=min_hold_days,
            signal_confirm_days=signal_confirm_days,
            max_positions=max_positions,
        )
        grid_total_count = len(param_grid)
        grid_results = run_portfolio_grid_backtest(
            symbol_data=prepared,
            param_grid=param_grid,
            sort_by=bt_grid_sort_by,
        )
        if not grid_results:
            return "参数网格回测结果: 无有效结果。"
        best_metrics = grid_results[0].get("metrics") or {}
        best_params = grid_results[0].get("params") or {}
    else:
        metrics = run_portfolio_backtest(
            symbol_data=prepared,
            fee_rate=bt_fee_rate,
            slippage_bps=bt_slippage_bps,
            min_hold_days=bt_min_hold_days,
            signal_confirm_days=bt_signal_confirm_days,
            max_positions=bt_max_positions,
        )
        if not metrics:
            return "组合回测结果: 数据不足或指标缺失，无法回测。"
        best_metrics = metrics
        best_params = {
            "fee_rate": bt_fee_rate,
            "slippage_bps": bt_slippage_bps,
            "min_hold_days": bt_min_hold_days,
            "signal_confirm_days": bt_signal_confirm_days,
            "max_positions": bt_max_positions,
        }

    lines = [
        f"组合回测区间: {start} ~ {end}",
        f"输入标的: {', '.join(normalized_symbols)}",
        f"有效标的: {', '.join(sorted(prepared.keys()))}",
        format_portfolio_backtest_report(best_metrics),
    ]
    if bt_grid:
        lines.extend(
            [
                "",
                "参数网格最佳参数:",
                f"- 手续费率: {float(best_params.get('fee_rate', 0.0)):.4f}",
                f"- 滑点: {float(best_params.get('slippage_bps', 0.0)):.1f}bps",
                f"- 最小持仓天数: {int(best_params.get('min_hold_days', 1))}",
                f"- 信号确认天数: {int(best_params.get('signal_confirm_days', 1))}",
                f"- 最大持仓数: {int(best_params.get('max_positions', 1))}",
                "",
                format_grid_report(
                    results=grid_results,
                    total_count=grid_total_count,
                    sort_by=bt_grid_sort_by,
                    top_n=bt_grid_top,
                ),
            ]
        )
    if bt_save:
        params = best_params
        output_dir = bt_output_dir or CONFIG.backtest_output_dir
        export_result = export_backtest_record(
            mode="portfolio",
            symbols=sorted(prepared.keys()),
            start=start,
            end=end,
            params=params,
            metrics=best_metrics,
            output_dir=output_dir,
            compare_last=bt_compare_last,
            extra={
                "input_symbols": normalized_symbols,
                "effective_symbols": sorted(prepared.keys()),
                "failed_symbols": failed,
                "grid_enabled": bt_grid,
                "grid_sort_by": bt_grid_sort_by if bt_grid else "",
                "grid_total_count": grid_total_count if bt_grid else 1,
            },
        )
        lines.extend(["回测文件已导出:", f"- 最优JSON: {export_result['json_path']}", f"- 最优Markdown: {export_result['md_path']}"])
        if bt_grid:
            grid_export = export_grid_results(
                mode="portfolio",
                symbols=sorted(prepared.keys()),
                start=start,
                end=end,
                sort_by=bt_grid_sort_by,
                results=grid_results,
                output_dir=output_dir,
            )
            lines.extend(
                [
                    f"- 网格JSON: {grid_export['json_path']}",
                    f"- 网格CSV: {grid_export['csv_path']}",
                    f"- 网格Markdown: {grid_export['md_path']}",
                ]
            )
        if export_result.get("baseline_path"):
            lines.append(f"- 对比基线: {export_result['baseline_path']}")
        if export_result.get("compare_text"):
            lines.append(str(export_result["compare_text"]))
    if failed:
        lines.append(f"未纳入标的: {'; '.join(failed)}")
    return "\n".join(lines)
