import json
from typing import Any, Optional


_DEFAULT_SAFETY_NOTE = "仅供研究，不构成投资建议。"
_SAFETY_CORE = "仅供研究，不构成投资建议"
_BANNED_PHRASES = (
    "保证收益",
    "稳赚",
    "必涨",
    "确定上涨",
    "无风险",
    "确定性收益",
)
_SCHEMA_FIELDS = ("conclusion", "evidence", "risks", "watch_points", "safety_note")

_SEMANTIC_RULES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "evidence": [
        ("ma_trend", ("ma20", "ma60", "均线", "趋势")),
        ("macd_state", ("macd", "dif", "dea")),
        ("rsi_state", ("rsi", "超买", "超卖")),
        ("boll_state", ("布林", "boll", "中轨", "上轨", "下轨")),
        ("price_level", ("收盘价", "价格", "价位", "高于", "低于")),
        ("volume_state", ("成交量", "量能", "换手", "amount")),
    ],
    "risks": [
        ("macro_market", ("宏观", "市场", "情绪", "流动性", "波动")),
        ("policy_industry", ("政策", "监管", "行业", "竞争")),
        ("fundamental", ("业绩", "盈利", "基本面", "财务", "经营")),
        ("execution_uncertainty", ("不确定", "执行", "纪律", "风控", "偏离")),
    ],
    "watch_points": [
        ("watch_ma_break", ("突破ma", "ma20", "ma60", "均线突破")),
        ("watch_macd_cross", ("macd", "金叉", "死叉", "交叉")),
        ("watch_rsi_threshold", ("rsi", "70", "30", "超买", "超卖")),
        ("watch_boll_break", ("布林", "上轨", "下轨", "中轨")),
        ("watch_volume_spike", ("成交量", "量能", "放量", "缩量")),
    ],
}


def _extract_json_payload(raw: str) -> Optional[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except (TypeError, ValueError):
        pass

    left = text.find("{")
    right = text.rfind("}")
    if left >= 0 and right > left:
        candidate = text[left : right + 1]
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except (TypeError, ValueError):
            return None
    return None


def _string_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        out = [str(item).strip() for item in value if str(item).strip()]
        if out:
            return out[:4]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(default)


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_text_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return bool(cleaned)


def _contains_banned_phrase(text: str) -> bool:
    plain = str(text or "")
    return any(term in plain for term in _BANNED_PHRASES)


def _normalize_safety_note(text: str) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return _DEFAULT_SAFETY_NOTE
    if _SAFETY_CORE in raw:
        # Keep a single canonical safety note even when model duplicates it
        # with/without punctuation.
        return _DEFAULT_SAFETY_NOTE
    return f"{raw} {_DEFAULT_SAFETY_NOTE}".strip()


def _fallback_from_text(raw: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
    conclusion = lines[0] if lines else "当前信号中性，等待更高置信度触发。"
    return {
        "conclusion": conclusion,
        "evidence": ["建议结合 MA/MACD/RSI 与价格行为交叉验证。"],
        "risks": ["市场存在不确定性，历史表现不代表未来。"],
        "watch_points": ["关注量价共振与关键均线突破有效性。"],
        "safety_note": _DEFAULT_SAFETY_NOTE,
    }


def normalize_structured_summary(payload: dict[str, Any]) -> dict[str, Any]:
    conclusion = str(payload.get("conclusion") or payload.get("summary") or "").strip()
    if not conclusion:
        conclusion = "当前信号偏中性，建议等待更明确方向。"

    evidence = _string_list(
        payload.get("evidence") or payload.get("key_evidence"),
        default=["证据字段缺失，请结合原始技术指标复核。"],
    )
    risks = _string_list(
        payload.get("risks") or payload.get("risk_points"),
        default=["市场波动可能导致结论偏离预期。"],
    )
    watch_points = _string_list(
        payload.get("watch_points") or payload.get("observations"),
        default=["关注趋势延续与成交量配合情况。"],
    )
    safety_note = _normalize_safety_note(str(payload.get("safety_note") or ""))

    normalized = {
        "conclusion": conclusion,
        "evidence": evidence,
        "risks": risks,
        "watch_points": watch_points,
        "safety_note": safety_note,
    }
    return enforce_safety_rules(normalized)


def enforce_safety_rules(summary: dict[str, Any]) -> dict[str, Any]:
    safe = dict(summary)
    conclusion = str(safe.get("conclusion", "")).strip()
    if _contains_banned_phrase(conclusion):
        safe["conclusion"] = "当前结构存在不确定性，禁止将研究结论等同于确定收益。"

    risks = _string_list(safe.get("risks"), default=["市场存在不确定性与回撤风险。"])
    if not any("不确定" in item or "风险" in item for item in risks):
        risks.append("结论存在不确定性，请严格执行风险控制。")
    safe["risks"] = risks[:4]

    safe["safety_note"] = _normalize_safety_note(str(safe.get("safety_note", "")))
    return safe


def parse_structured_summary(raw: str) -> dict[str, Any]:
    payload = _extract_json_payload(raw)
    if payload is None:
        payload = _fallback_from_text(raw)
    return normalize_structured_summary(payload)


def evaluate_schema_completeness(summary: Optional[dict[str, Any]]) -> dict[str, Any]:
    data = summary or {}
    checks = {
        "conclusion": _is_non_empty_text(data.get("conclusion")),
        "evidence": _is_non_empty_text_list(data.get("evidence")),
        "risks": _is_non_empty_text_list(data.get("risks")),
        "watch_points": _is_non_empty_text_list(data.get("watch_points")),
        "safety_note": _is_non_empty_text(data.get("safety_note")),
    }
    passed = sum(1 for ok in checks.values() if ok)
    total = len(_SCHEMA_FIELDS)
    rate = passed / total if total else 0.0
    return {
        "required_fields": list(_SCHEMA_FIELDS),
        "field_checks": checks,
        "filled_fields": int(passed),
        "total_fields": int(total),
        "completeness_rate": float(rate),
        "completeness_pct": float(rate * 100.0),
        "pass_95pct": bool(rate >= 0.95),
    }


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    inter = left & right
    return float(len(inter) / len(union))


def _item_set(summary: dict[str, Any], key: str) -> set[str]:
    value = summary.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _normalize_text_for_tag(text: str) -> str:
    raw = str(text or "").strip().lower()
    keep = []
    for ch in raw:
        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            keep.append(ch)
    return "".join(keep)


def _semantic_tag(field: str, text: str) -> str:
    normalized = _normalize_text_for_tag(text)
    rules = _SEMANTIC_RULES.get(field, [])
    for tag, keywords in rules:
        if any(keyword in normalized for keyword in keywords):
            return tag
    return normalized[:24] if normalized else ""


def _semantic_item_set(summary: dict[str, Any], key: str) -> set[str]:
    value = summary.get(key)
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        tag = _semantic_tag(key, str(item))
        if tag:
            out.add(tag)
    return out


def _average_pairwise_jaccard(sets: list[set[str]]) -> float:
    if len(sets) <= 1:
        return 1.0
    total = 0.0
    count = 0
    for idx in range(len(sets)):
        for jdx in range(idx + 1, len(sets)):
            total += _jaccard_similarity(sets[idx], sets[jdx])
            count += 1
    if count <= 0:
        return 1.0
    return float(total / count)


def evaluate_low_temp_stability(
    samples: list[dict[str, Any]],
    target_runs: Optional[int] = None,
) -> dict[str, Any]:
    safe_samples = [item for item in samples if isinstance(item, dict)]
    n = len(safe_samples)
    expected_runs = max(int(target_runs or n or 0), 0)
    if n == 0:
        return {
            "target_runs": int(expected_runs),
            "completed_runs": 0,
            "schema_avg_pct": 0.0,
            "schema_pass_rate": 0.0,
            "dominant_conclusion": "",
            "conclusion_consistency": 0.0,
            "list_jaccard": {"evidence": 0.0, "risks": 0.0, "watch_points": 0.0},
            "mean_list_jaccard": 0.0,
            "stability_score": 0.0,
            "stable": False,
        }

    schema_reports = [evaluate_schema_completeness(item) for item in safe_samples]
    schema_avg_pct = sum(float(rep.get("completeness_pct", 0.0)) for rep in schema_reports) / n
    schema_pass_rate = sum(1 for rep in schema_reports if bool(rep.get("pass_95pct", False))) / n

    conclusion_counts: dict[str, int] = {}
    for item in safe_samples:
        conclusion = str(item.get("conclusion", "")).strip()
        if conclusion:
            conclusion_counts[conclusion] = conclusion_counts.get(conclusion, 0) + 1
    if conclusion_counts:
        dominant_conclusion, dominant_count = max(conclusion_counts.items(), key=lambda kv: kv[1])
        conclusion_consistency = float(dominant_count / n)
    else:
        dominant_conclusion = ""
        conclusion_consistency = 0.0

    evidence_sets = [_semantic_item_set(item, "evidence") for item in safe_samples]
    risk_sets = [_semantic_item_set(item, "risks") for item in safe_samples]
    watch_sets = [_semantic_item_set(item, "watch_points") for item in safe_samples]
    jaccard_evidence = _average_pairwise_jaccard(evidence_sets)
    jaccard_risks = _average_pairwise_jaccard(risk_sets)
    jaccard_watch = _average_pairwise_jaccard(watch_sets)
    mean_list_jaccard = float((jaccard_evidence + jaccard_risks + jaccard_watch) / 3.0)

    # Weighted composite for quick pass/fail reading.
    stability_score = (
        0.4 * conclusion_consistency
        + 0.3 * mean_list_jaccard
        + 0.3 * schema_pass_rate
    )

    return {
        "target_runs": int(expected_runs),
        "completed_runs": int(n),
        "schema_avg_pct": float(schema_avg_pct),
        "schema_pass_rate": float(schema_pass_rate),
        "dominant_conclusion": dominant_conclusion,
        "conclusion_consistency": float(conclusion_consistency),
        "list_jaccard": {
            "evidence": float(jaccard_evidence),
            "risks": float(jaccard_risks),
            "watch_points": float(jaccard_watch),
        },
        "mean_list_jaccard": float(mean_list_jaccard),
        "stability_score": float(stability_score),
        "stable": bool(stability_score >= 0.80),
    }


def format_low_temp_stability_report(report: dict[str, Any]) -> str:
    list_jaccard = report.get("list_jaccard") or {}
    return "\n".join(
        [
            "LLM 低温度稳定性评估:",
            f"- 运行次数: {int(report.get('completed_runs', 0))}/{int(report.get('target_runs', 0))}",
            f"- Schema平均齐全率: {float(report.get('schema_avg_pct', 0.0)):.2f}%",
            f"- Schema通过率(>=95%): {float(report.get('schema_pass_rate', 0.0)) * 100:.2f}%",
            f"- 结论一致率: {float(report.get('conclusion_consistency', 0.0)) * 100:.2f}%",
            f"- 主导结论: {str(report.get('dominant_conclusion', '')).strip() or 'N/A'}",
            (
                "- 语义重合度(Jaccard): "
                f"evidence={float(list_jaccard.get('evidence', 0.0)) * 100:.2f}% / "
                f"risks={float(list_jaccard.get('risks', 0.0)) * 100:.2f}% / "
                f"watch_points={float(list_jaccard.get('watch_points', 0.0)) * 100:.2f}%"
            ),
            f"- 综合稳定分: {float(report.get('stability_score', 0.0)):.3f}",
            f"- 稳定性结论: {'通过' if bool(report.get('stable', False)) else '需优化'}",
        ]
    )


def format_structured_summary(summary: dict[str, Any]) -> str:
    conclusion = str(summary.get("conclusion", "")).strip()
    evidence = _string_list(summary.get("evidence"), default=["N/A"])
    risks = _string_list(summary.get("risks"), default=["N/A"])
    watch_points = _string_list(summary.get("watch_points"), default=["N/A"])
    safety_note = str(summary.get("safety_note", _DEFAULT_SAFETY_NOTE)).strip()
    lines = [
        "1) 当前结构判断：",
        conclusion or "N/A",
        "",
        "2) 关键证据：",
    ]
    for item in evidence:
        lines.append(f"- {item}")
    lines.extend(["", "3) 主要风险："])
    for item in risks:
        lines.append(f"- {item}")
    lines.extend(["", "4) 待观察点："])
    for item in watch_points:
        lines.append(f"- {item}")
    lines.extend(["", f"风险声明：{safety_note}"])
    return "\n".join(lines)
