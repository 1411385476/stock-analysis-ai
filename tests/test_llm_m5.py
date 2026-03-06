import unittest

from llm.prompts import build_structured_analysis_prompt
from llm.summarizer import (
    evaluate_low_temp_stability,
    evaluate_schema_completeness,
    format_low_temp_stability_report,
    format_structured_summary,
    parse_structured_summary,
)


class LlmM5TestCase(unittest.TestCase):
    def test_build_structured_analysis_prompt_contains_schema(self) -> None:
        prompt = build_structured_analysis_prompt(
            symbol="600519",
            report_text="收盘价: 1400",
            signals={"趋势": "多头", "MACD": "观望"},
        )
        self.assertIn("【技术面解释】", prompt)
        self.assertIn("【策略复盘】", prompt)
        self.assertIn("【风险建议】", prompt)
        self.assertIn('"conclusion"', prompt)
        self.assertIn('"watch_points"', prompt)

    def test_parse_structured_summary_from_json(self) -> None:
        raw = """```json
{
  "conclusion": "趋势偏多但需确认",
  "evidence": ["MA20 > MA60", "MACD未死叉"],
  "risks": ["波动加剧风险"],
  "watch_points": ["关注放量突破"],
  "safety_note": "仅供研究，不构成投资建议"
}
```"""
        summary = parse_structured_summary(raw)
        self.assertEqual(summary["conclusion"], "趋势偏多但需确认")
        self.assertGreaterEqual(len(summary["evidence"]), 1)
        self.assertIn("仅供研究，不构成投资建议", summary["safety_note"])

    def test_parse_structured_summary_enforces_safety(self) -> None:
        raw = """{
  "conclusion": "这只票必涨，保证收益",
  "evidence": ["趋势向上"],
  "risks": ["短期调整"],
  "watch_points": ["关注量能"],
  "safety_note": "请谨慎"
}"""
        summary = parse_structured_summary(raw)
        self.assertNotIn("保证收益", summary["conclusion"])
        self.assertIn("仅供研究，不构成投资建议", summary["safety_note"])
        self.assertEqual(summary["safety_note"], "仅供研究，不构成投资建议。")

    def test_parse_structured_summary_dedup_safety_note(self) -> None:
        raw = """{
  "conclusion": "中性",
  "evidence": ["证据A"],
  "risks": ["风险A"],
  "watch_points": ["观察A"],
  "safety_note": "仅供研究，不构成投资建议 仅供研究，不构成投资建议。"
}"""
        summary = parse_structured_summary(raw)
        self.assertEqual(summary["safety_note"], "仅供研究，不构成投资建议。")

    def test_parse_structured_summary_fallback_for_plain_text(self) -> None:
        raw = "当前结构偏震荡，等待突破。"
        summary = parse_structured_summary(raw)
        self.assertIn("conclusion", summary)
        self.assertGreaterEqual(len(summary["risks"]), 1)
        formatted = format_structured_summary(summary)
        self.assertIn("1) 当前结构判断", formatted)
        self.assertIn("风险声明", formatted)

    def test_evaluate_schema_completeness(self) -> None:
        summary = {
            "conclusion": "中性",
            "evidence": ["A"],
            "risks": ["B"],
            "watch_points": ["C"],
            "safety_note": "仅供研究，不构成投资建议。",
        }
        quality = evaluate_schema_completeness(summary)
        self.assertAlmostEqual(float(quality["completeness_rate"]), 1.0, places=9)
        self.assertTrue(bool(quality["pass_95pct"]))

    def test_evaluate_low_temp_stability(self) -> None:
        samples = [
            {
                "conclusion": "中性",
                "evidence": ["MA20 高于 MA60", "MACD 观望"],
                "risks": ["宏观波动风险"],
                "watch_points": ["关注 MA20 突破"],
                "safety_note": "仅供研究，不构成投资建议。",
            },
            {
                "conclusion": "中性",
                "evidence": ["均线趋势维持", "MACD 未金叉"],
                "risks": ["市场情绪波动"],
                "watch_points": ["均线突破确认", "MACD 交叉观察"],
                "safety_note": "仅供研究，不构成投资建议。",
            },
            {
                "conclusion": "中性",
                "evidence": ["MA20/MA60 仍偏多", "MACD 偏弱"],
                "risks": ["宏观政策变化", "执行不确定性"],
                "watch_points": ["观察 MA60 支撑"],
                "safety_note": "仅供研究，不构成投资建议。",
            },
        ]
        report = evaluate_low_temp_stability(samples, target_runs=3)
        self.assertEqual(int(report["completed_runs"]), 3)
        self.assertGreater(float(report["conclusion_consistency"]), 0.9)
        self.assertGreater(float(report["mean_list_jaccard"]), 0.3)
        text = format_low_temp_stability_report(report)
        self.assertIn("LLM 低温度稳定性评估", text)


if __name__ == "__main__":
    unittest.main()
