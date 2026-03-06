import os
import tempfile
import unittest

from portfolio.risk import (
    evaluate_portfolio_risk,
    export_portfolio_risk_report,
    format_portfolio_risk_summary,
)


class PortfolioRiskTestCase(unittest.TestCase):
    def test_evaluate_portfolio_risk_with_alerts(self) -> None:
        metrics = {
            "max_positions": 1,
            "avg_active_positions": 0.8,
            "max_active_positions": 1.0,
            "annual_return": 0.05,
            "total_return": 0.02,
            "max_drawdown": -0.2,
            "sharpe": 0.2,
            "calmar": 0.3,
            "win_rate": 0.35,
        }
        report = evaluate_portfolio_risk(
            metrics=metrics,
            input_symbols=["600519", "000001"],
            effective_symbols=["600519", "000001"],
            failed_symbols=[],
            period_start="2025-01-01",
            period_end="2026-03-05",
            max_drawdown_limit=0.15,
            max_single_weight=0.35,
            min_holdings=3,
        )
        self.assertIn("risk_level", report)
        self.assertIn("risk_score", report)
        self.assertTrue(len(report.get("alerts", [])) >= 1)
        summary = format_portfolio_risk_summary(report)
        self.assertIn("风险评估", summary)

    def test_export_portfolio_risk_report(self) -> None:
        report = evaluate_portfolio_risk(
            metrics={"max_positions": 2, "max_drawdown": -0.08, "sharpe": 1.0, "win_rate": 0.55},
            input_symbols=["600519", "000001", "300750"],
            effective_symbols=["600519", "000001", "300750"],
            failed_symbols=[],
            period_start="2025-01-01",
            period_end="2026-03-05",
            max_drawdown_limit=0.15,
            max_single_weight=0.6,
            min_holdings=3,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            out = export_portfolio_risk_report(report, temp_dir)
            self.assertTrue(os.path.exists(out["json_path"]))
            self.assertTrue(os.path.exists(out["md_path"]))

    def test_evaluate_portfolio_risk_uses_actual_single_weight(self) -> None:
        report = evaluate_portfolio_risk(
            metrics={
                "max_positions": 3,
                "max_single_weight_used": 0.5,
                "max_drawdown": -0.05,
                "sharpe": 1.1,
                "win_rate": 0.6,
            },
            input_symbols=["600519", "000001", "300750"],
            effective_symbols=["600519", "000001", "300750"],
            failed_symbols=[],
            period_start="2025-01-01",
            period_end="2026-03-05",
            max_drawdown_limit=0.15,
            max_single_weight=0.35,
            min_holdings=3,
        )
        exposure = report.get("exposure", {})
        self.assertAlmostEqual(float(exposure.get("max_single_weight_used", 0.0)), 0.5, places=9)
        alert_codes = [str(item.get("code", "")) for item in report.get("alerts", [])]
        self.assertIn("single_weight", alert_codes)


if __name__ == "__main__":
    unittest.main()
