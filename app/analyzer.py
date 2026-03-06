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
from llm.qwen_client import call_local_qwen, get_last_qwen_structured
from llm.summarizer import (
    evaluate_low_temp_stability,
    evaluate_schema_completeness,
    format_low_temp_stability_report,
)
from portfolio.industry import load_industry_map
from portfolio.risk import (
    evaluate_portfolio_risk,
    export_portfolio_risk_report,
    format_portfolio_risk_summary,
)
from report.analysis_artifacts import build_analysis_record, export_analysis_record
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
    bt_stop_loss_pct: float = 0.0,
    bt_take_profit_pct: float = 0.0,
    bt_drawdown_circuit_pct: float = 0.0,
    bt_circuit_cooldown_days: int = 0,
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
    analysis_save: bool = False,
    analysis_output_dir: Optional[str] = None,
    llm_stability_runs: int = 1,
    llm_stability_temperature: float = 0.1,
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
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
            for params in param_grid:
                params["stop_loss_pct"] = max(float(bt_stop_loss_pct), 0.0)
                params["take_profit_pct"] = max(float(bt_take_profit_pct), 0.0)
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
                    f"- 止损比例: {float(best_params.get('stop_loss_pct', 0.0)) * 100:.2f}%",
                    f"- 止盈比例: {float(best_params.get('take_profit_pct', 0.0)) * 100:.2f}%",
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
                stop_loss_pct=bt_stop_loss_pct,
                take_profit_pct=bt_take_profit_pct,
            )
            backtest_text = format_backtest_report(metrics)
            if bt_save and metrics:
                params = {
                    "fee_rate": bt_fee_rate,
                    "slippage_bps": bt_slippage_bps,
                    "min_hold_days": bt_min_hold_days,
                    "signal_confirm_days": bt_signal_confirm_days,
                    "max_positions": bt_max_positions,
                    "stop_loss_pct": bt_stop_loss_pct,
                    "take_profit_pct": bt_take_profit_pct,
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
    analysis_export_text = None
    llm_stability_text = None
    llm_stability_payload = None
    if with_llm:
        runs = max(int(llm_stability_runs), 1)
        temperature = max(float(llm_stability_temperature), 0.0)
        stability_samples = []
        stability_mode = runs > 1
        for _ in range(runs):
            current = call_local_qwen(
                symbol,
                report,
                signals,
                temperature=temperature,
                stability_mode=stability_mode,
            )
            if current:
                llm_text = current
            structured_item = get_last_qwen_structured()
            if structured_item:
                stability_samples.append(structured_item)
        if runs > 1:
            llm_stability_payload = evaluate_low_temp_stability(stability_samples, target_runs=runs)
            llm_stability_text = format_low_temp_stability_report(llm_stability_payload)
    llm_structured = get_last_qwen_structured()

    if analysis_save:
        record = build_analysis_record(
            symbol=symbol,
            start=start,
            end=end,
            report_text=report,
            signals=signals,
            chart_path=chart_path,
            llm_text=llm_text,
            llm_structured=llm_structured,
            llm_stability=llm_stability_payload,
            backtest_text=backtest_text,
        )
        export_result = export_analysis_record(record, analysis_output_dir or CONFIG.analysis_output_dir)
        quality = evaluate_schema_completeness(llm_structured)
        analysis_export_text = "\n".join(
            [
                "分析文件已导出:",
                f"- JSON: {export_result['json_path']}",
                f"- Markdown: {export_result['md_path']}",
                (
                    f"- LLM Schema齐全率: {quality.get('completeness_pct', 0.0):.2f}% "
                    f"({int(quality.get('filled_fields', 0))}/{int(quality.get('total_fields', 0))})"
                ),
            ]
        )

    return report, chart_path, llm_text, backtest_text, analysis_export_text, llm_stability_text


def analyze_portfolio(
    symbols: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    bt_fee_rate: float = 0.001,
    bt_slippage_bps: float = 0.0,
    bt_min_hold_days: int = 1,
    bt_signal_confirm_days: int = 1,
    bt_max_positions: int = 5,
    bt_stop_loss_pct: float = 0.0,
    bt_take_profit_pct: float = 0.0,
    bt_drawdown_circuit_pct: float = 0.0,
    bt_circuit_cooldown_days: int = 0,
    bt_max_industry_weight: float = 1.0,
    bt_max_single_weight: float = 1.0,
    industry_map_file: Optional[str] = None,
    industry_level: str = "auto",
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
    risk_report: bool = False,
    risk_output_dir: Optional[str] = None,
    risk_max_drawdown_limit: float = 0.15,
    risk_max_single_weight: float = 0.35,
    risk_max_industry_weight: float = 0.6,
    risk_min_holdings: int = 3,
) -> str:
    normalized_symbols = [normalize_symbol(s) for s in symbols if str(s).strip()]
    if not normalized_symbols:
        return format_error(ErrorCode.INPUT, "组合回测需要至少一个有效股票代码。")
    industry_map: dict[str, str] = {}
    if industry_map_file:
        try:
            industry_map = load_industry_map(industry_map_file, level=industry_level)
        except FileNotFoundError:
            return format_error(
                ErrorCode.INPUT,
                f"行业映射文件不存在: {industry_map_file}。可先移除 --industry-map-file 参数，或创建 CSV（示例列: symbol,industry）。",
            )
        except Exception as exc:
            return format_error(ErrorCode.INPUT, f"行业映射文件读取失败: {type(exc).__name__}: {exc}")

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
        for params in param_grid:
            params["stop_loss_pct"] = max(float(bt_stop_loss_pct), 0.0)
            params["take_profit_pct"] = max(float(bt_take_profit_pct), 0.0)
            params["drawdown_circuit_pct"] = max(float(bt_drawdown_circuit_pct), 0.0)
            params["circuit_cooldown_days"] = max(int(bt_circuit_cooldown_days), 0)
            params["max_industry_weight"] = min(max(float(bt_max_industry_weight), 0.0), 1.0)
            params["max_single_weight"] = min(max(float(bt_max_single_weight), 0.0), 1.0)
        grid_total_count = len(param_grid)
        grid_results = run_portfolio_grid_backtest(
            symbol_data=prepared,
            param_grid=param_grid,
            sort_by=bt_grid_sort_by,
            industry_map=industry_map,
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
            stop_loss_pct=bt_stop_loss_pct,
            take_profit_pct=bt_take_profit_pct,
            industry_map=industry_map,
            max_industry_weight=bt_max_industry_weight,
            max_single_weight=bt_max_single_weight,
            drawdown_circuit_pct=bt_drawdown_circuit_pct,
            circuit_cooldown_days=bt_circuit_cooldown_days,
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
            "stop_loss_pct": bt_stop_loss_pct,
            "take_profit_pct": bt_take_profit_pct,
            "drawdown_circuit_pct": bt_drawdown_circuit_pct,
            "circuit_cooldown_days": bt_circuit_cooldown_days,
            "max_industry_weight": bt_max_industry_weight,
            "max_single_weight": bt_max_single_weight,
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
                f"- 止损比例: {float(best_params.get('stop_loss_pct', 0.0)) * 100:.2f}%",
                f"- 止盈比例: {float(best_params.get('take_profit_pct', 0.0)) * 100:.2f}%",
                f"- 回撤熔断阈值: {float(best_params.get('drawdown_circuit_pct', 0.0)) * 100:.2f}%",
                f"- 熔断冷却天数: {int(best_params.get('circuit_cooldown_days', 0))}",
                f"- 行业权重上限: {float(best_params.get('max_industry_weight', 1.0)) * 100:.2f}%",
                f"- 单票权重上限: {float(best_params.get('max_single_weight', 1.0)) * 100:.2f}%",
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
    if risk_report:
        risk = evaluate_portfolio_risk(
            metrics=best_metrics,
            input_symbols=normalized_symbols,
            effective_symbols=sorted(prepared.keys()),
            failed_symbols=failed,
            period_start=start,
            period_end=end,
            max_drawdown_limit=risk_max_drawdown_limit,
            max_single_weight=risk_max_single_weight,
            max_industry_weight=risk_max_industry_weight,
            min_holdings=risk_min_holdings,
        )
        lines.extend(["", format_portfolio_risk_summary(risk)])
        risk_export = export_portfolio_risk_report(risk, risk_output_dir or CONFIG.risk_report_output_dir)
        lines.extend(
            [
                "风险报告已导出:",
                f"- JSON: {risk_export['json_path']}",
                f"- Markdown: {risk_export['md_path']}",
            ]
        )
    if failed:
        lines.append(f"未纳入标的: {'; '.join(failed)}")
    return "\n".join(lines)
