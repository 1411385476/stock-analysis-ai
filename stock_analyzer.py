"""Backward-compatible CLI entry for the modular stock analyzer."""

from app.cli import has_screen_request, main, parse_args
from app.config import CONFIG
from app.utils import dedupe_keep_order, detect_network_restriction_hint, normalize_symbol
from backtest.engine import format_backtest_report, run_backtest
from data.providers.market_data import (
    fetch_a_share_history,
    fetch_ashare_spot_snapshot,
    get_last_fetch_error,
    resolve_yf_symbol,
)
from data.repository.snapshot_store import (
    format_screen_report,
    screen_ashare_snapshot,
    sync_ashare_snapshots,
    write_snapshot_batches,
)
from factors.indicators import add_indicators
from llm.qwen_client import call_local_qwen, get_last_qwen_error
from portfolio.store import load_portfolio, save_portfolio
from report.charting import generate_chart
from report.renderer import build_report
from strategy.signal_engine import strategy_signals
from app.analyzer import analyze_stock

PORTFOLIO_FILE = CONFIG.portfolio_file
CHART_DIR = CONFIG.chart_dir
DATA_DIR = CONFIG.data_dir
ASHARE_SNAPSHOT_DIR = CONFIG.ashare_snapshot_dir
ASHARE_LATEST_FILE = CONFIG.ashare_latest_file


if __name__ == "__main__":
    raise SystemExit(main())
