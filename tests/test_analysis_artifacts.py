import json
import os
import tempfile
import unittest

from report.analysis_artifacts import build_analysis_record, export_analysis_record


class AnalysisArtifactsTestCase(unittest.TestCase):
    def test_export_analysis_record(self) -> None:
        record = build_analysis_record(
            symbol="600519",
            start="2025-03-01",
            end="2026-03-06",
            report_text="600519 分析报告",
            signals={"trend": "多头趋势", "summary": "信号中性"},
            chart_path="/tmp/chart.png",
            llm_text="1) 当前结构判断：中性",
            llm_structured={
                "conclusion": "中性",
                "evidence": ["A"],
                "risks": ["B"],
                "watch_points": ["C"],
                "safety_note": "仅供研究，不构成投资建议。",
            },
            llm_stability={
                "target_runs": 3,
                "completed_runs": 3,
                "conclusion_consistency": 1.0,
                "mean_list_jaccard": 0.8,
                "stability_score": 0.9,
                "stable": True,
                "list_jaccard": {"evidence": 0.7, "risks": 0.8, "watch_points": 0.9},
            },
            backtest_text="回测结果: N/A",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            out = export_analysis_record(record, temp_dir)
            self.assertTrue(os.path.exists(out["json_path"]))
            self.assertTrue(os.path.exists(out["md_path"]))
            with open(out["json_path"], "r", encoding="utf-8") as f:
                payload = json.load(f)
            quality = (payload.get("llm") or {}).get("schema_quality") or {}
            self.assertGreaterEqual(float(quality.get("completeness_pct", 0.0)), 95.0)
            self.assertTrue(bool(quality.get("pass_95pct", False)))
            stability = (payload.get("llm") or {}).get("stability") or {}
            self.assertTrue(bool(stability.get("stable", False)))


if __name__ == "__main__":
    unittest.main()
