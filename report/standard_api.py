import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


def _latest_file(directory: Path, pattern: str) -> Optional[Path]:
    if not directory.exists():
        return None
    files = [path for path in directory.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _load_json(path: Optional[Path]) -> dict[str, Any]:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _load_candidate_preview(path: Optional[Path], top_n: int = 20) -> dict[str, Any]:
    if not path or not path.is_file():
        return {"count": 0, "top": []}
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return {"count": 0, "top": []}
    if df.empty:
        return {"count": 0, "top": []}

    df.columns = [str(col).replace("\ufeff", "").strip() for col in df.columns]
    if "score_total" in df.columns:
        df["score_total"] = pd.to_numeric(df["score_total"], errors="coerce").fillna(0.0)
        df = df.sort_values("score_total", ascending=False)

    keep = max(int(top_n), 1)
    fields = [
        "symbol",
        "name",
        "close",
        "price",
        "pct_change",
        "turnover",
        "score_total",
        "score_trend",
        "score_volume_price",
        "score_volatility",
        "score_turnover",
    ]

    top_rows: list[dict[str, Any]] = []
    for _, row in df.head(keep).iterrows():
        item: dict[str, Any] = {}
        for key in fields:
            if key not in df.columns:
                continue
            value = row.get(key)
            if pd.isna(value):
                continue
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except Exception:
                    pass
            item[key] = value
        if item:
            top_rows.append(item)
    return {"count": int(len(df)), "top": top_rows}


def build_standard_snapshot(data_dir: str | Path, candidate_top_n: int = 20) -> dict[str, Any]:
    root = Path(data_dir).expanduser()
    analysis_path = _latest_file(root / "analysis_reports", "*.json")
    candidate_path = _latest_file(root / "candidate_pools", "*.csv")
    backtest_path = _latest_file(root / "backtests", "bt_portfolio_*.json")
    grid_path = _latest_file(root / "backtests", "bt_grid_*.json")
    walk_forward_path = _latest_file(root / "backtests", "wf_portfolio_*.json")
    risk_path = _latest_file(root / "risk_reports", "risk_portfolio_*.json")
    rebalance_path = _latest_file(root / "backtests", "rebalance_*.csv")

    analysis = _load_json(analysis_path)
    backtest = _load_json(backtest_path)
    grid = _load_json(grid_path)
    walk_forward = _load_json(walk_forward_path)
    risk = _load_json(risk_path)
    candidate_preview = _load_candidate_preview(candidate_path, top_n=candidate_top_n)

    source_paths = {
        "analysis_json": str(analysis_path) if analysis_path else "",
        "candidate_csv": str(candidate_path) if candidate_path else "",
        "backtest_json": str(backtest_path) if backtest_path else "",
        "grid_json": str(grid_path) if grid_path else "",
        "walk_forward_json": str(walk_forward_path) if walk_forward_path else "",
        "risk_json": str(risk_path) if risk_path else "",
        "rebalance_csv": str(rebalance_path) if rebalance_path else "",
    }

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_dir": str(root),
        "sources": source_paths,
        "single_analysis": {
            "symbol": analysis.get("symbol", ""),
            "period": analysis.get("period", {}),
            "signals": analysis.get("signals", {}),
            "llm_structured": ((analysis.get("llm") or {}).get("structured") or {}),
            "llm_schema_quality": ((analysis.get("llm") or {}).get("schema_quality") or {}),
        },
        "candidate_pool": candidate_preview,
        "portfolio_backtest": {
            "period": backtest.get("period", {}),
            "params": backtest.get("params", {}),
            "metrics": backtest.get("metrics", {}),
        },
        "grid_backtest": {
            "sort_by": grid.get("sort_by", ""),
            "result_count": int(grid.get("result_count", 0) or 0),
            "top_results": list((grid.get("results") or [])[:10]),
            "robust_summary": grid.get("robust_summary", {}),
        },
        "walk_forward": {
            "config": walk_forward.get("config", {}),
            "windows_total": int(walk_forward.get("windows_total", 0) or 0),
            "windows_valid": int(walk_forward.get("windows_valid", 0) or 0),
            "summary": walk_forward.get("summary", {}),
            "segment_comparison": walk_forward.get("segment_comparison", {}),
        },
        "risk_report": {
            "risk_level": risk.get("risk_level", ""),
            "risk_score": risk.get("risk_score", 0),
            "alerts": risk.get("alerts", []),
            "risk_controls": risk.get("risk_controls", {}),
            "risk_events": list((risk.get("risk_events") or [])[:20]),
            "exposure": risk.get("exposure", {}),
        },
    }
    return payload


def export_standard_snapshot(
    data_dir: str | Path,
    output_path: Optional[str] = None,
    candidate_top_n: int = 20,
) -> dict[str, str]:
    payload = build_standard_snapshot(data_dir=data_dir, candidate_top_n=candidate_top_n)
    root = Path(data_dir).expanduser()

    if output_path:
        out_path = Path(output_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        return {"json_path": str(out_path), "latest_path": str(out_path)}

    api_dir = root / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    json_path = api_dir / f"standard_snapshot_{stamp}.json"
    latest_path = api_dir / "standard_snapshot_latest.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)

    return {"json_path": str(json_path), "latest_path": str(latest_path)}
