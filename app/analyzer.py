from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.errors import ErrorCode, format_error
from app.logging_config import get_logger
from app.utils import detect_network_restriction_hint, normalize_symbol
from backtest.engine import format_backtest_report, run_backtest
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
        metrics = run_backtest(df)
        backtest_text = format_backtest_report(metrics)

    llm_text = None
    if with_llm:
        llm_text = call_local_qwen(symbol, report, signals)

    return report, chart_path, llm_text, backtest_text
