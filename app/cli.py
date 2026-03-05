import argparse

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
from llm.qwen_client import get_last_qwen_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="股票行情分析器（单股分析 + A股全市场分批同步 + 条件筛选）")
    parser.add_argument("symbol", nargs="?", help="股票代码，例如 600519")
    parser.add_argument("--portfolio-symbols", help="组合回测股票列表，逗号分隔，例如 600519,000001,300750")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--no-llm", action="store_true", help="禁用Qwen解读")
    parser.add_argument("--backtest", action="store_true", help="启用策略模板回测")
    parser.add_argument("--bt-fee-rate", type=float, default=0.001, help="回测手续费率（单边），默认0.001")
    parser.add_argument("--bt-slippage-bps", type=float, default=0.0, help="回测单边滑点（bps），默认0")
    parser.add_argument("--bt-min-hold-days", type=int, default=1, help="回测最小持仓天数，默认1")
    parser.add_argument("--bt-signal-confirm-days", type=int, default=1, help="回测信号确认天数，默认1")
    parser.add_argument("--bt-max-positions", type=int, default=1, help="回测最大持仓数（组合模式生效）")
    parser.add_argument("--bt-grid", action="store_true", help="启用参数网格回测")
    parser.add_argument("--bt-grid-fee-rates", help="网格手续费率列表，逗号分隔，例如 0.0005,0.001")
    parser.add_argument("--bt-grid-slippage-bps", help="网格滑点列表(bps)，逗号分隔，例如 0,8,12")
    parser.add_argument("--bt-grid-min-hold-days", help="网格最小持仓天数列表，逗号分隔，例如 1,3,5")
    parser.add_argument("--bt-grid-signal-confirm-days", help="网格信号确认天数列表，逗号分隔，例如 1,2,3")
    parser.add_argument("--bt-grid-max-positions", help="网格最大持仓数列表，逗号分隔，例如 1,2,3")
    parser.add_argument("--bt-grid-sort-by", default="annual_return", help="网格排序字段，默认 annual_return")
    parser.add_argument("--bt-grid-top", type=int, default=10, help="网格结果展示Top N，默认10")
    parser.add_argument("--bt-save", action="store_true", help="导出回测结果到 JSON/Markdown 文件")
    parser.add_argument("--bt-output-dir", help="回测结果导出目录（默认 data/backtests）")
    parser.add_argument("--bt-compare-last", action="store_true", help="导出回测时自动对比同目标最近一次记录")
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
            print(
                analyze_portfolio(
                    symbols=symbols,
                    start=args.start,
                    end=args.end,
                    bt_fee_rate=args.bt_fee_rate,
                    bt_slippage_bps=args.bt_slippage_bps,
                    bt_min_hold_days=args.bt_min_hold_days,
                    bt_signal_confirm_days=args.bt_signal_confirm_days,
                    bt_max_positions=args.bt_max_positions,
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
                )
            )
            return 0
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

    text, chart, llm_result, bt_result = analyze_stock(
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
    )

    print(text)
    if bt_result:
        print("\n" + bt_result)
    if chart:
        print(f"\n图表已保存: {chart}")
    if llm_result:
        print("\nQwen 解读:\n")
        print(llm_result)
    elif not args.no_llm and chart:
        print("\nQwen 解读不可用（请检查本地接口、模型名或环境变量）。")
        detail = get_last_qwen_error()
        if detail:
            print(f"详细原因: {format_error(ErrorCode.LLM_CALL, detail)}")

    return 0
