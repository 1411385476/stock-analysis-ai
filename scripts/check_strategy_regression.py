#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report.strategy_regression import (
    SNAPSHOT_KEYS,
    build_regression_snapshot,
    compare_regression_snapshots,
)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid json root: {path}")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def _fmt(v: float) -> str:
    return f"{v:.6f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check strategy regression snapshot drift.")
    parser.add_argument(
        "--baseline",
        default="tests/fixtures/strategy_regression_baseline.json",
        help="Baseline snapshot json path.",
    )
    parser.add_argument(
        "--output",
        default="data/ci/strategy_regression_latest.json",
        help="Current snapshot output path.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline file with current snapshot and exit 0.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_path = Path(args.baseline).expanduser()
    output_path = Path(args.output).expanduser()

    current = build_regression_snapshot()
    _write_json(output_path, current)
    print(f"[regression] snapshot written: {output_path}")

    if args.update_baseline:
        _write_json(baseline_path, current)
        print(f"[regression] baseline updated: {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"[regression] baseline missing: {baseline_path}")
        print("[regression] hint: run with --update-baseline once and commit baseline.")
        return 2

    baseline = _load_json(baseline_path)
    drifts = compare_regression_snapshots(current, baseline)
    if drifts:
        print("[regression] drift detected:")
        for item in drifts:
            print(
                "  - "
                + f"{item['metric']}: current={_fmt(float(item['current']))}, "
                + f"baseline={_fmt(float(item['baseline']))}, "
                + f"delta={_fmt(float(item['delta']))}, "
                + f"threshold={_fmt(float(item['threshold']))}, "
                + f"reason={item['reason']}"
            )
        return 2

    print(f"[regression] passed ({len(SNAPSHOT_KEYS)} metrics within thresholds).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
