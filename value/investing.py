from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.config import CONFIG
from app.errors import ErrorCode, format_error
from app.utils import normalize_symbol
from data.providers.market_data import fetch_a_share_history, get_last_fetch_error, resolve_yf_symbol

_VALUE_SCAN_COLUMNS = [
    "value_rank",
    "value_score_total",
    "value_score_pe",
    "value_score_pb",
    "value_score_stability",
    "value_score_scale",
    "symbol",
    "name",
    "price",
    "pe_ttm",
    "pb",
    "total_market_cap",
    "pct_change_60d",
    "value_reason",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: Optional[float]) -> str:
    if value is None or np.isnan(value):
        return "N/A"
    return f"{value * 100:.2f}%"


def _fmt_num(value: Optional[float], digits: int = 2) -> str:
    if value is None or np.isnan(value):
        return "N/A"
    return f"{value:.{digits}f}"


def _rank_score(series: pd.Series, higher_is_better: bool, neutral: float = 50.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(neutral, index=series.index, dtype="float64")
    score = numeric.rank(pct=True, method="average", ascending=higher_is_better) * 100.0
    return score.fillna(neutral).clip(lower=0.0, upper=100.0)


def build_value_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ["pe_ttm", "pb", "total_market_cap", "pct_change_60d", "pct_change", "price"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    pe = out.get("pe_ttm", pd.Series(np.nan, index=out.index)).where(lambda x: x > 0)
    pb = out.get("pb", pd.Series(np.nan, index=out.index)).where(lambda x: x > 0)
    scale = out.get("total_market_cap", pd.Series(np.nan, index=out.index)).where(lambda x: x > 0)
    if "pct_change_60d" in out.columns:
        stability_metric = out["pct_change_60d"].abs()
    elif "pct_change" in out.columns:
        stability_metric = out["pct_change"].abs()
    else:
        stability_metric = pd.Series(np.nan, index=out.index)

    out["value_score_pe"] = _rank_score(pe, higher_is_better=False)
    out["value_score_pb"] = _rank_score(pb, higher_is_better=False)
    out["value_score_scale"] = _rank_score(scale, higher_is_better=True)
    out["value_score_stability"] = _rank_score(stability_metric, higher_is_better=False)
    out["value_score_total"] = (
        out["value_score_pe"] * 0.40
        + out["value_score_pb"] * 0.30
        + out["value_score_stability"] * 0.15
        + out["value_score_scale"] * 0.15
    )
    out["value_rank"] = out["value_score_total"].rank(method="first", ascending=False).astype(int)

    pe_q30 = pe.quantile(0.30) if pe.notna().any() else None
    pb_q30 = pb.quantile(0.30) if pb.notna().any() else None
    scale_q60 = scale.quantile(0.60) if scale.notna().any() else None
    stability_q40 = stability_metric.quantile(0.40) if stability_metric.notna().any() else None

    reasons: list[str] = []
    for _, row in out.iterrows():
        row_reasons: list[str] = []
        pe_val = _safe_float(row.get("pe_ttm"), np.nan)
        pb_val = _safe_float(row.get("pb"), np.nan)
        cap_val = _safe_float(row.get("total_market_cap"), np.nan)
        if "pct_change_60d" in out.columns:
            stab_val = abs(_safe_float(row.get("pct_change_60d"), np.nan))
        else:
            stab_val = abs(_safe_float(row.get("pct_change"), np.nan))

        if pe_q30 is not None and not np.isnan(pe_val) and pe_val <= pe_q30:
            row_reasons.append("PE处于样本低分位")
        if pb_q30 is not None and not np.isnan(pb_val) and pb_val <= pb_q30:
            row_reasons.append("PB处于样本低分位")
        if scale_q60 is not None and not np.isnan(cap_val) and cap_val >= scale_q60:
            row_reasons.append("市值规模较大")
        if stability_q40 is not None and not np.isnan(stab_val) and stab_val <= stability_q40:
            row_reasons.append("中短期波动较温和")
        if not row_reasons:
            row_reasons.append("估值与稳定性信号中性")
        reasons.append("；".join(row_reasons[:3]))

    out["value_reason"] = reasons
    out = out.sort_values("value_score_total", ascending=False, na_position="last")
    return out


def format_value_scan_report(df: pd.DataFrame, snapshot_file: str) -> str:
    if df.empty:
        return f"价值扫描结果为空。快照文件: {snapshot_file}"
    available_cols = [c for c in _VALUE_SCAN_COLUMNS if c in df.columns]
    table = df[available_cols].to_string(index=False)
    return f"价值投资候选（{len(df)}条）:\n{table}"


def export_value_pool(
    df: pd.DataFrame,
    universe: str = "all",
    output_dir: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    if df.empty:
        return None, None
    target_dir = output_dir or os.path.join(CONFIG.data_dir, "value_pools")
    os.makedirs(target_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"value_pool_{str(universe).strip().lower() or 'all'}_{ts}"
    csv_path = os.path.join(target_dir, f"{base}.csv")
    md_path = os.path.join(target_dir, f"{base}.md")

    out_cols = [c for c in _VALUE_SCAN_COLUMNS if c in df.columns]
    df[out_cols].to_csv(csv_path, index=False, encoding="utf-8-sig")

    md_lines = [
        "# 价值投资候选池",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Universe: {universe}",
        f"- 样本数: {len(df)}",
        "",
        "| 排名 | 代码 | 名称 | 价值总分 | PE | PB | 理由 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for _, row in df.head(100).iterrows():
        md_lines.append(
            "| "
            + f"{int(_safe_float(row.get('value_rank'), 0))} | "
            + f"{row.get('symbol', '')} | "
            + f"{row.get('name', '')} | "
            + f"{_safe_float(row.get('value_score_total'), 0.0):.2f} | "
            + f"{_fmt_num(_safe_float(row.get('pe_ttm'), np.nan))} | "
            + f"{_fmt_num(_safe_float(row.get('pb'), np.nan))} | "
            + f"{row.get('value_reason', '')} |"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    return csv_path, md_path


def _load_snapshot_row(symbol: str, snapshot_file: str) -> dict[str, Any]:
    if not snapshot_file or not os.path.exists(snapshot_file):
        return {}
    try:
        df = pd.read_csv(snapshot_file)
    except Exception:
        return {}
    if df.empty:
        return {}
    if "symbol" in df.columns:
        symbol6 = "".join(ch for ch in str(symbol) if ch.isdigit())[-6:]
        key = df["symbol"].astype(str).str.extract(r"(\d{6})", expand=False)
        hit = df[key == symbol6]
        if not hit.empty:
            row = hit.iloc[0].to_dict()
            return {str(k): row[k] for k in row}
    return {}


def _extract_news(ticker: Any, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if limit <= 0:
        return out
    try:
        raw_news = ticker.news
    except Exception:
        raw_news = []
    if not isinstance(raw_news, list):
        return out
    for item in raw_news[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        ts = item.get("providerPublishTime")
        try:
            ts_text = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else "N/A"
        except Exception:
            ts_text = "N/A"
        out.append(
            {
                "date": ts_text,
                "publisher": str(item.get("publisher", "")).strip(),
                "title": title,
                "link": str(item.get("link", "")).strip(),
            }
        )
    return out


def fetch_value_profile(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    news_limit: int = 5,
    snapshot_file: str = CONFIG.ashare_latest_file,
) -> dict[str, Any]:
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start is None:
        start = (datetime.now() - timedelta(days=750)).strftime("%Y-%m-%d")

    bars = fetch_a_share_history(symbol=symbol, start=start, end=end)
    if bars.empty:
        detail = get_last_fetch_error() or "未获取到行情"
        raise RuntimeError(format_error(ErrorCode.DATA_FETCH, f"价值分析无法获取行情: {detail}"))

    close = bars["Close"]
    daily_ret = close.pct_change().dropna()
    ret_1y = np.nan
    if len(close) >= 252:
        ret_1y = close.iloc[-1] / close.iloc[-252] - 1.0
    elif len(close) > 1:
        ret_1y = close.iloc[-1] / close.iloc[0] - 1.0
    realized_vol = daily_ret.std(ddof=0) * np.sqrt(252) if not daily_ret.empty else np.nan
    drawdown = close / close.cummax() - 1.0
    max_drawdown = drawdown.min() if not drawdown.empty else np.nan

    snapshot_row = _load_snapshot_row(symbol=symbol, snapshot_file=snapshot_file)
    yf_symbol = resolve_yf_symbol(symbol)
    ticker = yf.Ticker(yf_symbol)
    info: dict[str, Any] = {}
    try:
        raw_info = ticker.info
        if isinstance(raw_info, dict):
            info = raw_info
    except Exception:
        info = {}

    profile = {
        "symbol": symbol,
        "yf_symbol": yf_symbol,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price": _safe_float(snapshot_row.get("price"), close.iloc[-1] if len(close) else np.nan),
        "pe": _safe_float(info.get("trailingPE"), _safe_float(snapshot_row.get("pe_ttm"), np.nan)),
        "pb": _safe_float(info.get("priceToBook"), _safe_float(snapshot_row.get("pb"), np.nan)),
        "roe": _safe_float(info.get("returnOnEquity"), np.nan),
        "gross_margin": _safe_float(info.get("grossMargins"), np.nan),
        "operating_margin": _safe_float(info.get("operatingMargins"), np.nan),
        "dividend_yield": _safe_float(info.get("dividendYield"), np.nan),
        "debt_to_equity": _safe_float(info.get("debtToEquity"), np.nan),
        "free_cashflow": _safe_float(info.get("freeCashflow"), np.nan),
        "market_cap": _safe_float(info.get("marketCap"), _safe_float(snapshot_row.get("total_market_cap"), np.nan)),
        "ret_1y": _safe_float(ret_1y, np.nan),
        "realized_vol": _safe_float(realized_vol, np.nan),
        "max_drawdown": _safe_float(max_drawdown, np.nan),
        "news": _extract_news(ticker, limit=max(int(news_limit), 0)),
        "snapshot": snapshot_row,
    }
    return profile


def _news_sentiment_score(news_items: list[dict[str, str]]) -> int:
    pos_kw = ("增长", "提价", "回购", "分红", "创新高", "超预期")
    neg_kw = ("下滑", "减持", "诉讼", "处罚", "下调", "风险")
    score = 0
    for item in news_items:
        title = str(item.get("title", ""))
        if any(k in title for k in pos_kw):
            score += 1
        if any(k in title for k in neg_kw):
            score -= 1
    return score


def build_value_thesis(profile: dict[str, Any]) -> dict[str, Any]:
    pe = _safe_float(profile.get("pe"), np.nan)
    pb = _safe_float(profile.get("pb"), np.nan)
    roe = _safe_float(profile.get("roe"), np.nan)
    gm = _safe_float(profile.get("gross_margin"), np.nan)
    dividend_yield = _safe_float(profile.get("dividend_yield"), np.nan)
    dte = _safe_float(profile.get("debt_to_equity"), np.nan)
    fcf = _safe_float(profile.get("free_cashflow"), np.nan)
    ret_1y = _safe_float(profile.get("ret_1y"), np.nan)
    vol = _safe_float(profile.get("realized_vol"), np.nan)
    mdd = _safe_float(profile.get("max_drawdown"), np.nan)

    valuation = 50.0
    quality = 50.0
    shareholder = 50.0
    risk = 50.0
    reasons: list[str] = []
    risks: list[str] = []

    if not np.isnan(pe):
        if 0 < pe <= 18:
            valuation += 22
            reasons.append("PE处于价值区间（<=18）")
        elif pe <= 25:
            valuation += 12
            reasons.append("PE处于相对合理区间（<=25）")
        elif pe > 35:
            valuation -= 20
            risks.append("PE偏高，安全边际不足")
    else:
        risks.append("PE数据缺失，估值判断不充分")

    if not np.isnan(pb):
        if pb <= 3.0:
            valuation += 15
            reasons.append("PB较低（<=3）")
        elif pb > 8.0:
            valuation -= 12
            risks.append("PB偏高，估值弹性受限")

    if not np.isnan(roe):
        if roe >= 0.18:
            quality += 20
            reasons.append("ROE较高（>=18%）")
        elif roe < 0.10:
            quality -= 12
            risks.append("ROE偏低，盈利效率待观察")
    else:
        risks.append("ROE数据缺失")

    if not np.isnan(gm):
        if gm >= 0.45:
            quality += 10
            reasons.append("毛利率较高，护城河较强")
        elif gm < 0.20:
            quality -= 10
            risks.append("毛利率偏低，竞争压力较大")

    if not np.isnan(dte):
        if dte <= 80:
            quality += 8
        elif dte > 180:
            quality -= 12
            risks.append("杠杆较高，财务弹性受限")

    if not np.isnan(fcf):
        if fcf > 0:
            quality += 8
            reasons.append("自由现金流为正")
        else:
            quality -= 10
            risks.append("自由现金流为负，现金创造能力需复核")

    if not np.isnan(dividend_yield):
        if dividend_yield >= 0.02:
            shareholder += 18
            reasons.append("股息率具备吸引力（>=2%）")
        elif dividend_yield <= 0.005:
            shareholder -= 8
    else:
        risks.append("股息率数据缺失")

    if not np.isnan(vol):
        if vol <= 0.30:
            risk += 8
        elif vol > 0.50:
            risk -= 10
            risks.append("波动率较高，回撤压力更大")

    if not np.isnan(mdd):
        if mdd <= -0.40:
            risk -= 12
            risks.append("历史最大回撤较深")
        elif mdd >= -0.15:
            risk += 6

    news_score = _news_sentiment_score(profile.get("news") or [])
    risk += float(news_score) * 2.0
    if news_score < 0:
        risks.append("近期新闻偏负面，需关注舆情与基本面变化")
    elif news_score > 0:
        reasons.append("近期新闻情绪偏正面")

    valuation = float(np.clip(valuation, 0, 100))
    quality = float(np.clip(quality, 0, 100))
    shareholder = float(np.clip(shareholder, 0, 100))
    risk = float(np.clip(risk, 0, 100))
    score_total = float(np.clip(valuation * 0.35 + quality * 0.40 + shareholder * 0.15 + risk * 0.10, 0, 100))

    if score_total >= 75:
        conclusion = "高质量且估值可接受，符合价值投资跟踪标准。"
    elif score_total >= 60:
        conclusion = "质量较好，但安全边际一般，建议分批和跟踪。"
    elif score_total >= 45:
        conclusion = "估值与质量匹配一般，等待更优价格或业绩确认。"
    else:
        conclusion = "当前不符合价值投资偏好，建议谨慎观察。"

    bull = int(np.clip(28 + (score_total - 50) * 0.35 + news_score * 2, 15, 55))
    base = int(np.clip(50 - abs(score_total - 60) * 0.15, 30, 65))
    bear = max(100 - bull - base, 10)
    if bull + base + bear != 100:
        bear = 100 - bull - base

    watch_points = [
        "后续财报中的ROE与自由现金流是否持续改善",
        "估值是否回到更有安全边际的区间（PE/PB）",
        "行业景气与公司定价权是否保持稳定",
    ]
    if not np.isnan(ret_1y):
        watch_points.append(f"近1年收益为{ret_1y * 100:.2f}%，关注是否出现均值回归")

    return {
        "score_total": score_total,
        "sub_scores": {
            "valuation": valuation,
            "quality": quality,
            "shareholder": shareholder,
            "risk": risk,
        },
        "conclusion": conclusion,
        "reasons": reasons[:6] or ["当前可用数据不足，建议补充财务数据后再评估。"],
        "risks": risks[:6] or ["短期波动与宏观变化仍可能影响估值。"],
        "watch_points": watch_points[:4],
        "forecast": {
            "bull_pct": bull,
            "base_pct": base,
            "bear_pct": bear,
            "bull_case": "盈利稳定增长且估值提升，价格中枢上移。",
            "base_case": "盈利温和增长，估值中枢维持震荡。",
            "bear_case": "需求或政策扰动导致盈利承压，估值回落。",
        },
    }


def format_value_stock_report(symbol: str, profile: dict[str, Any], thesis: dict[str, Any]) -> str:
    score = _safe_float(thesis.get("score_total"), 0.0)
    sub_scores = thesis.get("sub_scores") or {}
    lines = [
        f"{symbol} 价值投资报告 ({profile.get('as_of', 'N/A')})",
        f"价值总分: {score:.1f}/100",
        (
            "子评分: "
            + f"估值={_safe_float(sub_scores.get('valuation'), 0.0):.1f}, "
            + f"质量={_safe_float(sub_scores.get('quality'), 0.0):.1f}, "
            + f"股东回报={_safe_float(sub_scores.get('shareholder'), 0.0):.1f}, "
            + f"风险={_safe_float(sub_scores.get('risk'), 0.0):.1f}"
        ),
        "",
        "核心指标:",
        f"- 现价: {_fmt_num(_safe_float(profile.get('price'), np.nan), 2)}",
        f"- PE/PB: {_fmt_num(_safe_float(profile.get('pe'), np.nan), 2)} / {_fmt_num(_safe_float(profile.get('pb'), np.nan), 2)}",
        f"- ROE: {_fmt_pct(_safe_float(profile.get('roe'), np.nan))}",
        f"- 毛利率: {_fmt_pct(_safe_float(profile.get('gross_margin'), np.nan))}",
        f"- 股息率: {_fmt_pct(_safe_float(profile.get('dividend_yield'), np.nan))}",
        f"- 资产负债指标(债务权益比): {_fmt_num(_safe_float(profile.get('debt_to_equity'), np.nan), 2)}",
        f"- 近1年收益/波动/最大回撤: {_fmt_pct(_safe_float(profile.get('ret_1y'), np.nan))} / {_fmt_pct(_safe_float(profile.get('realized_vol'), np.nan))} / {_fmt_pct(_safe_float(profile.get('max_drawdown'), np.nan))}",
        "",
        "投资结论:",
        f"- {thesis.get('conclusion', '')}",
        "",
        "价值理由:",
    ]
    for item in thesis.get("reasons") or []:
        lines.append(f"- {item}")
    lines.extend(["", "主要风险:"])
    for item in thesis.get("risks") or []:
        lines.append(f"- {item}")
    lines.extend(["", "待观察点:"])
    for item in thesis.get("watch_points") or []:
        lines.append(f"- {item}")

    forecast = thesis.get("forecast") or {}
    lines.extend(
        [
            "",
            "12个月预判（概率化）:",
            f"- 乐观: {int(_safe_float(forecast.get('bull_pct'), 0))}% | {forecast.get('bull_case', '')}",
            f"- 基准: {int(_safe_float(forecast.get('base_pct'), 0))}% | {forecast.get('base_case', '')}",
            f"- 谨慎: {int(_safe_float(forecast.get('bear_pct'), 0))}% | {forecast.get('bear_case', '')}",
        ]
    )

    news_items = profile.get("news") or []
    lines.extend(["", "网络信息摘要(近期新闻):"])
    if news_items:
        for item in news_items:
            lines.append(
                f"- [{item.get('date', 'N/A')}] {item.get('publisher', '').strip()} | {item.get('title', '')}"
            )
    else:
        lines.append("- 未获取到可用新闻条目（可能受网络或数据源限制）")

    lines.extend(["", "风险声明：仅供研究，不构成投资建议。"])
    return "\n".join(lines)


def analyze_value_stock(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    news_limit: int = 5,
) -> str:
    normalized = normalize_symbol(symbol)
    try:
        profile = fetch_value_profile(
            symbol=normalized,
            start=start,
            end=end,
            news_limit=news_limit,
            snapshot_file=CONFIG.ashare_latest_file,
        )
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:
        return format_error(ErrorCode.DATA_FETCH, f"价值分析失败: {type(exc).__name__}: {exc}")
    thesis = build_value_thesis(profile)
    return format_value_stock_report(symbol=normalized, profile=profile, thesis=thesis)
