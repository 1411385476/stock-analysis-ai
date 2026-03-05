from contextlib import contextmanager
from datetime import datetime
import os
import socket
from typing import Callable, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.logging_config import get_logger
from app.utils import dedupe_keep_order
from app.utils import normalize_symbol

logger = get_logger(__name__)
LAST_FETCH_ERROR: Optional[str] = None
_DEFAULT_SOCKET_TIMEOUT_SEC = float(os.getenv("OPENCLAW_YF_SOCKET_TIMEOUT_SEC", "8"))
UNIVERSE_ALL = "all"
UNIVERSE_HS300 = "hs300"
UNIVERSE_ZZ500 = "zz500"
_UNIVERSE_TO_INDEX_CODE = {
    UNIVERSE_HS300: "000300",
    UNIVERSE_ZZ500: "000905",
}
_UNIVERSE_ALIASES = {
    "all": UNIVERSE_ALL,
    "a": UNIVERSE_ALL,
    "full": UNIVERSE_ALL,
    "hs300": UNIVERSE_HS300,
    "000300": UNIVERSE_HS300,
    "沪深300": UNIVERSE_HS300,
    "zz500": UNIVERSE_ZZ500,
    "000905": UNIVERSE_ZZ500,
    "中证500": UNIVERSE_ZZ500,
}


def _init_yfinance_cache() -> None:
    """
    Point yfinance tz cache to a writable path.
    Some sandboxed sessions have read-only HOME, which can trigger
    sqlite readonly errors in yfinance cache writes.
    """
    cache_setter = getattr(yf, "set_tz_cache_location", None)
    if not callable(cache_setter):
        return
    try:
        cache_setter("/tmp/openclaw-yfinance")
    except Exception:
        # Cache path setup is a best-effort optimization; fetch can still proceed.
        pass


@contextmanager
def _temporary_socket_timeout(seconds: float):
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(seconds)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous)


_init_yfinance_cache()


@contextmanager
def _temporary_disable_proxies():
    """
    Temporarily clear common proxy env vars.
    Useful when a stale proxy causes ProxyError for direct data APIs.
    """
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    ]
    saved = {k: os.environ.get(k) for k in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _looks_like_proxy_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()
    return "proxyerror" in lower or "unable to connect to proxy" in lower


def _call_akshare_with_proxy_fallback(call: Callable[[], pd.DataFrame], operation: str) -> pd.DataFrame:
    """
    Call an AkShare API once with current env; if proxy errors are detected,
    retry once with proxy env vars temporarily disabled.
    """
    try:
        return call()
    except Exception as first_exc:
        if not _looks_like_proxy_error(first_exc):
            raise
        logger.warning("%s 首次请求命中代理错误，尝试禁用代理后重试: %s", operation, first_exc)
        with _temporary_disable_proxies():
            return call()


def get_last_fetch_error() -> Optional[str]:
    return LAST_FETCH_ERROR


def normalize_universe(universe: str) -> str:
    raw = str(universe or UNIVERSE_ALL).strip().lower()
    if raw in _UNIVERSE_ALIASES:
        return _UNIVERSE_ALIASES[raw]
    return raw


def _extract_symbols_from_constituents(df: pd.DataFrame) -> set[str]:
    if df is None or df.empty:
        return set()

    candidate_columns = [
        "品种代码",
        "成分券代码",
        "代码",
        "symbol",
        "stock_code",
        "证券代码",
    ]
    chosen_col: Optional[str] = None
    for col in candidate_columns:
        if col in df.columns:
            chosen_col = col
            break

    if not chosen_col:
        for col in df.columns:
            if "代码" in str(col):
                chosen_col = col
                break

    if not chosen_col:
        return set()

    out = (
        df[chosen_col]
        .astype(str)
        .str.extract(r"(\d{6})", expand=False)
        .dropna()
        .str.zfill(6)
    )
    return set(out.tolist())


def fetch_universe_symbols(universe: str = UNIVERSE_ALL) -> Optional[set[str]]:
    normalized = normalize_universe(universe)
    if normalized == UNIVERSE_ALL:
        return None

    index_code = _UNIVERSE_TO_INDEX_CODE.get(normalized)
    if not index_code:
        raise ValueError(f"不支持的 universe: {universe}")

    try:
        import akshare as ak
    except Exception as exc:
        raise RuntimeError(f"无法导入 akshare: {type(exc).__name__}: {exc}") from exc

    fetch_attempts: list[tuple[str, Callable[[], pd.DataFrame]]] = []
    if hasattr(ak, "index_stock_cons"):
        fetch_attempts.append(("index_stock_cons", lambda: ak.index_stock_cons(symbol=index_code)))
    if hasattr(ak, "index_stock_cons_csindex"):
        fetch_attempts.append(("index_stock_cons_csindex", lambda: ak.index_stock_cons_csindex(symbol=index_code)))
    if hasattr(ak, "stock_zh_index_cons_csindex"):
        fetch_attempts.append(("stock_zh_index_cons_csindex", lambda: ak.stock_zh_index_cons_csindex(symbol=index_code)))

    errors: list[str] = []
    for name, fn in fetch_attempts:
        try:
            df = _call_akshare_with_proxy_fallback(fn, f"{name}({index_code})")
            symbols = _extract_symbols_from_constituents(df)
            if symbols:
                return symbols
            errors.append(f"{name}: 返回为空或字段无法识别")
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    if not fetch_attempts:
        raise RuntimeError("akshare 当前版本不包含指数成分股接口")
    raise RuntimeError(f"获取 {normalized} 成分股失败: {' | '.join(errors)}")


def resolve_yf_symbol(symbol: str) -> str:
    s = normalize_symbol(symbol)
    if "." in s:
        return s
    if s.isdigit() and len(s) == 6:
        if s.startswith(("6", "5", "9")):
            return f"{s}.SS"
        if s.startswith(("0", "2", "3")):
            return f"{s}.SZ"
        if s.startswith(("4", "8")):
            return f"{s}.BJ"
    if s.isdigit() and len(s) == 5:
        return f"{s}.HK"
    return s


def _is_mainland_a_share_symbol(symbol: str) -> bool:
    s = normalize_symbol(symbol)
    if "." in s:
        code, market = s.split(".", 1)
        return code.isdigit() and len(code) == 6 and market in {"SS", "SZ", "BJ"}
    return s.isdigit() and len(s) == 6


def _resolve_akshare_symbol(symbol: str) -> Optional[str]:
    s = normalize_symbol(symbol)
    if "." in s:
        code, market = s.split(".", 1)
        if code.isdigit() and len(code) == 6 and market in {"SS", "SZ", "BJ"}:
            return code
        return None
    if s.isdigit() and len(s) == 6:
        return s
    return None


def _history_provider_order(symbol: str) -> list[str]:
    """
    Decide provider order for history fetch.
    OPENCLAW_HISTORY_PROVIDERS supports: auto, akshare, yfinance (comma-separated).
    Example: OPENCLAW_HISTORY_PROVIDERS=akshare,yfinance
    """
    configured = os.getenv("OPENCLAW_HISTORY_PROVIDERS", "auto")
    raw_items = [item.strip().lower() for item in configured.split(",") if item.strip()]
    if not raw_items:
        raw_items = ["auto"]

    order: list[str] = []
    for item in raw_items:
        if item == "auto":
            if _is_mainland_a_share_symbol(symbol):
                order.extend(["akshare", "yfinance"])
            else:
                order.append("yfinance")
            continue
        if item in {"akshare", "yfinance"}:
            order.append(item)

    if not order:
        order = ["yfinance"]
    return dedupe_keep_order(order)


def _normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" not in df.columns:
        first_col = df.columns[0]
        df = df.rename(columns={first_col: "Date"})

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    try:
        df["Date"] = df["Date"].dt.tz_localize(None)
    except TypeError:
        pass

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    optional_cols = ["Amount", "Amplitude", "PctChange", "Change", "Turnover"]
    for col in optional_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan

    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"])
    if df.empty:
        return pd.DataFrame()
    return df.sort_values("Date").set_index("Date")


def _fetch_history_yfinance(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, Optional[str]]:
    yf_symbol = resolve_yf_symbol(symbol)
    try:
        with _temporary_socket_timeout(_DEFAULT_SOCKET_TIMEOUT_SEC):
            raw = yf.Ticker(yf_symbol).history(
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                actions=False,
                timeout=_DEFAULT_SOCKET_TIMEOUT_SEC,
            )
    except Exception as exc:
        return pd.DataFrame(), f"yfinance请求异常: {type(exc).__name__}: {exc}"

    if raw is None or raw.empty:
        return (
            pd.DataFrame(),
            f"yfinance返回空数据: symbol={yf_symbol}, start={start}, end={end}",
        )

    normalized = _normalize_ohlcv_frame(raw.copy().reset_index())
    if normalized.empty:
        return pd.DataFrame(), "yfinance数据清洗后为空（OHLCV存在缺失或字段异常）"
    return normalized, None


def _fetch_history_akshare(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, Optional[str]]:
    ak_symbol = _resolve_akshare_symbol(symbol)
    if not ak_symbol:
        return pd.DataFrame(), "akshare仅支持A股6位代码（含 .SS/.SZ/.BJ）"

    try:
        import akshare as ak
    except Exception as exc:
        return pd.DataFrame(), f"无法导入akshare: {type(exc).__name__}: {exc}"

    start_date = start.replace("-", "")
    end_date = end.replace("-", "")
    try:
        with _temporary_socket_timeout(_DEFAULT_SOCKET_TIMEOUT_SEC):
            raw = _call_akshare_with_proxy_fallback(
                lambda: ak.stock_zh_a_hist(
                    symbol=ak_symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="",
                ),
                f"stock_zh_a_hist({ak_symbol})",
            )
    except Exception as exc:
        return pd.DataFrame(), f"akshare请求异常: {type(exc).__name__}: {exc}"

    if raw is None or raw.empty:
        return (
            pd.DataFrame(),
            f"akshare返回空数据: symbol={ak_symbol}, start={start_date}, end={end_date}",
        )

    col_map = {
        "日期": "Date",
        "开盘": "Open",
        "最高": "High",
        "最低": "Low",
        "收盘": "Close",
        "成交量": "Volume",
        "成交额": "Amount",
        "振幅": "Amplitude",
        "涨跌幅": "PctChange",
        "涨跌额": "Change",
        "换手率": "Turnover",
    }
    normalized = _normalize_ohlcv_frame(raw.rename(columns=col_map).copy())
    if normalized.empty:
        return pd.DataFrame(), f"akshare字段不完整或清洗后为空: 实际字段={list(raw.columns)}"
    return normalized, None


def fetch_a_share_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily bars and normalize OHLCV schema with fast provider fallback."""
    global LAST_FETCH_ERROR
    LAST_FETCH_ERROR = None

    provider_errors: list[str] = []
    for provider in _history_provider_order(symbol):
        if provider == "akshare":
            data, error = _fetch_history_akshare(symbol=symbol, start=start, end=end)
        else:
            data, error = _fetch_history_yfinance(symbol=symbol, start=start, end=end)

        if not data.empty:
            logger.info("历史行情获取成功: provider=%s, symbol=%s, rows=%s", provider, symbol, len(data))
            return data
        if error:
            provider_errors.append(f"[{provider}] {error}")

    LAST_FETCH_ERROR = " | ".join(provider_errors) if provider_errors else "历史行情获取失败（未知错误）"
    logger.error(LAST_FETCH_ERROR)
    return pd.DataFrame()


def fetch_ashare_spot_snapshot() -> pd.DataFrame:
    """
    Fetch full A-share market snapshot from AkShare.
    Returns a normalized table for local screening/storage.
    """
    try:
        import akshare as ak
    except Exception as exc:
        err = f"无法导入 akshare: {type(exc).__name__}: {exc}"
        logger.error(err)
        raise RuntimeError(err) from exc

    raw = pd.DataFrame()
    attempt_errors: list[str] = []
    source_attempts: list[tuple[str, Callable[[], pd.DataFrame]]] = [
        ("eastmoney", lambda: ak.stock_zh_a_spot_em()),
        ("sina", lambda: ak.stock_zh_a_spot()),
    ]

    for source_name, fn in source_attempts:
        try:
            raw = _call_akshare_with_proxy_fallback(fn, f"stock_zh_a_spot[{source_name}]")
            if raw is not None and not raw.empty:
                logger.info("A股快照获取成功: source=%s, rows=%s", source_name, len(raw))
                break
            attempt_errors.append(f"{source_name}: 返回空数据")
        except Exception as exc:
            attempt_errors.append(f"{source_name}: {type(exc).__name__}: {exc}")

    if raw is None or raw.empty:
        err = f"拉取A股全市场快照失败: {' | '.join(attempt_errors)}"
        logger.error(err)
        raise RuntimeError(err)

    col_map = {
        "代码": "symbol",
        "名称": "name",
        "最新价": "price",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "最高": "high",
        "最低": "low",
        "今开": "open",
        "昨收": "prev_close",
        "量比": "volume_ratio",
        "换手率": "turnover",
        "市盈率-动态": "pe_ttm",
        "市净率": "pb",
        "总市值": "total_market_cap",
        "流通市值": "float_market_cap",
        "涨速": "speed",
        "5分钟涨跌": "change_5m",
        "60日涨跌幅": "pct_change_60d",
        "年初至今涨跌幅": "pct_change_ytd",
    }

    df = raw.rename(columns=col_map).copy()
    if "symbol" not in df.columns or "name" not in df.columns:
        err = f"A股快照字段异常: {list(df.columns)}"
        logger.error(err)
        raise RuntimeError(err)

    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)
    numeric_cols = [
        "price",
        "pct_change",
        "change",
        "volume",
        "amount",
        "amplitude",
        "high",
        "low",
        "open",
        "prev_close",
        "volume_ratio",
        "turnover",
        "pe_ttm",
        "pb",
        "total_market_cap",
        "float_market_cap",
        "speed",
        "change_5m",
        "pct_change_60d",
        "pct_change_ytd",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["snapshot_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return df
