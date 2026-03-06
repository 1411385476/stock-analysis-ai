import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from llm.summarizer import evaluate_schema_completeness


def _stable_hash(value: Any, length: int = 12) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def build_analysis_record(
    symbol: str,
    start: str,
    end: str,
    report_text: str,
    signals: dict[str, Any],
    chart_path: Optional[str],
    llm_text: Optional[str],
    llm_structured: Optional[dict[str, Any]],
    llm_stability: Optional[dict[str, Any]] = None,
    backtest_text: Optional[str] = None,
) -> dict[str, Any]:
    structured = llm_structured or {}
    schema_quality = evaluate_schema_completeness(structured if structured else None)
    target_hash = _stable_hash({"symbol": symbol, "start": start, "end": end})
    return {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_hash": target_hash,
        "symbol": str(symbol).strip().upper(),
        "period": {"start": start, "end": end},
        "technical_report": report_text or "",
        "signals": signals or {},
        "chart_path": chart_path or "",
        "backtest_summary": backtest_text or "",
        "llm": {
            "text": llm_text or "",
            "structured": structured,
            "schema_quality": schema_quality,
            "stability": llm_stability or {},
        },
    }


def render_analysis_markdown(record: dict[str, Any]) -> str:
    period = record.get("period") or {}
    llm = record.get("llm") or {}
    schema = llm.get("schema_quality") or {}
    lines = [
        f"# 单股分析记录（{record.get('symbol', 'N/A')}）",
        "",
        f"- 生成时间: {record.get('generated_at', 'N/A')}",
        f"- 区间: {period.get('start', 'N/A')} ~ {period.get('end', 'N/A')}",
        f"- 目标指纹: {record.get('target_hash', '')}",
        f"- 图表: {record.get('chart_path', 'N/A') or 'N/A'}",
        "",
        "## 技术报告",
        record.get("technical_report", "N/A"),
        "",
        "## 信号",
    ]
    signals = record.get("signals") or {}
    if not signals:
        lines.append("- N/A")
    else:
        for key in sorted(signals.keys()):
            lines.append(f"- {key}: {signals[key]}")

    lines.extend(
        [
            "",
            "## LLM 结构化质量",
            f"- 字段齐全率: {float(schema.get('completeness_pct', 0.0)):.2f}% ({int(schema.get('filled_fields', 0))}/{int(schema.get('total_fields', 0))})",
            f"- 通过95%阈值: {'是' if bool(schema.get('pass_95pct', False)) else '否'}",
        ]
    )

    checks = schema.get("field_checks") or {}
    if checks:
        lines.append("- 字段检查:")
        for key in sorted(checks.keys()):
            lines.append(f"  - {key}: {'OK' if checks[key] else 'MISSING'}")

    lines.extend(["", "## LLM 解读文本", llm.get("text") or "N/A"])
    stability = llm.get("stability") or {}
    if stability:
        list_jaccard = stability.get("list_jaccard") or {}
        lines.extend(
            [
                "",
                "## LLM 稳定性",
                f"- 运行次数: {int(stability.get('completed_runs', 0))}/{int(stability.get('target_runs', 0))}",
                f"- 结论一致率: {float(stability.get('conclusion_consistency', 0.0)) * 100:.2f}%",
                f"- 列表重合度均值: {float(stability.get('mean_list_jaccard', 0.0)) * 100:.2f}%",
                (
                    "- 列表重合度细分: "
                    f"evidence={float(list_jaccard.get('evidence', 0.0)) * 100:.2f}% / "
                    f"risks={float(list_jaccard.get('risks', 0.0)) * 100:.2f}% / "
                    f"watch_points={float(list_jaccard.get('watch_points', 0.0)) * 100:.2f}%"
                ),
                f"- 综合稳定分: {float(stability.get('stability_score', 0.0)):.3f}",
                f"- 稳定性结论: {'通过' if bool(stability.get('stable', False)) else '需优化'}",
            ]
        )
    if record.get("backtest_summary"):
        lines.extend(["", "## 回测摘要", str(record.get("backtest_summary"))])
    return "\n".join(lines)


def export_analysis_record(record: dict[str, Any], output_dir: str) -> dict[str, str]:
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    symbol = str(record.get("symbol", "unknown")).strip().upper() or "UNKNOWN"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = f"analysis_{symbol}_{record.get('target_hash', 'na')}_{stamp}"
    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_analysis_markdown(record))

    return {"json_path": str(json_path), "md_path": str(md_path)}
