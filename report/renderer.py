from datetime import datetime
from typing import Dict

import pandas as pd


def build_report(symbol: str, df: pd.DataFrame, signals: Dict[str, str]) -> str:
    latest = df.iloc[-1]
    prev_close = df.iloc[-2]["Close"] if len(df) >= 2 else latest["Close"]
    change_pct = (latest["Close"] / prev_close - 1.0) * 100 if prev_close else 0.0

    amount_text = f"{latest.get('Amount', float('nan')):,.0f}" if pd.notna(latest.get("Amount", float("nan"))) else "N/A"
    turnover_text = f"{latest.get('Turnover', float('nan')):.2f}%" if pd.notna(latest.get("Turnover", float("nan"))) else "N/A"

    lines = [
        f"{symbol} 分析报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
        f"收盘价: {latest['Close']:.2f} ({change_pct:+.2f}%)",
        f"成交量: {latest['Volume']:,.0f}",
        f"成交额: {amount_text}",
        f"换手率: {turnover_text}",
        f"MA20/MA60: {latest.get('MA20', float('nan')):.2f} / {latest.get('MA60', float('nan')):.2f}",
        f"RSI14: {latest.get('RSI14', float('nan')):.2f}",
        f"MACD/MACD_SIGNAL: {latest.get('MACD', float('nan')):.4f} / {latest.get('MACD_SIGNAL', float('nan')):.4f}",
        "策略模板信号:",
        f"- 趋势: {signals['trend']}",
        f"- MACD: {signals['macd_signal']}",
        f"- RSI: {signals['rsi_signal']}",
        f"- 布林: {signals['boll_signal']}",
        f"- 结论: {signals['summary']}",
    ]
    return "\n".join(lines)
