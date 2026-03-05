import argparse

from app.analyzer import analyze_stock
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
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--no-llm", action="store_true", help="禁用Qwen解读")
    parser.add_argument("--backtest", action="store_true", help="启用策略模板回测")
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
