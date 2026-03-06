import argparse
import json

from app.analyzer import analyze_portfolio, analyze_stock
from app.config import CONFIG
from app.errors import ErrorCode, format_error
from app.logging_config import setup_logging
from data.repository.snapshot_store import (
    export_candidate_pool,
    format_screen_report,
    screen_ashare_snapshot,
    sync_ashare_snapshots,
)
from llm.qwen_client import get_last_qwen_error, get_last_qwen_structured
from llm.summarizer import evaluate_schema_completeness
from report.standard_api import export_standard_snapshot


def _is_error_text(text: object) -> bool:
    return isinstance(text, str) and text.startswith("[E_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="股票行情分析器（单股分析 + A股全市场分批同步 + 条件筛选）")
    parser.add_argument("symbol", nargs="?", help="股票代码，例如 600519")
    parser.add_argument("--portfolio-symbols", help="组合回测股票列表，逗号分隔，例如 600519,000001,300750")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--no-llm", action="store_true", help="禁用Qwen解读")
    parser.add_argument("--llm-json", action="store_true", help="输出Qwen结构化JSON结果（M5）")
    parser.add_argument("--llm-stability-runs", type=int, default=1, help="低温度稳定性评估轮数，默认1(不评估)")
    parser.add_argument("--llm-stability-temperature", type=float, default=0.1, help="低温度稳定性评估温度，默认0.1")
    parser.add_argument("--analysis-save", action="store_true", help="导出单股分析记录（JSON/Markdown）")
    parser.add_argument("--analysis-output-dir", help="单股分析导出目录（默认 data/analysis_reports）")
    parser.add_argument("--standard-json-export", action="store_true", help="导出标准化 JSON 快照（M7 Week4）")
    parser.add_argument("--standard-json-data-dir", default=CONFIG.data_dir, help="标准化 JSON 数据目录（默认 data/）")
    parser.add_argument("--standard-json-output", help="标准化 JSON 输出路径（默认 <data_dir>/api/standard_snapshot_latest.json）")
    parser.add_argument("--standard-json-top", type=int, default=20, help="候选池标准输出 topN，默认20")
    parser.add_argument("--backtest", action="store_true", help="启用策略模板回测")
    parser.add_argument("--bt-fee-rate", type=float, default=0.001, help="回测手续费率（单边），默认0.001")
    parser.add_argument("--bt-slippage-bps", type=float, default=0.0, help="回测单边滑点（bps），默认0")
    parser.add_argument("--bt-min-hold-days", type=int, default=1, help="回测最小持仓天数，默认1")
    parser.add_argument("--bt-signal-confirm-days", type=int, default=1, help="回测信号确认天数，默认1")
    parser.add_argument("--bt-max-positions", type=int, default=1, help="回测最大持仓数（组合模式生效）")
    parser.add_argument("--bt-stop-loss-pct", type=float, default=0.0, help="回测止损比例(0-1)，默认0(禁用)")
    parser.add_argument("--bt-take-profit-pct", type=float, default=0.0, help="回测止盈比例(0-1)，默认0(禁用)")
    parser.add_argument("--bt-drawdown-circuit-pct", type=float, default=0.0, help="回测回撤熔断阈值(0-1)，默认0(禁用)")
    parser.add_argument("--bt-circuit-cooldown-days", type=int, default=0, help="回撤熔断冷却天数，默认0")
    parser.add_argument("--bt-max-industry-weight", type=float, default=1.0, help="行业权重上限(0-1)，默认1.0")
    parser.add_argument("--bt-max-single-weight", type=float, default=1.0, help="单票权重上限(0-1)，默认1.0")
    parser.add_argument("--bt-target-volatility", type=float, default=0.0, help="组合目标年化波动率(0-1)，默认0(禁用)")
    parser.add_argument("--bt-vol-lookback-days", type=int, default=20, help="波动率控制回看天数，默认20")
    parser.add_argument("--bt-min-capital-utilization", type=float, default=0.0, help="资金利用率下限(0-1)，默认0")
    parser.add_argument("--bt-max-capital-utilization", type=float, default=1.0, help="资金利用率上限(0-1)，默认1")
    parser.add_argument(
        "--bt-rebalance-frequency",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="组合再平衡频率: daily/weekly/monthly，默认 daily",
    )
    parser.add_argument("--bt-rebalance-weekday", type=int, default=0, help="周再平衡日(0=周一..4=周五)，默认0")
    parser.add_argument("--industry-map-file", help="行业映射CSV（含 symbol/code 与 industry/行业 列）")
    parser.add_argument("--industry-level", choices=["auto", "l1", "l2"], default="auto", help="行业层级: auto/l1/l2，默认 auto")
    parser.add_argument("--bt-grid", action="store_true", help="启用参数网格回测")
    parser.add_argument("--bt-grid-fee-rates", help="网格手续费率列表，逗号分隔，例如 0.0005,0.001")
    parser.add_argument("--bt-grid-slippage-bps", help="网格滑点列表(bps)，逗号分隔，例如 0,8,12")
    parser.add_argument("--bt-grid-min-hold-days", help="网格最小持仓天数列表，逗号分隔，例如 1,3,5")
    parser.add_argument("--bt-grid-signal-confirm-days", help="网格信号确认天数列表，逗号分隔，例如 1,2,3")
    parser.add_argument("--bt-grid-max-positions", help="网格最大持仓数列表，逗号分隔，例如 1,2,3")
    parser.add_argument("--bt-grid-sort-by", default="annual_return", help="网格排序字段，默认 annual_return")
    parser.add_argument("--bt-grid-top", type=int, default=10, help="网格结果展示Top N，默认10")
    parser.add_argument("--bt-walk-forward", action="store_true", help="启用Walk-forward滚动评估（组合模式）")
    parser.add_argument("--bt-wf-train-days", type=int, default=126, help="Walk-forward训练窗口交易日，默认126")
    parser.add_argument("--bt-wf-test-days", type=int, default=63, help="Walk-forward测试窗口交易日，默认63")
    parser.add_argument("--bt-wf-step-days", type=int, default=21, help="Walk-forward滚动步长交易日，默认21")
    parser.add_argument("--bt-wf-sort-by", default="annual_return", help="Walk-forward训练段选参排序字段，默认 annual_return")
    parser.add_argument("--bt-save", action="store_true", help="导出回测结果到 JSON/Markdown 文件")
    parser.add_argument("--bt-output-dir", help="回测结果导出目录（默认 data/backtests）")
    parser.add_argument("--bt-compare-last", action="store_true", help="导出回测时自动对比同目标最近一次记录")
    parser.add_argument("--risk-report", action="store_true", help="输出并导出组合风险报告（Markdown/JSON）")
    parser.add_argument("--risk-output-dir", help="风险报告导出目录（默认 data/risk_reports）")
    parser.add_argument("--risk-max-drawdown-limit", type=float, default=0.15, help="风险阈值：最大回撤上限(正数)，默认0.15")
    parser.add_argument("--risk-max-single-weight", type=float, default=0.35, help="风险阈值：单票权重上限，默认0.35")
    parser.add_argument("--risk-max-industry-weight", type=float, default=0.6, help="风险阈值：行业权重上限，默认0.6")
    parser.add_argument("--risk-min-holdings", type=int, default=3, help="风险阈值：最少持仓标的数，默认3")
    parser.add_argument("--sync-a-share", action="store_true", help="分批拉取A股全市场快照并落盘")
    parser.add_argument("--scan", action="store_true", help="执行候选池扫描（可与 --universe 配合）")
    parser.add_argument("--batch-size", type=int, default=300, help="快照分批文件大小，默认300")
    parser.add_argument("--interval-seconds", type=int, default=0, help="定时拉取间隔秒数，默认0(不循环)")
    parser.add_argument("--runs", type=int, default=1, help="定时拉取轮数，默认1")
    parser.add_argument("--snapshot-file", default=CONFIG.ashare_latest_file, help="筛选使用的快照文件路径")
    parser.add_argument("--keyword", help="按代码或公司名关键词筛选")
    parser.add_argument("--min-price", type=float, help="最小价格筛选")
    parser.add_argument("--max-price", type=float, help="最大价格筛选")
    parser.add_argument("--min-pct-change", type=float, help="最小涨跌幅筛选(%%)")
    parser.add_argument("--max-pct-change", type=float, help="最大涨跌幅筛选(%%)")
    parser.add_argument("--min-turnover", type=float, help="最小换手率筛选(%%)")
    parser.add_argument("--max-turnover", type=float, help="最大换手率筛选(%%)")
    parser.add_argument("--min-market-cap", type=float, help="最小总市值筛选")
    parser.add_argument("--max-market-cap", type=float, help="最大总市值筛选")
    parser.add_argument("--universe", default="all", help="候选池范围: all/hs300/zz500（支持中文别名）")
    parser.add_argument("--sort-by", default="score_total", help="筛选排序字段，默认 score_total")
    parser.add_argument("--asc", action="store_true", help="筛选结果升序排序(默认降序)")
    parser.add_argument("--top", type=int, default=20, help="筛选返回条数，默认20")
    parser.add_argument("--candidate-output-dir", help="候选池导出目录（默认 data/candidate_pools）")
    return parser.parse_args()


def has_screen_request(args: argparse.Namespace) -> bool:
    return any(
        [
            args.keyword,
            args.min_price is not None,
            args.max_price is not None,
            args.min_pct_change is not None,
            args.max_pct_change is not None,
            args.min_turnover is not None,
            args.max_turnover is not None,
            args.min_market_cap is not None,
            args.max_market_cap is not None,
            args.scan,
            str(args.universe).strip().lower() not in {"", "all"},
        ]
    )


def main() -> int:
    setup_logging()
    args = parse_args()
    if args.standard_json_export:
        exported = export_standard_snapshot(
            data_dir=args.standard_json_data_dir,
            output_path=args.standard_json_output,
            candidate_top_n=args.standard_json_top,
        )
        print("标准化JSON已导出:")
        print(f"- JSON: {exported['json_path']}")
        print(f"- Latest: {exported['latest_path']}")
        return 0

    screen_requested = has_screen_request(args)

    if args.sync_a_share:
        print(
            sync_ashare_snapshots(
                batch_size=args.batch_size,
                interval_seconds=args.interval_seconds,
                runs=args.runs,
            )
        )
        if not screen_requested and not args.symbol:
            return 0

    if screen_requested:
        screened_df = screen_ashare_snapshot(
            snapshot_file=args.snapshot_file,
            universe=args.universe,
            keyword=args.keyword,
            min_price=args.min_price,
            max_price=args.max_price,
            min_pct_change=args.min_pct_change,
            max_pct_change=args.max_pct_change,
            min_turnover=args.min_turnover,
            max_turnover=args.max_turnover,
            min_market_cap=args.min_market_cap,
            max_market_cap=args.max_market_cap,
            sort_by=args.sort_by,
            ascending=args.asc,
            top_n=args.top,
        )
        print(format_screen_report(screened_df, args.snapshot_file))
        csv_path, md_path = export_candidate_pool(
            screened_df,
            universe=args.universe,
            output_dir=args.candidate_output_dir,
        )
        if csv_path and md_path:
            print("\n候选池文件已导出:")
            print(f"- CSV: {csv_path}")
            print(f"- Markdown: {md_path}")
        if not args.symbol:
            return 0

    if not args.symbol:
        if args.portfolio_symbols and args.backtest:
            symbols = [item.strip() for item in str(args.portfolio_symbols).split(",") if item.strip()]
            portfolio_text = analyze_portfolio(
                symbols=symbols,
                start=args.start,
                end=args.end,
                bt_fee_rate=args.bt_fee_rate,
                bt_slippage_bps=args.bt_slippage_bps,
                bt_min_hold_days=args.bt_min_hold_days,
                bt_signal_confirm_days=args.bt_signal_confirm_days,
                bt_max_positions=args.bt_max_positions,
                bt_stop_loss_pct=args.bt_stop_loss_pct,
                bt_take_profit_pct=args.bt_take_profit_pct,
                bt_drawdown_circuit_pct=args.bt_drawdown_circuit_pct,
                bt_circuit_cooldown_days=args.bt_circuit_cooldown_days,
                bt_max_industry_weight=args.bt_max_industry_weight,
                bt_max_single_weight=args.bt_max_single_weight,
                bt_target_volatility=args.bt_target_volatility,
                bt_vol_lookback_days=args.bt_vol_lookback_days,
                bt_min_capital_utilization=args.bt_min_capital_utilization,
                bt_max_capital_utilization=args.bt_max_capital_utilization,
                bt_rebalance_frequency=args.bt_rebalance_frequency,
                bt_rebalance_weekday=args.bt_rebalance_weekday,
                industry_map_file=args.industry_map_file,
                industry_level=args.industry_level,
                bt_grid=args.bt_grid,
                bt_grid_fee_rates=args.bt_grid_fee_rates,
                bt_grid_slippage_bps=args.bt_grid_slippage_bps,
                bt_grid_min_hold_days=args.bt_grid_min_hold_days,
                bt_grid_signal_confirm_days=args.bt_grid_signal_confirm_days,
                bt_grid_max_positions=args.bt_grid_max_positions,
                bt_grid_sort_by=args.bt_grid_sort_by,
                bt_grid_top=args.bt_grid_top,
                bt_walk_forward=args.bt_walk_forward,
                bt_wf_train_days=args.bt_wf_train_days,
                bt_wf_test_days=args.bt_wf_test_days,
                bt_wf_step_days=args.bt_wf_step_days,
                bt_wf_sort_by=args.bt_wf_sort_by,
                bt_save=args.bt_save,
                bt_output_dir=args.bt_output_dir,
                bt_compare_last=args.bt_compare_last,
                risk_report=args.risk_report,
                risk_output_dir=args.risk_output_dir,
                risk_max_drawdown_limit=args.risk_max_drawdown_limit,
                risk_max_single_weight=args.risk_max_single_weight,
                risk_max_industry_weight=args.risk_max_industry_weight,
                risk_min_holdings=args.risk_min_holdings,
            )
            print(portfolio_text)
            return 1 if _is_error_text(portfolio_text) else 0
        if args.portfolio_symbols and not args.backtest:
            print(format_error(ErrorCode.INPUT, "组合回测请同时传入 --backtest 参数。"))
            return 1
        print(
            format_error(
                ErrorCode.INPUT,
                "用法示例: python stock_analyzer.py 600519 或 python stock_analyzer.py --sync-a-share",
            )
        )
        return 1

    text, chart, llm_result, bt_result, analysis_result, llm_stability_result = analyze_stock(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        with_llm=not args.no_llm,
        run_bt=args.backtest,
        bt_fee_rate=args.bt_fee_rate,
        bt_slippage_bps=args.bt_slippage_bps,
        bt_min_hold_days=args.bt_min_hold_days,
        bt_signal_confirm_days=args.bt_signal_confirm_days,
        bt_max_positions=args.bt_max_positions,
        bt_stop_loss_pct=args.bt_stop_loss_pct,
        bt_take_profit_pct=args.bt_take_profit_pct,
        bt_drawdown_circuit_pct=args.bt_drawdown_circuit_pct,
        bt_circuit_cooldown_days=args.bt_circuit_cooldown_days,
        bt_grid=args.bt_grid,
        bt_grid_fee_rates=args.bt_grid_fee_rates,
        bt_grid_slippage_bps=args.bt_grid_slippage_bps,
        bt_grid_min_hold_days=args.bt_grid_min_hold_days,
        bt_grid_signal_confirm_days=args.bt_grid_signal_confirm_days,
        bt_grid_max_positions=args.bt_grid_max_positions,
        bt_grid_sort_by=args.bt_grid_sort_by,
        bt_grid_top=args.bt_grid_top,
        bt_save=args.bt_save,
        bt_output_dir=args.bt_output_dir,
        bt_compare_last=args.bt_compare_last,
        analysis_save=args.analysis_save,
        analysis_output_dir=args.analysis_output_dir,
        llm_stability_runs=args.llm_stability_runs,
        llm_stability_temperature=args.llm_stability_temperature,
    )

    print(text)
    if bt_result:
        print("\n" + bt_result)
    if analysis_result:
        print("\n" + analysis_result)
    if chart:
        print(f"\n图表已保存: {chart}")
    if llm_result:
        print("\nQwen 解读:\n")
        print(llm_result)
        if llm_stability_result:
            print("\n" + llm_stability_result)
        if args.llm_json:
            payload = get_last_qwen_structured()
            if payload:
                print("\nQwen 结构化输出:\n")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                quality = evaluate_schema_completeness(payload)
                print(
                    "\nQwen Schema 质量:\n"
                    f"- 齐全率: {quality.get('completeness_pct', 0.0):.2f}% "
                    f"({int(quality.get('filled_fields', 0))}/{int(quality.get('total_fields', 0))})\n"
                    f"- 通过95%阈值: {'是' if bool(quality.get('pass_95pct', False)) else '否'}"
                )
    elif not args.no_llm and chart:
        print("\nQwen 解读不可用（请检查本地接口、模型名或环境变量）。")
        detail = get_last_qwen_error()
        if detail:
            print(f"详细原因: {format_error(ErrorCode.LLM_CALL, detail)}")

    return 1 if _is_error_text(text) else 0
