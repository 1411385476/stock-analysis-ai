from typing import Dict

import numpy as np
import pandas as pd


def run_backtest(df: pd.DataFrame, fee_rate: float = 0.001) -> Dict[str, float]:
    """
    Simple long-only template:
    - Buy: MA20 > MA60 and MACD > MACD_SIGNAL and RSI14 < 70
    - Sell: MA20 < MA60 or MACD < MACD_SIGNAL or RSI14 > 75
    """
    data = df.copy()
    required_cols = ["Close", "MA20", "MA60", "MACD", "MACD_SIGNAL", "RSI14"]
    if any(col not in data.columns for col in required_cols):
        return {}

    data = data.dropna(subset=required_cols)
    if len(data) < 30:
        return {}

    data["buy_signal"] = (
        (data["MA20"] > data["MA60"])
        & (data["MACD"] > data["MACD_SIGNAL"])
        & (data["RSI14"] < 70)
    )
    data["sell_signal"] = (
        (data["MA20"] < data["MA60"])
        | (data["MACD"] < data["MACD_SIGNAL"])
        | (data["RSI14"] > 75)
    )

    position = np.zeros(len(data), dtype=float)
    in_position = False
    trades = 0

    for i in range(len(data)):
        if not in_position and bool(data["buy_signal"].iloc[i]):
            in_position = True
            position[i] = 1.0
            trades += 1
        elif in_position and bool(data["sell_signal"].iloc[i]):
            in_position = False
            position[i] = 0.0
        else:
            position[i] = 1.0 if in_position else 0.0

    data["position"] = pd.Series(position, index=data.index).shift(1).fillna(0.0)
    data["ret"] = data["Close"].pct_change().fillna(0.0)
    data["trade_change"] = data["position"].diff().abs().fillna(0.0)
    data["strategy_ret"] = data["position"] * data["ret"] - data["trade_change"] * fee_rate
    data["equity"] = (1.0 + data["strategy_ret"]).cumprod()

    total_return = data["equity"].iloc[-1] - 1.0
    years = max((data.index[-1] - data.index[0]).days / 365.0, 1 / 365.0)
    annual_return = (1.0 + total_return) ** (1 / years) - 1.0

    rolling_max = data["equity"].cummax()
    drawdown = data["equity"] / rolling_max - 1.0
    max_drawdown = drawdown.min()

    if data["strategy_ret"].std(ddof=0) > 0:
        sharpe = (data["strategy_ret"].mean() / data["strategy_ret"].std(ddof=0)) * np.sqrt(252)
    else:
        sharpe = 0.0

    wins = 0
    closed = 0
    last_entry_price = None
    last_position = 0.0
    for _, row in data.iterrows():
        if last_position == 0.0 and row["position"] == 1.0:
            last_entry_price = row["Close"]
        if last_position == 1.0 and row["position"] == 0.0 and last_entry_price is not None:
            closed += 1
            if row["Close"] > last_entry_price:
                wins += 1
            last_entry_price = None
        last_position = row["position"]
    win_rate = (wins / closed) if closed > 0 else 0.0

    benchmark = (1.0 + data["ret"]).cumprod().iloc[-1] - 1.0
    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "max_drawdown": float(max_drawdown),
        "sharpe": float(sharpe),
        "win_rate": float(win_rate),
        "trades": float(trades),
        "benchmark_return": float(benchmark),
        "samples": float(len(data)),
    }


def format_backtest_report(metrics: Dict[str, float]) -> str:
    if not metrics:
        return "回测结果: 数据不足或指标缺失，无法回测。"

    return "\n".join(
        [
            "回测结果:",
            f"- 区间样本: {int(metrics['samples'])} 交易日",
            f"- 策略总收益: {metrics['total_return'] * 100:.2f}%",
            f"- 年化收益: {metrics['annual_return'] * 100:.2f}%",
            f"- 基准收益(买入持有): {metrics['benchmark_return'] * 100:.2f}%",
            f"- 最大回撤: {metrics['max_drawdown'] * 100:.2f}%",
            f"- 夏普比率(年化): {metrics['sharpe']:.2f}",
            f"- 胜率: {metrics['win_rate'] * 100:.2f}%",
            f"- 开仓次数: {int(metrics['trades'])}",
        ]
    )
