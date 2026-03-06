import json
import tempfile
import unittest
from pathlib import Path

from dashboard.app import build_dashboard_html, generate_dashboard


class DashboardTestCase(unittest.TestCase):
    def test_generate_dashboard_from_latest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            (data_dir / "analysis_reports").mkdir(parents=True, exist_ok=True)
            (data_dir / "candidate_pools").mkdir(parents=True, exist_ok=True)
            (data_dir / "backtests").mkdir(parents=True, exist_ok=True)
            (data_dir / "risk_reports").mkdir(parents=True, exist_ok=True)
            (root / "charts").mkdir(parents=True, exist_ok=True)

            chart_path = root / "charts" / "sample.png"
            chart_path.write_bytes(b"fake-png-binary")

            analysis = {
                "symbol": "600519",
                "chart_path": str(chart_path),
                "llm": {
                    "structured": {
                        "conclusion": "信号中性，等待更明确方向。",
                        "evidence": ["证据A"],
                        "risks": ["风险A"],
                        "watch_points": ["观察点A"],
                        "safety_note": "仅供研究，不构成投资建议。",
                    },
                    "schema_quality": {"completeness_pct": 100.0},
                    "stability": {"stability_score": 0.9},
                },
            }
            (data_dir / "analysis_reports" / "analysis_test.json").write_text(
                json.dumps(analysis, ensure_ascii=False),
                encoding="utf-8",
            )

            candidate_csv = (
                "symbol,name,pct_change,score_total,amount,volume\n"
                "sh600519,贵州茅台,1.2,78.5,1000000,5000\n"
                "sz000001,平安银行,0.8,74.3,800000,12000\n"
            )
            (data_dir / "candidate_pools" / "candidate_pool_test.csv").write_text(
                candidate_csv,
                encoding="utf-8",
            )

            bt1 = {
                "generated_at": "2026-03-05 10:00:00",
                "metrics": {"annual_return": 0.1, "total_return": 0.08, "max_drawdown": -0.06, "benchmark_return": 0.05},
            }
            bt2 = {
                "generated_at": "2026-03-06 10:00:00",
                "metrics": {"annual_return": 0.12, "total_return": 0.1, "max_drawdown": -0.05, "benchmark_return": 0.06},
            }
            (data_dir / "backtests" / "bt_portfolio_test_1.json").write_text(
                json.dumps(bt1, ensure_ascii=False),
                encoding="utf-8",
            )
            (data_dir / "backtests" / "bt_portfolio_test_2.json").write_text(
                json.dumps(bt2, ensure_ascii=False),
                encoding="utf-8",
            )

            risk = {
                "generated_at": "2026-03-06 10:00:00",
                "risk_level": "low",
                "risk_score": 92,
                "alerts": [],
                "exposure": {
                    "max_single_weight_used": 0.33,
                    "max_industry_weight_used": 0.4,
                    "implied_single_weight": 0.5,
                },
            }
            (data_dir / "risk_reports" / "risk_test.json").write_text(
                json.dumps(risk, ensure_ascii=False),
                encoding="utf-8",
            )

            html_text = build_dashboard_html(data_dir)
            self.assertIn("A-Share AI Portfolio Dashboard", html_text)
            self.assertIn("单股分析", html_text)
            self.assertIn("候选池评分", html_text)
            self.assertIn("组合回测", html_text)
            self.assertIn("风险日报", html_text)
            self.assertIn("参数对比（最新 vs 上次）", html_text)
            self.assertNotIn("历史样本不足，无法生成策略/基准对比图。", html_text)

            risk2 = {
                "generated_at": "2026-03-05 10:00:00",
                "risk_level": "medium",
                "risk_score": 75,
                "alerts": [{"severity": "low", "message": "test"}],
                "exposure": {
                    "max_single_weight_used": 0.5,
                    "max_industry_weight_used": 0.5,
                    "implied_single_weight": 0.5,
                },
            }
            (data_dir / "risk_reports" / "risk_test_2.json").write_text(
                json.dumps(risk2, ensure_ascii=False),
                encoding="utf-8",
            )
            html_text_with_risk_history = build_dashboard_html(data_dir)
            self.assertNotIn("历史样本不足，无法生成风险时序。", html_text_with_risk_history)

            out_path = root / "dashboard" / "dist" / "index.html"
            generated = generate_dashboard(out_path, data_dir)
            self.assertTrue(generated.exists())
            saved = generated.read_text(encoding="utf-8")
            self.assertIn("风险声明：仅供研究，不构成投资建议。", saved)

    def test_dashboard_falls_back_to_rule_signals_when_llm_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            (data_dir / "analysis_reports").mkdir(parents=True, exist_ok=True)
            (data_dir / "candidate_pools").mkdir(parents=True, exist_ok=True)
            (data_dir / "backtests").mkdir(parents=True, exist_ok=True)
            (data_dir / "risk_reports").mkdir(parents=True, exist_ok=True)

            analysis = {
                "symbol": "600519",
                "signals": {
                    "trend": "多头趋势",
                    "macd_signal": "观望",
                    "rsi_signal": "RSI中性",
                    "boll_signal": "布林中轨附近",
                    "summary": "信号中性，等待更明确方向。",
                },
                "llm": {"structured": {}, "schema_quality": {}, "stability": {}, "text": ""},
            }
            (data_dir / "analysis_reports" / "analysis_test.json").write_text(
                json.dumps(analysis, ensure_ascii=False),
                encoding="utf-8",
            )

            html_text = build_dashboard_html(data_dir)
            self.assertIn("信号中性，等待更明确方向。", html_text)
            self.assertIn("趋势: 多头趋势", html_text)
            self.assertIn("Schema齐全率", html_text)
            self.assertIn("N/A", html_text)


if __name__ == "__main__":
    unittest.main()
