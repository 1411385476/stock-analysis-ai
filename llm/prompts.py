import json
from typing import Dict


SYSTEM_PROMPT = "你是谨慎、可审计的A股量化研究助手，只能基于输入信号给出研究结论，不得承诺收益。"


def build_technical_prompt(symbol: str, report_text: str, signals: Dict[str, str]) -> str:
    return (
        "【技术面解释】\n"
        f"股票: {symbol}\n"
        f"技术信号: {json.dumps(signals, ensure_ascii=False)}\n"
        "请给出当前结构判断（1段）与关键证据（2-4条）。\n"
        f"数据摘要:\n{report_text}\n"
    )


def build_strategy_review_prompt(symbol: str, signals: Dict[str, str]) -> str:
    return (
        "【策略复盘】\n"
        f"股票: {symbol}\n"
        f"技术信号: {json.dumps(signals, ensure_ascii=False)}\n"
        "请输出可执行待观察点（2-4条），强调触发条件而非主观预测。\n"
    )


def build_risk_prompt() -> str:
    return (
        "【风险建议】\n"
        "请输出主要风险（2-4条），必须包含不确定性描述。\n"
        "禁止出现保证收益、确定上涨、稳赚等承诺性表达。\n"
    )


def build_structured_analysis_prompt(
    symbol: str,
    report_text: str,
    signals: Dict[str, str],
    stability_mode: bool = False,
) -> str:
    schema = (
        '{\n'
        '  "conclusion": "string",\n'
        '  "evidence": ["string"],\n'
        '  "risks": ["string"],\n'
        '  "watch_points": ["string"],\n'
        '  "safety_note": "string"\n'
        "}"
    )
    base = (
        "你将收到三段任务，最终请严格输出一个 JSON 对象，不要输出 Markdown，不要输出多余文字。\n\n"
        f"{build_technical_prompt(symbol=symbol, report_text=report_text, signals=signals)}\n"
        f"{build_strategy_review_prompt(symbol=symbol, signals=signals)}\n"
        f"{build_risk_prompt()}\n"
        "输出要求:\n"
        f"1) JSON schema 严格遵循:\n{schema}\n"
        "2) evidence/risks/watch_points 每个数组 2-4 条\n"
        "3) safety_note 固定包含“仅供研究，不构成投资建议”\n"
    )
    if not stability_mode:
        return base
    return (
        base
        + "4) 稳定性模式：请尽量复用固定槽位语义，不要随意扩展。\n"
        + "   evidence 优先覆盖：均线趋势 / 动量指标 / 波动位置\n"
        + "   risks 优先覆盖：市场宏观 / 行业政策 / 个股基本面 / 执行纪律\n"
        + "   watch_points 优先覆盖：均线突破 / MACD交叉 / RSI阈值 / 布林或量能触发\n"
    )
