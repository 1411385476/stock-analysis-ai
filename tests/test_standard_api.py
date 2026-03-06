import json
import os
import tempfile
import unittest
from pathlib import Path

from report.standard_api import build_standard_snapshot, export_standard_snapshot


class StandardApiTestCase(unittest.TestCase):
    def test_build_standard_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "analysis_reports").mkdir(parents=True, exist_ok=True)
            (root / "candidate_pools").mkdir(parents=True, exist_ok=True)
            (root / "backtests").mkdir(parents=True, exist_ok=True)
            (root / "risk_reports").mkdir(parents=True, exist_ok=True)

            (root / "analysis_reports" / "analysis_x.json").write_text(
                json.dumps(
                    {
                        "symbol": "600519",
                        "period": {"start": "2025-01-01", "end": "2026-03-06"},
                        "signals": {"summary": "信号中性"},
                        "llm": {"structured": {"conclusion": "信号中性"}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "candidate_pools" / "candidate_x.csv").write_text(
                "symbol,name,score_total\n600519,贵州茅台,91.2\n000001,平安银行,88.3\n",
                encoding="utf-8",
            )
            (root / "backtests" / "bt_portfolio_x.json").write_text(
                json.dumps(
                    {
                        "period": {"start": "2025-01-01", "end": "2026-03-06"},
                        "params": {"max_positions": 2},
                        "metrics": {"annual_return": 0.12},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "risk_reports" / "risk_portfolio_x.json").write_text(
                json.dumps(
                    {
                        "risk_level": "low",
                        "risk_score": 95,
                        "alerts": [],
                        "risk_controls": {"risk_event_count": 3},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_standard_snapshot(root, candidate_top_n=1)
            self.assertEqual(int(payload.get("schema_version", 0)), 1)
            self.assertEqual(str(payload.get("single_analysis", {}).get("symbol", "")), "600519")
            self.assertEqual(int(payload.get("candidate_pool", {}).get("count", 0)), 2)
            self.assertEqual(len(payload.get("candidate_pool", {}).get("top", [])), 1)
            self.assertEqual(str(payload.get("risk_report", {}).get("risk_level", "")), "low")

    def test_export_standard_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "analysis_reports").mkdir(parents=True, exist_ok=True)
            (root / "analysis_reports" / "analysis_x.json").write_text(
                json.dumps({"symbol": "600519"}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = export_standard_snapshot(root)
            self.assertTrue(os.path.exists(out["json_path"]))
            self.assertTrue(os.path.exists(out["latest_path"]))


if __name__ == "__main__":
    unittest.main()
