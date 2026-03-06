import hashlib
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


_COMPARE_KEYS: list[tuple[str, str, bool]] = [
    ("total_return", "策略总收益", True),
    ("annual_return", "年化收益", True),
    ("benchmark_return", "基准收益", True),
    ("max_drawdown", "最大回撤", True),
    ("sharpe", "夏普比率", False),
    ("calmar", "卡玛比率", False),
    ("win_rate", "胜率", True),
    ("trades", "开仓次数", False),
]


def _stable_hash(value: Any, length: int = 12) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return sorted({str(s).strip().upper() for s in symbols if str(s).strip()})


def _normalize_numeric_map(values: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in values.items():
        try:
            if value is None:
                continue
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def build_backtest_record(
    mode: str,
    symbols: list[str],
    start: str,
    end: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "single").strip().lower()
    normalized_symbols = _normalize_symbols(symbols)
    period = {"start": start, "end": end}
    target_fingerprint = {
        "mode": normalized_mode,
        "symbols": normalized_symbols,
        "period": period,
    }
    clean_params = dict(params or {})
    record = {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": normalized_mode,
        "symbols": normalized_symbols,
        "period": period,
        "target_hash": _stable_hash(target_fingerprint),
        "params": clean_params,
        "params_hash": _stable_hash(clean_params),
        "metrics": _normalize_numeric_map(metrics),
    }
    if extra:
        record["extra"] = extra
    return record


def _render_metrics_markdown(metrics: dict[str, float]) -> list[str]:
    year_items = sorted(
        [(int(k.split("_")[-1]), float(v)) for k, v in metrics.items() if k.startswith("year_return_")],
        key=lambda x: x[0],
    )
    yearly_text = ", ".join([f"{y}: {r * 100:.2f}%" for y, r in year_items]) if year_items else "N/A"
    lines = [
        f"- 区间样本: {int(metrics.get('samples', 0))} 交易日",
        f"- 策略总收益: {metrics.get('total_return', 0.0) * 100:.2f}%",
        f"- 年化收益: {metrics.get('annual_return', 0.0) * 100:.2f}%",
        f"- 基准收益: {metrics.get('benchmark_return', 0.0) * 100:.2f}%",
        f"- 最大回撤: {metrics.get('max_drawdown', 0.0) * 100:.2f}%",
        f"- 夏普比率: {metrics.get('sharpe', 0.0):.2f}",
        f"- 卡玛比率: {metrics.get('calmar', 0.0):.2f}",
        f"- 胜率: {metrics.get('win_rate', 0.0) * 100:.2f}%",
        f"- 开仓次数: {int(metrics.get('trades', 0))}",
        f"- 年度分解: {yearly_text}",
        f"- 滚动回撤(3M/6M/12M): {metrics.get('rolling_drawdown_63', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_126', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_252', 0.0) * 100:.2f}%",
        f"- 成本模型: 手续费={metrics.get('fee_rate', 0.0) * 100:.2f}% / 滑点={metrics.get('slippage_bps', 0.0):.1f}bps",
        f"- 交易约束: 最小持仓={int(metrics.get('min_hold_days', 1))}天 / 信号确认={int(metrics.get('signal_confirm_days', 1))}天",
    ]
    if "max_positions" in metrics:
        lines.append(f"- 最大持仓限制: {int(metrics.get('max_positions', 1))}")
    if "max_single_weight_limit" in metrics:
        lines.append(
            f"- 单票约束: 上限={metrics.get('max_single_weight_limit', 1.0) * 100:.2f}% / "
            f"实际峰值={metrics.get('max_single_weight_used', 0.0) * 100:.2f}%"
        )
    if "avg_capital_utilization" in metrics:
        lines.append(f"- 平均资金利用率: {metrics.get('avg_capital_utilization', 0.0) * 100:.2f}%")
    return lines


def render_backtest_markdown(record: dict[str, Any]) -> str:
    symbols_text = ", ".join(record.get("symbols", [])) or "N/A"
    period = record.get("period") or {}
    lines = [
        f"# 回测记录（{record.get('mode', 'unknown')}）",
        "",
        f"- 生成时间: {record.get('generated_at', 'N/A')}",
        f"- 标的: {symbols_text}",
        f"- 区间: {period.get('start', 'N/A')} ~ {period.get('end', 'N/A')}",
        f"- 目标指纹: {record.get('target_hash', '')}",
        f"- 参数指纹: {record.get('params_hash', '')}",
        "",
        "## 参数",
    ]
    params = record.get("params") or {}
    if not params:
        lines.append("- N/A")
    else:
        for key in sorted(params.keys()):
            lines.append(f"- {key}: {params[key]}")
    lines.extend(["", "## 指标"])
    lines.extend(_render_metrics_markdown(record.get("metrics") or {}))
    extra = record.get("extra")
    if extra:
        lines.extend(["", "## 附加信息"])
        for key in sorted(extra.keys()):
            lines.append(f"- {key}: {extra[key]}")
    return "\n".join(lines)


def _record_pattern(mode: str, target_hash: str) -> str:
    return f"bt_{mode}_{target_hash}_*.json"


def _load_record(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_metric_change(label: str, current: float, previous: float, percentage: bool) -> str:
    delta = current - previous
    if percentage:
        return f"{label} {delta * 100:+.2f}pp"
    if abs(delta - round(delta)) < 1e-9:
        return f"{label} {delta:+.0f}"
    return f"{label} {delta:+.2f}"


def _build_compare_text(current_metrics: dict[str, float], previous_metrics: dict[str, float]) -> Optional[str]:
    chunks: list[str] = []
    for key, label, percentage in _COMPARE_KEYS:
        if key not in current_metrics or key not in previous_metrics:
            continue
        cur = float(current_metrics[key])
        prev = float(previous_metrics[key])
        if abs(cur - prev) < 1e-10:
            continue
        chunks.append(_format_metric_change(label, cur, prev, percentage))
    if not chunks:
        return "参数对比: 与上次记录相比，核心指标无变化。"
    return "参数对比: " + "；".join(chunks[:8])


def export_backtest_record(
    mode: str,
    symbols: list[str],
    start: str,
    end: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    output_dir: str,
    extra: Optional[dict[str, Any]] = None,
    compare_last: bool = False,
) -> dict[str, Optional[str]]:
    record = build_backtest_record(
        mode=mode,
        symbols=symbols,
        start=start,
        end=end,
        params=params,
        metrics=metrics,
        extra=extra,
    )
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_path: Optional[str] = None
    compare_text: Optional[str] = None
    if compare_last:
        candidates = sorted(
            [p for p in out_dir.glob(_record_pattern(record["mode"], record["target_hash"])) if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            baseline_path = str(candidates[0])
            try:
                prev = _load_record(baseline_path)
                compare_text = _build_compare_text(
                    current_metrics=record.get("metrics", {}),
                    previous_metrics=(prev or {}).get("metrics", {}),
                )
            except Exception as exc:
                compare_text = f"参数对比: 读取历史基线失败（{type(exc).__name__}: {exc}）"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = f"bt_{record['mode']}_{record['target_hash']}_{record['params_hash']}_{stamp}"
    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_backtest_markdown(record))

    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "baseline_path": baseline_path,
        "compare_text": compare_text,
    }


def export_grid_results(
    mode: str,
    symbols: list[str],
    start: str,
    end: str,
    sort_by: str,
    results: list[dict[str, Any]],
    output_dir: str,
) -> dict[str, str]:
    normalized_mode = str(mode or "single").strip().lower()
    target_hash = _stable_hash(
        {
            "mode": normalized_mode,
            "symbols": _normalize_symbols(symbols),
            "period": {"start": start, "end": end},
        }
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = f"bt_grid_{normalized_mode}_{target_hash}_{stamp}"

    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"
    csv_path = out_dir / f"{prefix}.csv"

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": normalized_mode,
        "symbols": _normalize_symbols(symbols),
        "period": {"start": start, "end": end},
        "sort_by": sort_by,
        "result_count": len(results),
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)

    md_lines = [
        f"# 参数网格回测（{normalized_mode}）",
        "",
        f"- 生成时间: {payload['generated_at']}",
        f"- 标的: {', '.join(payload['symbols'])}",
        f"- 区间: {start} ~ {end}",
        f"- 排序字段: {sort_by}",
        f"- 成功组合数: {len(results)}",
        "",
        "| 排名 | 年化收益 | 总收益 | 最大回撤 | 夏普 | 参数 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(results, start=1):
        metrics = row.get("metrics") or {}
        params = row.get("params") or {}
        md_lines.append(
            "| "
            + f"{idx} | "
            + f"{float(metrics.get('annual_return', 0.0)) * 100:.2f}% | "
            + f"{float(metrics.get('total_return', 0.0)) * 100:.2f}% | "
            + f"{float(metrics.get('max_drawdown', 0.0)) * 100:.2f}% | "
            + f"{float(metrics.get('sharpe', 0.0)):.2f} | "
            + f"fee={float(params.get('fee_rate', 0.0)):.4f}, slip={float(params.get('slippage_bps', 0.0)):.1f}bps, hold={int(params.get('min_hold_days', 1))}, confirm={int(params.get('signal_confirm_days', 1))}, max_pos={int(params.get('max_positions', 1))}, stop={float(params.get('stop_loss_pct', 0.0)) * 100:.2f}%, take={float(params.get('take_profit_pct', 0.0)) * 100:.2f}%, dd_circuit={float(params.get('drawdown_circuit_pct', 0.0)) * 100:.2f}%, cooldown={int(params.get('circuit_cooldown_days', 0))}d, industry_cap={float(params.get('max_industry_weight', 1.0)) * 100:.2f}%, single_cap={float(params.get('max_single_weight', 1.0)) * 100:.2f}% |"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "annual_return",
                "total_return",
                "max_drawdown",
                "sharpe",
                "calmar",
                "win_rate",
                "trades",
                "fee_rate",
                "slippage_bps",
                "min_hold_days",
                "signal_confirm_days",
                "max_positions",
                "stop_loss_pct",
                "take_profit_pct",
                "drawdown_circuit_pct",
                "circuit_cooldown_days",
                "max_industry_weight",
                "max_single_weight",
            ]
        )
        for idx, row in enumerate(results, start=1):
            metrics = row.get("metrics") or {}
            params = row.get("params") or {}
            writer.writerow(
                [
                    idx,
                    metrics.get("annual_return", 0.0),
                    metrics.get("total_return", 0.0),
                    metrics.get("max_drawdown", 0.0),
                    metrics.get("sharpe", 0.0),
                    metrics.get("calmar", 0.0),
                    metrics.get("win_rate", 0.0),
                    metrics.get("trades", 0.0),
                    params.get("fee_rate", 0.0),
                    params.get("slippage_bps", 0.0),
                    params.get("min_hold_days", 1),
                    params.get("signal_confirm_days", 1),
                    params.get("max_positions", 1),
                    params.get("stop_loss_pct", 0.0),
                    params.get("take_profit_pct", 0.0),
                    params.get("drawdown_circuit_pct", 0.0),
                    params.get("circuit_cooldown_days", 0),
                    params.get("max_industry_weight", 1.0),
                    params.get("max_single_weight", 1.0),
                ]
            )

    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "csv_path": str(csv_path),
    }
