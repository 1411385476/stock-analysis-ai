from typing import Dict

import pandas as pd


def strategy_signals(df: pd.DataFrame) -> Dict[str, str]:
    """Template strategy signals based on MACD/RSI/Bollinger/MA trend."""
    if len(df) < 2:
        return {
            "trend": "数据不足",
            "macd_signal": "数据不足",
            "rsi_signal": "数据不足",
            "boll_signal": "数据不足",
            "summary": "数据不足，无法生成策略结论。",
        }

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    trend = "震荡"
    if pd.notna(latest.get("MA20")) and pd.notna(latest.get("MA60")):
        if latest["MA20"] > latest["MA60"]:
            trend = "多头趋势"
        elif latest["MA20"] < latest["MA60"]:
            trend = "空头趋势"

    macd_signal = "观望"
    if pd.notna(latest.get("MACD")) and pd.notna(latest.get("MACD_SIGNAL")):
        if latest["MACD"] > latest["MACD_SIGNAL"] and prev.get("MACD", 0) <= prev.get("MACD_SIGNAL", 0):
            macd_signal = "MACD金叉"
        elif latest["MACD"] < latest["MACD_SIGNAL"] and prev.get("MACD", 0) >= prev.get("MACD_SIGNAL", 0):
            macd_signal = "MACD死叉"

    rsi_signal = "RSI中性"
    if pd.notna(latest.get("RSI14")):
        if latest["RSI14"] >= 70:
            rsi_signal = "RSI超买"
        elif latest["RSI14"] <= 30:
            rsi_signal = "RSI超卖"

    boll_signal = "布林中轨附近"
    if pd.notna(latest.get("BBU")) and pd.notna(latest.get("BBL")):
        if latest["Close"] >= latest["BBU"]:
            boll_signal = "触及布林上轨"
        elif latest["Close"] <= latest["BBL"]:
            boll_signal = "触及布林下轨"

    signals = [trend, macd_signal, rsi_signal, boll_signal]
    if any(s in ["MACD金叉", "RSI超卖", "触及布林下轨"] for s in signals):
        summary = "偏多信号增多，关注分批跟踪。"
    elif any(s in ["MACD死叉", "RSI超买", "触及布林上轨"] for s in signals):
        summary = "偏空或过热信号出现，控制仓位与止盈。"
    else:
        summary = "信号中性，等待更明确方向。"

    return {
        "trend": trend,
        "macd_signal": macd_signal,
        "rsi_signal": rsi_signal,
        "boll_signal": boll_signal,
        "summary": summary,
    }
