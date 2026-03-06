import argparse
import base64
import html
import json
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.config import CONFIG


def _latest_file(directory: Path, pattern: str) -> Optional[Path]:
    if not directory.exists():
        return None
    files = [path for path in directory.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _load_json(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _load_candidate_df(path: Optional[Path]) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    # Remove BOM and whitespace from source headers.
    df.columns = [str(col).replace("\ufeff", "").strip() for col in df.columns]
    return df


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    return f"{_safe_float(value) * 100:.2f}%"


def _read_chart_data_uri(chart_path: str) -> str:
    if not chart_path:
        return ""
    path = Path(chart_path).expanduser()
    if not path.is_file():
        return ""
    try:
        with open(path, "rb") as f:
            content = f.read()
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


def _fallback_structured_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    signals = analysis.get("signals") or {}
    trend = str(signals.get("trend", "")).strip()
    macd = str(signals.get("macd_signal", "")).strip()
    rsi = str(signals.get("rsi_signal", "")).strip()
    boll = str(signals.get("boll_signal", "")).strip()
    summary = str(signals.get("summary", "")).strip()
    evidence = [item for item in [f"趋势: {trend}" if trend else "", f"MACD: {macd}" if macd else "", f"RSI: {rsi}" if rsi else "", f"布林: {boll}" if boll else ""] if item]
    return {
        "conclusion": summary or "暂无结构化结论",
        "evidence": evidence or ["暂无"],
        "risks": ["当前为规则引擎结果，未启用LLM结构化风险解读。"],
        "watch_points": ["建议关注成交量变化、均线关系与MACD/RSI方向变化。"],
        "safety_note": "仅供研究，不构成投资建议。",
    }


def _fig_schema_stability(analysis: dict[str, Any]) -> go.Figure:
    llm = analysis.get("llm") or {}
    schema = llm.get("schema_quality") or {}
    stability = llm.get("stability") or {}
    schema_score = _safe_float(schema.get("completeness_pct"), 0.0)
    stability_score = _safe_float(stability.get("stability_score"), 0.0) * 100

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=["Schema齐全率", "稳定性分数"],
            y=[schema_score, stability_score],
            marker_color=["#2ab07f", "#3b82f6"],
            text=[f"{schema_score:.1f}%", f"{stability_score:.1f}%"],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="LLM质量视图",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=280,
        yaxis=dict(range=[0, 100], title="百分比"),
    )
    return fig


def _fig_candidate_top(df: pd.DataFrame) -> go.Figure:
    top_df = df.copy()
    if "score_total" not in top_df.columns:
        top_df["score_total"] = 0.0
    top_df["score_total"] = pd.to_numeric(top_df["score_total"], errors="coerce").fillna(0.0)
    top_df["name"] = top_df.get("name", top_df.get("symbol", "N/A")).astype(str)
    top_df = top_df.sort_values(by="score_total", ascending=False).head(15).sort_values(by="score_total")

    fig = px.bar(
        top_df,
        x="score_total",
        y="name",
        orientation="h",
        color="score_total",
        color_continuous_scale="Tealgrn",
    )
    fig.update_layout(
        title="候选池 Top15 总分",
        template="plotly_white",
        margin=dict(l=24, r=20, t=48, b=20),
        height=420,
        coloraxis_showscale=False,
    )
    fig.update_traces(hovertemplate="%{y}<br>score_total=%{x:.2f}<extra></extra>")
    fig.update_xaxes(title="score_total")
    fig.update_yaxes(title="")
    return fig


def _fig_candidate_scatter(df: pd.DataFrame) -> go.Figure:
    scatter_df = df.copy()
    for col in ["pct_change", "score_total", "amount", "volume"]:
        if col in scatter_df.columns:
            scatter_df[col] = pd.to_numeric(scatter_df[col], errors="coerce")
        else:
            scatter_df[col] = 0.0
    scatter_df["name"] = scatter_df.get("name", scatter_df.get("symbol", "N/A")).astype(str)
    scatter_df = scatter_df.head(300)

    fig = px.scatter(
        scatter_df,
        x="pct_change",
        y="score_total",
        size="amount",
        color="volume",
        hover_name="name",
        color_continuous_scale="Turbo",
        size_max=26,
    )
    fig.update_layout(
        title="量价-评分散点图",
        template="plotly_white",
        margin=dict(l=24, r=20, t=48, b=20),
        height=420,
    )
    fig.update_xaxes(title="涨跌幅(%)")
    fig.update_yaxes(title="score_total")
    return fig


def _fig_backtest_returns(backtest: dict[str, Any]) -> go.Figure:
    metrics = backtest.get("metrics") or {}
    values = [
        _safe_float(metrics.get("total_return")) * 100,
        _safe_float(metrics.get("annual_return")) * 100,
        _safe_float(metrics.get("benchmark_return")) * 100,
        _safe_float(metrics.get("max_drawdown")) * 100,
    ]
    labels = ["策略总收益", "年化收益", "基准收益", "最大回撤"]
    colors = ["#0f766e", "#14b8a6", "#60a5fa", "#f97316"]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                text=[f"{item:.2f}%" for item in values],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="组合绩效核心指标",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=320,
        yaxis_title="百分比",
    )
    return fig


def _fig_backtest_history(backtest_dir: Path) -> Optional[go.Figure]:
    rows: list[dict[str, Any]] = []
    for path in sorted(backtest_dir.glob("bt_portfolio_*.json")):
        payload = _load_json(path)
        if not payload:
            continue
        metrics = payload.get("metrics") or {}
        rows.append(
            {
                "generated_at": payload.get("generated_at", ""),
                "annual_return": _safe_float(metrics.get("annual_return")) * 100,
                "max_drawdown": _safe_float(metrics.get("max_drawdown")) * 100,
                "total_return": _safe_float(metrics.get("total_return")) * 100,
            }
        )
    if len(rows) < 2:
        return None
    hist = pd.DataFrame(rows)
    hist["generated_at"] = pd.to_datetime(hist["generated_at"], errors="coerce")
    hist = hist.dropna(subset=["generated_at"]).sort_values("generated_at")
    if hist.empty:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist["generated_at"],
            y=hist["annual_return"],
            mode="lines+markers",
            name="年化收益",
            line=dict(color="#0ea5e9", width=2.5),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=hist["generated_at"],
            y=hist["max_drawdown"],
            mode="lines+markers",
            name="最大回撤",
            line=dict(color="#f97316", width=2.5),
        )
    )
    fig.update_layout(
        title="历史回测走势",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=320,
        yaxis_title="百分比",
    )
    return fig


def _load_backtest_history(backtest_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not backtest_dir.exists():
        return rows
    for path in sorted(backtest_dir.glob("bt_portfolio_*.json")):
        payload = _load_json(path)
        if not payload:
            continue
        ts = pd.to_datetime(payload.get("generated_at", ""), errors="coerce")
        if pd.isna(ts):
            continue
        rows.append(
            {
                "generated_at": ts,
                "path": str(path),
                "params": payload.get("params") or {},
                "metrics": payload.get("metrics") or {},
            }
        )
    rows.sort(key=lambda item: item["generated_at"])
    return rows


def _build_backtest_param_compare_lines(history: list[dict[str, Any]]) -> list[str]:
    if len(history) < 2:
        return ["暂无历史基线（至少需要两次组合回测记录）。"]

    prev = history[-2]
    curr = history[-1]
    prev_params = prev.get("params") or {}
    curr_params = curr.get("params") or {}
    prev_metrics = prev.get("metrics") or {}
    curr_metrics = curr.get("metrics") or {}

    lines: list[str] = []

    def _fmt_pct(v: Any) -> str:
        return f"{_safe_float(v) * 100:.2f}%"

    param_keys = [
        "fee_rate",
        "slippage_bps",
        "min_hold_days",
        "signal_confirm_days",
        "max_positions",
        "max_single_weight",
        "max_industry_weight",
        "target_volatility",
        "rebalance_frequency",
        "rebalance_weekday",
    ]
    param_changes: list[str] = []
    for key in param_keys:
        old = prev_params.get(key)
        new = curr_params.get(key)
        if old == new:
            continue
        if key in {"fee_rate", "max_single_weight", "max_industry_weight", "target_volatility"}:
            param_changes.append(f"{key}: {_fmt_pct(old)} -> {_fmt_pct(new)}")
        elif key == "slippage_bps":
            param_changes.append(f"{key}: {_safe_float(old):.1f} -> {_safe_float(new):.1f} bps")
        else:
            param_changes.append(f"{key}: {old} -> {new}")
    if param_changes:
        lines.append("参数变化: " + "；".join(param_changes[:4]))
    else:
        lines.append("参数变化: 与上次记录一致。")

    metric_items = [
        ("annual_return", "年化收益", True),
        ("total_return", "总收益", True),
        ("max_drawdown", "最大回撤", True),
        ("sharpe", "夏普", False),
        ("calmar", "卡玛", False),
    ]
    metric_changes: list[str] = []
    for key, label, pct in metric_items:
        old = _safe_float(prev_metrics.get(key), 0.0)
        new = _safe_float(curr_metrics.get(key), 0.0)
        if abs(new - old) < 1e-12:
            continue
        delta = new - old
        if pct:
            metric_changes.append(f"{label} {delta * 100:+.2f}pp")
        else:
            metric_changes.append(f"{label} {delta:+.2f}")
    if metric_changes:
        lines.append("指标变化: " + "；".join(metric_changes[:5]))
    else:
        lines.append("指标变化: 核心指标无变化。")

    lines.append(
        "基线时间: "
        + f"{prev['generated_at'].strftime('%Y-%m-%d %H:%M:%S')} -> {curr['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return lines


def _fig_backtest_strategy_benchmark(history: list[dict[str, Any]]) -> Optional[go.Figure]:
    if len(history) < 2:
        return None
    rows = []
    for item in history:
        metrics = item.get("metrics") or {}
        rows.append(
            {
                "generated_at": item["generated_at"],
                "strategy_total_return": _safe_float(metrics.get("total_return")) * 100,
                "benchmark_return": _safe_float(metrics.get("benchmark_return")) * 100,
            }
        )
    hist = pd.DataFrame(rows).sort_values("generated_at")
    if hist.empty:
        return None
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist["generated_at"],
            y=hist["strategy_total_return"],
            mode="lines+markers",
            name="策略总收益",
            line=dict(color="#0f766e", width=2.5),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=hist["generated_at"],
            y=hist["benchmark_return"],
            mode="lines+markers",
            name="基准收益",
            line=dict(color="#2563eb", width=2.5),
        )
    )
    fig.update_layout(
        title="策略/基准收益对比（历史）",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=320,
        yaxis_title="百分比",
    )
    return fig


def _fig_risk_score(risk: dict[str, Any]) -> go.Figure:
    score = _safe_float(risk.get("risk_score"), 0.0)
    level = str(risk.get("risk_level", "unknown")).lower()
    color = "#16a34a" if level == "low" else "#f59e0b" if level == "medium" else "#dc2626"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 60], "color": "#fee2e2"},
                    {"range": [60, 80], "color": "#fef3c7"},
                    {"range": [80, 100], "color": "#dcfce7"},
                ],
            },
            title={"text": "风险评分"},
        )
    )
    fig.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=48, b=20), height=280)
    return fig


def _fig_risk_exposure(risk: dict[str, Any]) -> go.Figure:
    exposure = risk.get("exposure") or {}
    values = [
        _safe_float(exposure.get("max_single_weight_used")) * 100,
        _safe_float(exposure.get("max_industry_weight_used")) * 100,
        _safe_float(exposure.get("implied_single_weight")) * 100,
    ]
    labels = ["单票峰值权重", "行业峰值权重", "隐含单票权重"]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=["#0ea5e9", "#f97316", "#14b8a6"],
                text=[f"{item:.2f}%" for item in values],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="风险暴露快照",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=300,
        yaxis_title="百分比",
    )
    return fig


def _fig_risk_history(risk_dir: Path) -> Optional[go.Figure]:
    rows: list[dict[str, Any]] = []
    if not risk_dir.exists():
        return None
    # Support both pipeline exports (risk_portfolio_*.json) and ad-hoc/report tests (risk_*.json).
    risk_files: set[Path] = set()
    for pattern in ("risk_portfolio_*.json", "risk_*.json", "*.json"):
        risk_files.update(path for path in risk_dir.glob(pattern) if path.is_file())

    for path in sorted(risk_files):
        payload = _load_json(path)
        if not payload:
            continue
        if not any(key in payload for key in ("risk_score", "risk_level", "alerts", "exposure")):
            continue
        ts = pd.to_datetime(payload.get("generated_at", ""), errors="coerce")
        if pd.isna(ts):
            continue
        alerts = payload.get("alerts") or []
        rows.append(
            {
                "generated_at": ts,
                "risk_score": _safe_float(payload.get("risk_score"), 0.0),
                "alert_count": float(len(alerts)),
            }
        )
    if len(rows) < 2:
        return None
    hist = pd.DataFrame(rows).sort_values("generated_at")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist["generated_at"],
            y=hist["risk_score"],
            mode="lines+markers",
            name="风险评分",
            line=dict(color="#16a34a", width=2.5),
        )
    )
    fig.add_trace(
        go.Bar(
            x=hist["generated_at"],
            y=hist["alert_count"],
            name="告警数",
            marker_color="#f97316",
            opacity=0.45,
            yaxis="y2",
        )
    )
    fig.update_layout(
        title="风险时序（评分/告警）",
        template="plotly_white",
        margin=dict(l=20, r=20, t=48, b=20),
        height=320,
        yaxis=dict(title="风险评分", range=[0, 100]),
        yaxis2=dict(title="告警数", overlaying="y", side="right", rangemode="tozero"),
        barmode="overlay",
    )
    return fig


def _render_figures(figures: list[go.Figure]) -> list[str]:
    snippets: list[str] = []
    include_js = True
    for fig in figures:
        snippet = fig.to_html(
            full_html=False,
            include_plotlyjs="inline" if include_js else False,
            config={"responsive": True, "displayModeBar": False},
        )
        snippets.append(snippet)
        include_js = False
    return snippets


def _card(title: str, value: str, caption: str = "") -> str:
    caption_html = f"<div class='card-caption'>{html.escape(caption)}</div>" if caption else ""
    return (
        "<div class='metric-card'>"
        f"<div class='card-title'>{html.escape(title)}</div>"
        f"<div class='card-value'>{html.escape(value)}</div>"
        f"{caption_html}"
        "</div>"
    )


def build_dashboard_html(data_dir: Path) -> str:
    analysis_path = _latest_file(data_dir / "analysis_reports", "*.json")
    backtest_path = _latest_file(data_dir / "backtests", "bt_portfolio_*.json")
    risk_path = _latest_file(data_dir / "risk_reports", "*.json")
    candidate_path = _latest_file(data_dir / "candidate_pools", "*.csv")

    analysis = _load_json(analysis_path) or {}
    backtest = _load_json(backtest_path) or {}
    risk = _load_json(risk_path) or {}
    candidate_df = _load_candidate_df(candidate_path)
    backtest_history = _load_backtest_history(data_dir / "backtests")

    llm = analysis.get("llm") or {}
    llm_structured = llm.get("structured") or {}
    llm_schema = llm.get("schema_quality") or {}
    llm_stability = llm.get("stability") or {}
    llm_available = bool(llm_structured) or bool(str(llm.get("text", "")).strip())
    if not llm_structured:
        llm_structured = _fallback_structured_from_analysis(analysis)
    backtest_metrics = backtest.get("metrics") or {}
    alerts = risk.get("alerts") or []
    chart_uri = _read_chart_data_uri(str(analysis.get("chart_path", "")))
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    backtest_compare_lines = _build_backtest_param_compare_lines(backtest_history)

    figures: list[go.Figure] = []
    plot_slots: dict[str, str] = {}

    analysis_fig = _fig_schema_stability(analysis) if analysis and llm_available else None
    if analysis_fig:
        figures.append(analysis_fig)
        plot_slots["analysis_quality"] = "__PLOT_0__"

    if not candidate_df.empty:
        candidate_top = _fig_candidate_top(candidate_df)
        candidate_scatter = _fig_candidate_scatter(candidate_df)
        base = len(figures)
        figures.extend([candidate_top, candidate_scatter])
        plot_slots["candidate_top"] = f"__PLOT_{base}__"
        plot_slots["candidate_scatter"] = f"__PLOT_{base + 1}__"

    backtest_fig = _fig_backtest_returns(backtest) if backtest else None
    if backtest_fig:
        base = len(figures)
        figures.append(backtest_fig)
        plot_slots["backtest_core"] = f"__PLOT_{base}__"
    history_fig = _fig_backtest_history(data_dir / "backtests")
    if history_fig:
        base = len(figures)
        figures.append(history_fig)
        plot_slots["backtest_history"] = f"__PLOT_{base}__"
    backtest_compare_fig = _fig_backtest_strategy_benchmark(backtest_history)
    if backtest_compare_fig:
        base = len(figures)
        figures.append(backtest_compare_fig)
        plot_slots["backtest_compare"] = f"__PLOT_{base}__"

    risk_score_fig = _fig_risk_score(risk) if risk else None
    if risk_score_fig:
        base = len(figures)
        figures.append(risk_score_fig)
        plot_slots["risk_score"] = f"__PLOT_{base}__"
    risk_exposure_fig = _fig_risk_exposure(risk) if risk else None
    if risk_exposure_fig:
        base = len(figures)
        figures.append(risk_exposure_fig)
        plot_slots["risk_exposure"] = f"__PLOT_{base}__"
    risk_history_fig = _fig_risk_history(data_dir / "risk_reports")
    if risk_history_fig:
        base = len(figures)
        figures.append(risk_history_fig)
        plot_slots["risk_history"] = f"__PLOT_{base}__"

    figure_snippets = _render_figures(figures)

    head_cards = [
        _card("最新分析标的", str(analysis.get("symbol", "N/A"))),
        _card("Schema齐全率", (f"{_safe_float(llm_schema.get('completeness_pct')):.1f}%" if llm_available else "N/A"), "目标 >= 95%"),
        _card("稳定性得分", (f"{_safe_float(llm_stability.get('stability_score')) * 100:.1f}%" if llm_available else "N/A"), "低温度评估"),
        _card("风险等级", str(risk.get("risk_level", "N/A")).upper(), f"score={int(_safe_float(risk.get('risk_score'), 0))}"),
    ]

    evidence_items = llm_structured.get("evidence") or []
    risk_items = llm_structured.get("risks") or []
    watch_items = llm_structured.get("watch_points") or []
    conclusion = llm_structured.get("conclusion", "暂无结构化结论")

    alerts_html = ""
    if alerts:
        alert_rows = []
        for item in alerts:
            sev = html.escape(str(item.get("severity", "unknown")))
            msg = html.escape(str(item.get("message", "")))
            alert_rows.append(f"<li><span class='tag tag-{sev}'>{sev}</span>{msg}</li>")
        alerts_html = "<ul class='alert-list'>" + "".join(alert_rows) + "</ul>"
    else:
        alerts_html = "<div class='empty'>暂无风险告警。</div>"

    chart_html = (
        f"<img class='analysis-chart' src='{chart_uri}' alt='analysis chart' />"
        if chart_uri
        else "<div class='empty'>暂无技术图表。</div>"
    )

    candidate_meta = (
        f"文件: {html.escape(str(candidate_path))} ｜ 样本: {len(candidate_df)}"
        if candidate_path and not candidate_df.empty
        else "暂无候选池数据。"
    )
    backtest_meta = f"文件: {html.escape(str(backtest_path))}" if backtest_path else "暂无回测结果。"
    risk_meta = f"文件: {html.escape(str(risk_path))}" if risk_path else "暂无风险报告。"

    html_page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpenClaw Quant Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');
    :root {{
      --bg-a: #f4faf8;
      --bg-b: #f8fbff;
      --ink: #0f172a;
      --muted: #475569;
      --panel: rgba(255, 255, 255, 0.86);
      --line: rgba(15, 23, 42, 0.1);
      --teal: #0f766e;
      --cyan: #0891b2;
      --orange: #ea580c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at 8% 8%, rgba(20, 184, 166, 0.22) 0%, rgba(20, 184, 166, 0) 38%),
        radial-gradient(circle at 95% 10%, rgba(14, 165, 233, 0.18) 0%, rgba(14, 165, 233, 0) 44%),
        linear-gradient(140deg, var(--bg-a), var(--bg-b));
      min-height: 100vh;
    }}
    .wrap {{ width: min(1280px, 94vw); margin: 0 auto; padding: 22px 0 40px; }}
    .hero {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      padding: 20px 20px 10px;
    }}
    .title {{
      margin: 0;
      font-size: clamp(26px, 4vw, 40px);
      line-height: 1.1;
      letter-spacing: 0.2px;
    }}
    .subtitle {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .meta {{
      font-size: 12px;
      color: #334155;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.72);
      white-space: nowrap;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      padding: 10px 20px 8px;
    }}
    .metric-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      backdrop-filter: blur(2px);
      box-shadow: 0 4px 18px rgba(15, 23, 42, 0.04);
    }}
    .card-title {{ color: #334155; font-size: 12px; }}
    .card-value {{
      margin-top: 6px;
      font-size: clamp(20px, 3.2vw, 30px);
      font-weight: 700;
      color: #0b3d3a;
    }}
    .card-caption {{ margin-top: 4px; color: #64748b; font-size: 12px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 8px 20px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      opacity: 0;
      transform: translateY(14px);
      animation: rise 0.72s ease forwards;
    }}
    .panel:nth-of-type(1) {{ animation-delay: 0.05s; }}
    .panel:nth-of-type(2) {{ animation-delay: 0.12s; }}
    .panel:nth-of-type(3) {{ animation-delay: 0.19s; }}
    .panel:nth-of-type(4) {{ animation-delay: 0.26s; }}
    @keyframes rise {{
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    .panel h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: 0.2px;
    }}
    .panel-meta {{
      margin-top: 6px;
      margin-bottom: 8px;
      color: #64748b;
      font-size: 12px;
      word-break: break-all;
    }}
    .split {{
      display: grid;
      grid-template-columns: 1.15fr 1fr;
      gap: 10px;
    }}
    .text-block {{
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      margin-bottom: 10px;
    }}
    .text-block h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--teal);
    }}
    .text-block p {{
      margin: 0;
      font-size: 14px;
      line-height: 1.6;
      color: #1f2937;
    }}
    ul.bullets {{
      margin: 0;
      padding-left: 18px;
      color: #1f2937;
      line-height: 1.55;
      font-size: 13px;
    }}
    ul.bullets li {{ margin: 4px 0; }}
    .chart-wrap {{
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
      background: rgba(255,255,255,0.8);
    }}
    .analysis-chart {{
      display: block;
      width: 100%;
      height: auto;
      max-height: 320px;
      object-fit: contain;
      background: #fff;
    }}
    .empty {{
      border: 1px dashed #94a3b8;
      border-radius: 10px;
      padding: 12px;
      font-size: 13px;
      color: #475569;
      background: rgba(255, 255, 255, 0.7);
    }}
    .alert-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 8px;
    }}
    .alert-list li {{
      display: flex;
      gap: 8px;
      align-items: flex-start;
      padding: 10px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.75);
      border: 1px solid var(--line);
      font-size: 13px;
      line-height: 1.5;
    }}
    .tag {{
      display: inline-block;
      min-width: 56px;
      text-align: center;
      border-radius: 999px;
      padding: 1px 8px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .tag-high {{ background: #fee2e2; color: #991b1b; }}
    .tag-medium {{ background: #fef3c7; color: #92400e; }}
    .tag-low {{ background: #dcfce7; color: #166534; }}
    .footer {{
      margin: 16px 20px 0;
      color: #64748b;
      font-size: 12px;
      line-height: 1.5;
    }}
    @media (max-width: 1100px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 720px) {{
      .hero {{ flex-direction: column; align-items: flex-start; }}
      .cards {{ grid-template-columns: 1fr; padding: 8px 14px; }}
      .grid {{ padding: 8px 14px; }}
      .split {{ grid-template-columns: 1fr; }}
      .wrap {{ width: min(1280px, 100vw); }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div>
        <h1 class="title">A-Share AI Portfolio Dashboard</h1>
        <div class="subtitle">单股分析 · 候选池 · 组合回测 · 风险日报</div>
      </div>
      <div class="meta">渲染时间：{html.escape(now_text)}</div>
    </section>

    <section class="cards">
      {"".join(head_cards)}
    </section>

    <section class="grid">
      <article class="panel">
        <h2>单股分析</h2>
        <div class="panel-meta">文件: {html.escape(str(analysis_path)) if analysis_path else "暂无单股分析文件。"}</div>
        <div class="split">
          <div>
            <div class="text-block">
              <h3>当前结论</h3>
              <p>{html.escape(str(conclusion))}</p>
            </div>
            <div class="text-block">
              <h3>关键证据</h3>
              <ul class="bullets">
                {"".join(f"<li>{html.escape(str(item))}</li>" for item in evidence_items[:4]) or "<li>暂无</li>"}
              </ul>
            </div>
            <div class="text-block">
              <h3>主要风险</h3>
              <ul class="bullets">
                {"".join(f"<li>{html.escape(str(item))}</li>" for item in risk_items[:4]) or "<li>暂无</li>"}
              </ul>
            </div>
            <div class="text-block">
              <h3>待观察点</h3>
              <ul class="bullets">
                {"".join(f"<li>{html.escape(str(item))}</li>" for item in watch_items[:4]) or "<li>暂无</li>"}
              </ul>
            </div>
          </div>
          <div>
            <div class="chart-wrap">{chart_html}</div>
            <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("analysis_quality", "<div class='empty'>暂无质量指标。</div>")}</div>
          </div>
        </div>
      </article>

      <article class="panel">
        <h2>候选池评分</h2>
        <div class="panel-meta">{candidate_meta}</div>
        <div class="chart-wrap">{plot_slots.get("candidate_top", "<div class='empty'>暂无候选池评分图。</div>")}</div>
        <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("candidate_scatter", "<div class='empty'>暂无候选池散点图。</div>")}</div>
      </article>

      <article class="panel">
        <h2>组合回测</h2>
        <div class="panel-meta">{backtest_meta}</div>
        <div class="text-block">
          <h3>核心指标</h3>
          <p>
            总收益 {_pct(backtest_metrics.get("total_return"))} ｜ 年化 {_pct(backtest_metrics.get("annual_return"))}
            ｜ 回撤 {_pct(backtest_metrics.get("max_drawdown"))} ｜ 夏普 {_safe_float(backtest_metrics.get("sharpe")):.2f}
            ｜ 卡玛 {_safe_float(backtest_metrics.get("calmar")):.2f}
          </p>
        </div>
        <div class="text-block">
          <h3>参数对比（最新 vs 上次）</h3>
          <ul class="bullets">
            {"".join(f"<li>{html.escape(str(item))}</li>" for item in backtest_compare_lines)}
          </ul>
        </div>
        <div class="chart-wrap">{plot_slots.get("backtest_core", "<div class='empty'>暂无回测图。</div>")}</div>
        <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("backtest_history", "<div class='empty'>历史样本不足，无法生成趋势图。</div>")}</div>
        <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("backtest_compare", "<div class='empty'>历史样本不足，无法生成策略/基准对比图。</div>")}</div>
      </article>

      <article class="panel">
        <h2>风险日报</h2>
        <div class="panel-meta">{risk_meta}</div>
        <div class="split">
          <div>
            <div class="chart-wrap">{plot_slots.get("risk_score", "<div class='empty'>暂无风险评分。</div>")}</div>
            <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("risk_exposure", "<div class='empty'>暂无风险暴露图。</div>")}</div>
            <div class="chart-wrap" style="margin-top:10px;">{plot_slots.get("risk_history", "<div class='empty'>历史样本不足，无法生成风险时序。</div>")}</div>
          </div>
          <div>
            <div class="text-block">
              <h3>风控摘要</h3>
              <p>
                风险等级 {html.escape(str(risk.get("risk_level", "N/A"))).upper()}，
                分数 {int(_safe_float(risk.get("risk_score"), 0))} / 100，
                单票峰值 {_pct((risk.get("exposure") or {}).get("max_single_weight_used"))}，
                行业峰值 {_pct((risk.get("exposure") or {}).get("max_industry_weight_used"))}。
              </p>
            </div>
            <div class="text-block">
              <h3>风险告警</h3>
              {alerts_html}
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="footer">
      数据来源：analysis_reports / candidate_pools / backtests / risk_reports（自动读取最新文件）<br/>
      风险声明：仅供研究，不构成投资建议。
    </section>
  </main>
</body>
</html>
"""

    for idx, snippet in enumerate(figure_snippets):
        html_page = html_page.replace(f"__PLOT_{idx}__", snippet)
    return html_page


def generate_dashboard(output_path: Path, data_dir: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = build_dashboard_html(data_dir)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return output_path


def serve_dashboard(output_path: Path, host: str, port: int) -> None:
    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(output_path.parent), **kwargs)

    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Dashboard running at http://{host}:{port}/{output_path.name}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Plotly dashboard from latest artifacts.")
    parser.add_argument(
        "--data-dir",
        default=CONFIG.data_dir,
        help="Data directory that contains analysis_reports/backtests/risk_reports/candidate_pools.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("dashboard") / "dist" / "index.html"),
        help="Output html path.",
    )
    parser.add_argument("--serve", action="store_true", help="Serve generated dashboard via local HTTP.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local server.")
    parser.add_argument("--port", type=int, default=8765, help="Port for local server.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser()
    output_path = Path(args.output).expanduser()
    generated = generate_dashboard(output_path=output_path, data_dir=data_dir)
    print(f"Dashboard generated: {generated}")
    if args.serve:
        serve_dashboard(output_path=generated, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
