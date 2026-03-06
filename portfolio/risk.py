import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _risk_level_from_score(score: int) -> str:
    if score <= 60:
        return "high"
    if score <= 80:
        return "medium"
    return "low"


def _stable_hash(value: Any, length: int = 12) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def evaluate_portfolio_risk(
    metrics: dict[str, Any],
    input_symbols: list[str],
    effective_symbols: list[str],
    failed_symbols: list[str],
    period_start: str,
    period_end: str,
    max_drawdown_limit: float = 0.15,
    max_single_weight: float = 0.35,
    max_industry_weight: float = 0.6,
    min_holdings: int = 3,
) -> dict[str, Any]:
    safe_limit = max(float(max_drawdown_limit), 0.0)
    safe_single_weight = min(max(float(max_single_weight), 0.0), 1.0)
    safe_industry_weight = min(max(float(max_industry_weight), 0.0), 1.0)
    safe_min_holdings = max(int(min_holdings), 1)

    max_positions = max(int(float(metrics.get("max_positions", 1))), 1)
    implied_single_weight = 1.0 / max_positions
    used_single_weight = float(metrics.get("max_single_weight_used", 0.0))
    if used_single_weight <= 0:
        used_single_weight = implied_single_weight
    used_industry_weight = float(metrics.get("max_industry_weight_used", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    sharpe = float(metrics.get("sharpe", 0.0))
    win_rate = float(metrics.get("win_rate", 0.0))
    circuit_triggers = int(float(metrics.get("drawdown_circuit_triggers", 0)))
    circuit_active_days = int(float(metrics.get("circuit_active_days", 0)))

    alerts: list[dict[str, str]] = []
    penalties = 0

    if max_drawdown <= -safe_limit:
        alerts.append(
            {
                "severity": "high",
                "code": "drawdown_limit",
                "message": f"最大回撤 {max_drawdown * 100:.2f}% 已触达阈值 {-safe_limit * 100:.2f}%。",
            }
        )
        penalties += 25

    if used_single_weight > safe_single_weight:
        alerts.append(
            {
                "severity": "medium",
                "code": "single_weight",
                "message": f"单票峰值权重 {used_single_weight * 100:.2f}% 高于阈值 {safe_single_weight * 100:.2f}%。",
            }
        )
        penalties += 15

    if used_industry_weight > safe_industry_weight:
        alerts.append(
            {
                "severity": "medium",
                "code": "industry_weight",
                "message": f"行业峰值权重 {used_industry_weight * 100:.2f}% 高于阈值 {safe_industry_weight * 100:.2f}%。",
            }
        )
        penalties += 12

    if len(effective_symbols) < safe_min_holdings:
        alerts.append(
            {
                "severity": "medium",
                "code": "diversification",
                "message": f"有效标的数 {len(effective_symbols)} 低于分散化阈值 {safe_min_holdings}。",
            }
        )
        penalties += 10

    if sharpe < 0.5:
        alerts.append(
            {
                "severity": "low",
                "code": "low_sharpe",
                "message": f"夏普比率 {sharpe:.2f} 偏低，风险收益比需复核。",
            }
        )
        penalties += 8

    if win_rate < 0.4:
        alerts.append(
            {
                "severity": "low",
                "code": "low_win_rate",
                "message": f"胜率 {win_rate * 100:.2f}% 偏低，建议复核信号参数。",
            }
        )
        penalties += 6

    score = max(0, 100 - penalties)
    risk_level = _risk_level_from_score(score)

    recommendations: list[str] = []
    if used_single_weight > safe_single_weight:
        recommendations.append("降低单票权重上限或提高 max_positions，减少集中暴露。")
    if used_industry_weight > safe_industry_weight:
        recommendations.append("收紧行业集中度参数，或补充行业分散后的候选池。")
    if max_drawdown <= -safe_limit:
        recommendations.append("启用或收紧回撤熔断阈值，必要时提高信号确认天数。")
    if circuit_triggers > 0:
        recommendations.append("当前已触发回撤熔断，建议复核仓位上限与回撤阈值配置。")
    if win_rate < 0.4 or sharpe < 0.5:
        recommendations.append("优先在参数网格中筛选夏普/卡玛更稳健的组合。")
    if len(effective_symbols) < safe_min_holdings:
        recommendations.append("扩充组合标的池，避免过度集中在少数个股。")
    if not recommendations:
        recommendations.append("风险结构处于可控区间，继续按周复核并监控回撤。")

    report = {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "period": {"start": period_start, "end": period_end},
        "input_symbols": input_symbols,
        "effective_symbols": effective_symbols,
        "failed_symbols": failed_symbols,
        "thresholds": {
            "max_drawdown_limit": safe_limit,
            "max_single_weight": safe_single_weight,
            "max_industry_weight": safe_industry_weight,
            "min_holdings": safe_min_holdings,
        },
        "exposure": {
            "symbol_count": len(effective_symbols),
            "avg_active_positions": float(metrics.get("avg_active_positions", 0.0)),
            "max_active_positions": float(metrics.get("max_active_positions", 0.0)),
            "implied_single_weight": implied_single_weight,
            "max_single_weight_used": used_single_weight,
            "max_industry_weight_used": used_industry_weight,
        },
        "performance_snapshot": {
            "annual_return": float(metrics.get("annual_return", 0.0)),
            "total_return": float(metrics.get("total_return", 0.0)),
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "calmar": float(metrics.get("calmar", 0.0)),
            "win_rate": win_rate,
        },
        "risk_controls": {
            "drawdown_circuit_pct": float(metrics.get("drawdown_circuit_pct", 0.0)),
            "circuit_cooldown_days": int(float(metrics.get("circuit_cooldown_days", 0))),
            "drawdown_circuit_triggers": circuit_triggers,
            "circuit_active_days": circuit_active_days,
        },
        "alerts": alerts,
        "risk_score": score,
        "risk_level": risk_level,
        "recommendations": recommendations,
    }
    report["report_hash"] = _stable_hash(
        {
            "period": report["period"],
            "effective_symbols": report["effective_symbols"],
            "thresholds": report["thresholds"],
            "performance_snapshot": report["performance_snapshot"],
        }
    )
    return report


def format_portfolio_risk_summary(report: dict[str, Any]) -> str:
    lines = [
        "风险评估:",
        f"- 风险等级: {report.get('risk_level', 'unknown')} (score={int(report.get('risk_score', 0))})",
        f"- 标的数/单票峰值权重: {report.get('exposure', {}).get('symbol_count', 0)} / {report.get('exposure', {}).get('max_single_weight_used', 0.0) * 100:.2f}%",
        f"- 行业峰值权重: {report.get('exposure', {}).get('max_industry_weight_used', 0.0) * 100:.2f}%",
        f"- 回撤阈值: -{report.get('thresholds', {}).get('max_drawdown_limit', 0.0) * 100:.2f}%",
    ]
    alerts = report.get("alerts") or []
    if alerts:
        lines.append("- 告警:")
        for item in alerts:
            lines.append(f"  - [{item.get('severity', 'unknown')}] {item.get('message', '')}")
    else:
        lines.append("- 告警: 无")
    return "\n".join(lines)


def export_portfolio_risk_report(report: dict[str, Any], output_dir: str) -> dict[str, str]:
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    period = report.get("period") or {}
    symbol_key = ",".join(report.get("effective_symbols") or report.get("input_symbols") or [])
    prefix_hash = _stable_hash(
        {
            "period": period,
            "symbols": symbol_key,
            "report_hash": report.get("report_hash"),
        }
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = f"risk_portfolio_{prefix_hash}_{stamp}"
    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    lines = [
        "# 组合风险报告",
        "",
        f"- 生成时间: {report.get('generated_at', 'N/A')}",
        f"- 区间: {period.get('start', 'N/A')} ~ {period.get('end', 'N/A')}",
        f"- 风险等级: {report.get('risk_level', 'unknown')} (score={int(report.get('risk_score', 0))})",
        "",
        "## 风险暴露",
        f"- 标的数: {report.get('exposure', {}).get('symbol_count', 0)}",
        f"- 平均持仓数: {report.get('exposure', {}).get('avg_active_positions', 0.0):.2f}",
        f"- 最大持仓数: {report.get('exposure', {}).get('max_active_positions', 0.0):.0f}",
        f"- 单票峰值权重: {report.get('exposure', {}).get('max_single_weight_used', 0.0) * 100:.2f}%",
        f"- 隐含单票权重: {report.get('exposure', {}).get('implied_single_weight', 0.0) * 100:.2f}%",
        f"- 行业峰值权重: {report.get('exposure', {}).get('max_industry_weight_used', 0.0) * 100:.2f}%",
        "",
        "## 熔断状态",
        f"- 回撤熔断阈值: -{report.get('risk_controls', {}).get('drawdown_circuit_pct', 0.0) * 100:.2f}%",
        f"- 冷却天数: {int(report.get('risk_controls', {}).get('circuit_cooldown_days', 0))}",
        f"- 触发次数: {int(report.get('risk_controls', {}).get('drawdown_circuit_triggers', 0))}",
        f"- 熔断活跃天数: {int(report.get('risk_controls', {}).get('circuit_active_days', 0))}",
        "",
        "## 告警",
    ]
    alerts = report.get("alerts") or []
    if alerts:
        for item in alerts:
            lines.append(f"- [{item.get('severity', 'unknown')}] {item.get('message', '')}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 建议"])
    for rec in report.get("recommendations") or []:
        lines.append(f"- {rec}")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"json_path": str(json_path), "md_path": str(md_path)}
