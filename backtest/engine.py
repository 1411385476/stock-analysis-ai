from typing import Dict, Optional

import numpy as np
import pandas as pd

REQUIRED_SIGNAL_COLS = ["Close", "MA20", "MA60", "MACD", "MACD_SIGNAL", "RSI14"]


def _confirm_signal(signal: pd.Series, confirm_days: int) -> pd.Series:
    days = max(int(confirm_days), 1)
    base = signal.fillna(False).astype(bool)
    if days == 1:
        return base
    return base.rolling(days, min_periods=days).sum().eq(days)


def _sanitize_backtest_params(
    fee_rate: float,
    slippage_bps: float,
    min_hold_days: int,
    signal_confirm_days: int,
    max_positions: int,
) -> tuple[float, float, int, int, int]:
    return (
        max(float(fee_rate), 0.0),
        max(float(slippage_bps), 0.0),
        max(int(min_hold_days), 1),
        max(int(signal_confirm_days), 1),
        max(int(max_positions), 1),
    )


def _sanitize_risk_exit_params(
    stop_loss_pct: float,
    take_profit_pct: float,
) -> tuple[float, float]:
    return (
        max(float(stop_loss_pct), 0.0),
        max(float(take_profit_pct), 0.0),
    )


def _sanitize_portfolio_risk_params(
    drawdown_circuit_pct: float,
    circuit_cooldown_days: int,
    max_industry_weight: float,
    max_single_weight: float,
) -> tuple[float, int, float, float]:
    safe_single_weight = min(max(float(max_single_weight), 0.0), 1.0)
    if safe_single_weight <= 0:
        safe_single_weight = 1.0
    return (
        max(float(drawdown_circuit_pct), 0.0),
        max(int(circuit_cooldown_days), 0),
        min(max(float(max_industry_weight), 0.0), 1.0),
        safe_single_weight,
    )


def _signal_columns(data: pd.DataFrame, signal_confirm_days: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    buy_raw = (
        (data["MA20"] > data["MA60"])
        & (data["MACD"] > data["MACD_SIGNAL"])
        & (data["RSI14"] < 70)
    )
    sell_raw = (
        (data["MA20"] < data["MA60"])
        | (data["MACD"] < data["MACD_SIGNAL"])
        | (data["RSI14"] > 75)
    )
    buy_signal = _confirm_signal(buy_raw, signal_confirm_days)
    sell_signal = _confirm_signal(sell_raw, signal_confirm_days)
    # Used for ranking entry candidates in portfolio mode.
    strength = (
        (data["MA20"] - data["MA60"]).fillna(0.0)
        + (data["MACD"] - data["MACD_SIGNAL"]).fillna(0.0)
        - ((data["RSI14"] - 50.0).abs() / 100.0).fillna(0.0)
    )
    return buy_signal, sell_signal, strength


def _worst_rolling_drawdown(equity: pd.Series, window: int) -> float:
    if len(equity) < 2:
        return 0.0
    safe_window = max(int(window), 2)
    rolling_peak = equity.rolling(window=safe_window, min_periods=2).max()
    dd = equity / rolling_peak - 1.0
    value = dd.min()
    if pd.isna(value):
        return 0.0
    return float(value)


def _yearly_returns(strategy_ret: pd.Series) -> dict[int, float]:
    if strategy_ret.empty:
        return {}
    if not isinstance(strategy_ret.index, pd.DatetimeIndex):
        return {}
    yearly = (1.0 + strategy_ret).groupby(strategy_ret.index.year).prod() - 1.0
    return {int(year): float(ret) for year, ret in yearly.items()}


def _build_metrics(
    strategy_ret: pd.Series,
    benchmark_ret: pd.Series,
    trades: float,
    wins: int,
    closed: int,
    samples: int,
    fee_rate: float,
    slippage_bps: float,
    min_hold_days: int,
    signal_confirm_days: int,
    max_positions: int,
    avg_active_positions: float,
    max_active_positions: float,
    symbols: int,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    risk_exits: float = 0.0,
    drawdown_circuit_pct: float = 0.0,
    circuit_cooldown_days: float = 0.0,
    drawdown_circuit_triggers: float = 0.0,
    circuit_active_days: float = 0.0,
    max_industry_weight_limit: float = 1.0,
    max_industry_weight_used: float = 0.0,
    industry_blocked_entries: float = 0.0,
    max_single_weight_limit: float = 1.0,
    max_single_weight_used: float = 0.0,
    avg_capital_utilization: float = 0.0,
) -> Dict[str, float]:
    equity = (1.0 + strategy_ret).cumprod()
    benchmark_equity = (1.0 + benchmark_ret).cumprod()
    total_return = equity.iloc[-1] - 1.0
    benchmark_total = benchmark_equity.iloc[-1] - 1.0

    idx = strategy_ret.index
    if len(idx) > 1:
        years = max((idx[-1] - idx[0]).days / 365.0, 1 / 365.0)
    else:
        years = 1 / 365.0
    annual_return = (1.0 + total_return) ** (1 / years) - 1.0

    rolling_max = equity.cummax()
    drawdown = equity / rolling_max - 1.0
    max_drawdown = drawdown.min()
    if max_drawdown < 0:
        calmar = annual_return / abs(max_drawdown)
    else:
        calmar = 0.0
    rolling_dd_63 = _worst_rolling_drawdown(equity, 63)
    rolling_dd_126 = _worst_rolling_drawdown(equity, 126)
    rolling_dd_252 = _worst_rolling_drawdown(equity, 252)
    yearly = _yearly_returns(strategy_ret)

    if strategy_ret.std(ddof=0) > 0:
        sharpe = (strategy_ret.mean() / strategy_ret.std(ddof=0)) * np.sqrt(252)
    else:
        sharpe = 0.0

    win_rate = (wins / closed) if closed > 0 else 0.0
    metrics: Dict[str, float] = {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "max_drawdown": float(max_drawdown),
        "calmar": float(calmar),
        "sharpe": float(sharpe),
        "win_rate": float(win_rate),
        "trades": float(trades),
        "benchmark_return": float(benchmark_total),
        "samples": float(samples),
        "fee_rate": float(fee_rate),
        "slippage_bps": float(slippage_bps),
        "min_hold_days": float(min_hold_days),
        "signal_confirm_days": float(signal_confirm_days),
        "max_positions": float(max_positions),
        "avg_active_positions": float(avg_active_positions),
        "max_active_positions": float(max_active_positions),
        "avg_capital_utilization": float(avg_capital_utilization),
        "symbols": float(symbols),
        "stop_loss_pct": float(stop_loss_pct),
        "take_profit_pct": float(take_profit_pct),
        "risk_exits": float(risk_exits),
        "drawdown_circuit_pct": float(drawdown_circuit_pct),
        "circuit_cooldown_days": float(circuit_cooldown_days),
        "drawdown_circuit_triggers": float(drawdown_circuit_triggers),
        "circuit_active_days": float(circuit_active_days),
        "max_industry_weight_limit": float(max_industry_weight_limit),
        "max_industry_weight_used": float(max_industry_weight_used),
        "industry_blocked_entries": float(industry_blocked_entries),
        "max_single_weight_limit": float(max_single_weight_limit),
        "max_single_weight_used": float(max_single_weight_used),
        "rolling_drawdown_63": float(rolling_dd_63),
        "rolling_drawdown_126": float(rolling_dd_126),
        "rolling_drawdown_252": float(rolling_dd_252),
        "year_count": float(len(yearly)),
    }
    for year, ret in yearly.items():
        metrics[f"year_return_{year}"] = float(ret)
    return metrics


def run_backtest(
    df: pd.DataFrame,
    fee_rate: float = 0.001,
    slippage_bps: float = 0.0,
    min_hold_days: int = 1,
    signal_confirm_days: int = 1,
    max_positions: int = 1,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> Dict[str, float]:
    """
    Single-symbol long-only template.
    - Buy: MA20 > MA60 and MACD > MACD_SIGNAL and RSI14 < 70
    - Sell: MA20 < MA60 or MACD < MACD_SIGNAL or RSI14 > 75
    """
    data = df.copy()
    if any(col not in data.columns for col in REQUIRED_SIGNAL_COLS):
        return {}

    data = data.dropna(subset=REQUIRED_SIGNAL_COLS)
    if len(data) < 30:
        return {}

    fee_rate, slippage_bps, min_hold_days, signal_confirm_days, max_positions = _sanitize_backtest_params(
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        min_hold_days=min_hold_days,
        signal_confirm_days=signal_confirm_days,
        max_positions=max_positions,
    )
    stop_loss_pct, take_profit_pct = _sanitize_risk_exit_params(
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )

    buy_signal, sell_signal, _ = _signal_columns(data, signal_confirm_days)
    position = np.zeros(len(data), dtype=float)
    in_position = False
    hold_days = 0
    trades = 0
    entry_price = None
    risk_exits = 0

    for i in range(len(data)):
        close_price = float(data["Close"].iloc[i])
        if not in_position and bool(buy_signal.iloc[i]):
            in_position = True
            position[i] = 1.0
            hold_days = 1
            trades += 1
            entry_price = close_price
            continue

        risk_exit = False
        if in_position and entry_price is not None:
            if stop_loss_pct > 0 and close_price <= float(entry_price) * (1.0 - stop_loss_pct):
                risk_exit = True
            if take_profit_pct > 0 and close_price >= float(entry_price) * (1.0 + take_profit_pct):
                risk_exit = True

        if in_position and (risk_exit or (hold_days >= min_hold_days and bool(sell_signal.iloc[i]))):
            in_position = False
            position[i] = 0.0
            hold_days = 0
            entry_price = None
            if risk_exit:
                risk_exits += 1
            continue

        position[i] = 1.0 if in_position else 0.0
        if in_position:
            hold_days += 1

    position_series = pd.Series(position, index=data.index).shift(1).fillna(0.0)
    ret = data["Close"].pct_change().fillna(0.0)
    trade_change = position_series.diff().abs().fillna(position_series.iloc[0])
    cost_rate = fee_rate + (slippage_bps / 10000.0)
    strategy_ret = position_series * ret - trade_change * cost_rate
    benchmark_ret = ret

    wins = 0
    closed = 0
    last_entry_price = None
    last_position = 0.0
    for _, row in data.assign(position=position_series).iterrows():
        if last_position == 0.0 and row["position"] == 1.0:
            last_entry_price = row["Close"]
        if last_position == 1.0 and row["position"] == 0.0 and last_entry_price is not None:
            closed += 1
            if row["Close"] > last_entry_price:
                wins += 1
            last_entry_price = None
        last_position = row["position"]

    return _build_metrics(
        strategy_ret=strategy_ret,
        benchmark_ret=benchmark_ret,
        trades=float(trades),
        wins=wins,
        closed=closed,
        samples=len(data),
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        min_hold_days=min_hold_days,
        signal_confirm_days=signal_confirm_days,
        max_positions=max_positions,
        avg_active_positions=float(position_series.mean()),
        max_active_positions=float(position_series.max()),
        symbols=1,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        risk_exits=float(risk_exits),
    )


def run_portfolio_backtest(
    symbol_data: dict[str, pd.DataFrame],
    fee_rate: float = 0.001,
    slippage_bps: float = 0.0,
    min_hold_days: int = 1,
    signal_confirm_days: int = 1,
    max_positions: int = 5,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    industry_map: Optional[dict[str, str]] = None,
    max_industry_weight: float = 1.0,
    max_single_weight: float = 1.0,
    drawdown_circuit_pct: float = 0.0,
    circuit_cooldown_days: int = 0,
) -> Dict[str, float]:
    """
    Multi-symbol portfolio backtest with equal-weight active holdings.
    Entry ranking is based on signal strength; holdings count is capped by max_positions.
    """
    if not symbol_data:
        return {}

    fee_rate, slippage_bps, min_hold_days, signal_confirm_days, max_positions = _sanitize_backtest_params(
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        min_hold_days=min_hold_days,
        signal_confirm_days=signal_confirm_days,
        max_positions=max_positions,
    )
    stop_loss_pct, take_profit_pct = _sanitize_risk_exit_params(
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    drawdown_circuit_pct, circuit_cooldown_days, max_industry_weight, max_single_weight = _sanitize_portfolio_risk_params(
        drawdown_circuit_pct=drawdown_circuit_pct,
        circuit_cooldown_days=circuit_cooldown_days,
        max_industry_weight=max_industry_weight,
        max_single_weight=max_single_weight,
    )

    prepared: dict[str, pd.DataFrame] = {}
    for symbol, raw in symbol_data.items():
        if raw is None or raw.empty or any(col not in raw.columns for col in REQUIRED_SIGNAL_COLS):
            continue
        data = raw.copy().dropna(subset=REQUIRED_SIGNAL_COLS)
        if len(data) < 30:
            continue
        buy_signal, sell_signal, strength = _signal_columns(data, signal_confirm_days)
        prepared[symbol] = pd.DataFrame(
            {
                "Close": data["Close"],
                "buy_signal": buy_signal,
                "sell_signal": sell_signal,
                "strength": strength,
            },
            index=data.index,
        )

    if not prepared:
        return {}

    common_index = None
    for frame in prepared.values():
        idx = frame.index
        common_index = idx if common_index is None else common_index.intersection(idx)
    if common_index is None:
        return {}
    common_index = common_index.sort_values()
    if len(common_index) < 30:
        return {}

    symbols = sorted(prepared.keys())
    close_df = pd.DataFrame({s: prepared[s].loc[common_index, "Close"] for s in symbols})
    buy_df = pd.DataFrame({s: prepared[s].loc[common_index, "buy_signal"] for s in symbols})
    sell_df = pd.DataFrame({s: prepared[s].loc[common_index, "sell_signal"] for s in symbols})
    strength_df = pd.DataFrame({s: prepared[s].loc[common_index, "strength"] for s in symbols})

    holdings: set[str] = set()
    hold_days = {s: 0 for s in symbols}
    entry_price: dict[str, float] = {}
    trades = 0
    wins = 0
    closed = 0
    risk_exits = 0
    cost_rate = fee_rate + (slippage_bps / 10000.0)
    ret_df = close_df.pct_change().fillna(0.0)
    benchmark_ret = ret_df.mean(axis=1)
    industry_by_symbol = {s: str((industry_map or {}).get(s, s)) for s in symbols}
    capital_slots = max_positions
    if max_single_weight < 1.0:
        required_slots = int(np.ceil(1.0 / max_single_weight))
        capital_slots = max(capital_slots, required_slots)
    weight_per_position = 1.0 / float(capital_slots)
    max_per_industry = int(np.floor(capital_slots * max_industry_weight + 1e-9))
    if max_industry_weight >= 1.0:
        max_per_industry = capital_slots

    prev_position = {s: 0.0 for s in symbols}
    strategy_ret_values: list[float] = []
    active_positions_values: list[float] = []
    capital_util_values: list[float] = []
    max_active_positions_seen = 0.0
    max_industry_weight_used = 0.0
    max_single_weight_used = 0.0
    industry_blocked_entries = 0
    drawdown_circuit_triggers = 0
    circuit_active_days = 0
    cooldown_remaining = 0
    equity = 1.0
    peak = 1.0

    for ts in common_index:
        if cooldown_remaining > 0:
            if holdings:
                for s in list(holdings):
                    exit_price = float(close_df.at[ts, s])
                    if s in entry_price:
                        closed += 1
                        if exit_price > entry_price[s]:
                            wins += 1
                        entry_price.pop(s, None)
                    holdings.remove(s)
                    hold_days[s] = 0
                risk_exits += 1
            cooldown_remaining -= 1
            circuit_active_days += 1
        else:
            for s in list(holdings):
                hold_days[s] += 1

            for s in list(holdings):
                exit_price = float(close_df.at[ts, s])
                risk_exit = False
                if s in entry_price:
                    entry = float(entry_price[s])
                    if stop_loss_pct > 0 and exit_price <= entry * (1.0 - stop_loss_pct):
                        risk_exit = True
                    if take_profit_pct > 0 and exit_price >= entry * (1.0 + take_profit_pct):
                        risk_exit = True

                should_exit = risk_exit or (hold_days[s] >= min_hold_days and bool(sell_df.at[ts, s]))
                if not should_exit:
                    continue

                if s in entry_price:
                    closed += 1
                    if exit_price > entry_price[s]:
                        wins += 1
                    entry_price.pop(s, None)
                holdings.remove(s)
                hold_days[s] = 0
                if risk_exit:
                    risk_exits += 1

            slots = max_positions - len(holdings)
            if slots > 0:
                candidates = [s for s in symbols if s not in holdings and bool(buy_df.at[ts, s])]
                if candidates:
                    ranked = sorted(candidates, key=lambda s: (float(strength_df.at[ts, s]), s), reverse=True)
                    for s in ranked:
                        if slots <= 0:
                            break
                        target_industry = industry_by_symbol.get(s, s)
                        same_industry_count = 0
                        for h in holdings:
                            if industry_by_symbol.get(h, h) == target_industry:
                                same_industry_count += 1
                        if same_industry_count + 1 > max_per_industry:
                            industry_blocked_entries += 1
                            continue
                        holdings.add(s)
                        hold_days[s] = 1
                        entry_price[s] = float(close_df.at[ts, s])
                        trades += 1
                        slots -= 1

        current_position = {s: (weight_per_position if s in holdings else 0.0) for s in symbols}
        active_prev = float(sum(1 for s in symbols if prev_position[s] > 0))
        invested_prev = float(sum(prev_position.values()))
        max_active_positions_seen = max(max_active_positions_seen, active_prev)

        gross = 0.0
        for s in symbols:
            gross += prev_position[s] * float(ret_df.at[ts, s])
        portfolio_ret = gross

        turnover = 0.0
        for s in symbols:
            turnover += abs(current_position[s] - prev_position[s])
        strategy_today = portfolio_ret - turnover * cost_rate
        strategy_ret_values.append(strategy_today)
        active_positions_values.append(active_prev)
        capital_util_values.append(invested_prev)

        industry_counts: dict[str, int] = {}
        for s in holdings:
            industry = industry_by_symbol.get(s, s)
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if industry_counts:
            day_max = max(industry_counts.values()) * weight_per_position
            max_industry_weight_used = max(max_industry_weight_used, day_max)
        if holdings:
            max_single_weight_used = max(max_single_weight_used, weight_per_position)

        equity *= (1.0 + strategy_today)
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        if (
            drawdown_circuit_pct > 0
            and circuit_cooldown_days > 0
            and cooldown_remaining <= 0
            and drawdown <= -drawdown_circuit_pct
        ):
            drawdown_circuit_triggers += 1
            cooldown_remaining = circuit_cooldown_days

        prev_position = current_position

    strategy_ret = pd.Series(strategy_ret_values, index=common_index)
    active_positions = pd.Series(active_positions_values, index=common_index)

    return _build_metrics(
        strategy_ret=strategy_ret,
        benchmark_ret=benchmark_ret,
        trades=float(trades),
        wins=wins,
        closed=closed,
        samples=len(common_index),
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        min_hold_days=min_hold_days,
        signal_confirm_days=signal_confirm_days,
        max_positions=max_positions,
        avg_active_positions=float(active_positions.mean()),
        max_active_positions=float(max_active_positions_seen),
        avg_capital_utilization=float(pd.Series(capital_util_values, index=common_index).mean()),
        symbols=len(symbols),
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        risk_exits=float(risk_exits),
        drawdown_circuit_pct=drawdown_circuit_pct,
        circuit_cooldown_days=float(circuit_cooldown_days),
        drawdown_circuit_triggers=float(drawdown_circuit_triggers),
        circuit_active_days=float(circuit_active_days),
        max_industry_weight_limit=max_industry_weight,
        max_industry_weight_used=float(max_industry_weight_used),
        industry_blocked_entries=float(industry_blocked_entries),
        max_single_weight_limit=max_single_weight,
        max_single_weight_used=float(max_single_weight_used),
    )


def format_backtest_report(metrics: Dict[str, float]) -> str:
    if not metrics:
        return "回测结果: 数据不足或指标缺失，无法回测。"

    year_items = sorted(
        [
            (int(k.split("_")[-1]), float(v))
            for k, v in metrics.items()
            if k.startswith("year_return_")
        ],
        key=lambda x: x[0],
    )
    if year_items:
        yearly_text = ", ".join([f"{year}: {ret * 100:.2f}%" for year, ret in year_items])
    else:
        yearly_text = "N/A"

    return "\n".join(
        [
            "回测结果:",
            f"- 区间样本: {int(metrics['samples'])} 交易日",
            f"- 策略总收益: {metrics['total_return'] * 100:.2f}%",
            f"- 年化收益: {metrics['annual_return'] * 100:.2f}%",
            f"- 基准收益(买入持有): {metrics['benchmark_return'] * 100:.2f}%",
            f"- 最大回撤: {metrics['max_drawdown'] * 100:.2f}%",
            f"- 滚动回撤(3M/6M/12M): {metrics.get('rolling_drawdown_63', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_126', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_252', 0.0) * 100:.2f}%",
            f"- 夏普比率(年化): {metrics['sharpe']:.2f}",
            f"- 卡玛比率(年化): {metrics.get('calmar', 0.0):.2f}",
            f"- 年度分解: {yearly_text}",
            f"- 胜率: {metrics['win_rate'] * 100:.2f}%",
            f"- 开仓次数: {int(metrics['trades'])}",
            f"- 成本模型: 手续费={metrics.get('fee_rate', 0.0) * 100:.2f}% / 滑点={metrics.get('slippage_bps', 0.0):.1f}bps",
            f"- 交易约束: 最小持仓={int(metrics.get('min_hold_days', 1))}天 / 信号确认={int(metrics.get('signal_confirm_days', 1))}天",
            f"- 风控规则: 止损={metrics.get('stop_loss_pct', 0.0) * 100:.2f}% / 止盈={metrics.get('take_profit_pct', 0.0) * 100:.2f}% / 风控平仓={int(metrics.get('risk_exits', 0))}",
            f"- 回撤熔断: 阈值={metrics.get('drawdown_circuit_pct', 0.0) * 100:.2f}% / 冷却={int(metrics.get('circuit_cooldown_days', 0))}天 / 触发={int(metrics.get('drawdown_circuit_triggers', 0))}",
            f"- 行业约束: 上限={metrics.get('max_industry_weight_limit', 1.0) * 100:.2f}% / 实际峰值={metrics.get('max_industry_weight_used', 0.0) * 100:.2f}% / 拒绝开仓={int(metrics.get('industry_blocked_entries', 0))}",
        ]
    )


def format_portfolio_backtest_report(metrics: Dict[str, float]) -> str:
    if not metrics:
        return "组合回测结果: 数据不足或指标缺失，无法回测。"

    year_items = sorted(
        [
            (int(k.split("_")[-1]), float(v))
            for k, v in metrics.items()
            if k.startswith("year_return_")
        ],
        key=lambda x: x[0],
    )
    if year_items:
        yearly_text = ", ".join([f"{year}: {ret * 100:.2f}%" for year, ret in year_items])
    else:
        yearly_text = "N/A"

    return "\n".join(
        [
            "组合回测结果:",
            f"- 标的数量: {int(metrics.get('symbols', 0))}",
            f"- 区间样本: {int(metrics['samples'])} 交易日",
            f"- 策略总收益: {metrics['total_return'] * 100:.2f}%",
            f"- 年化收益: {metrics['annual_return'] * 100:.2f}%",
            f"- 基准收益(等权买入持有): {metrics['benchmark_return'] * 100:.2f}%",
            f"- 最大回撤: {metrics['max_drawdown'] * 100:.2f}%",
            f"- 滚动回撤(3M/6M/12M): {metrics.get('rolling_drawdown_63', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_126', 0.0) * 100:.2f}% / {metrics.get('rolling_drawdown_252', 0.0) * 100:.2f}%",
            f"- 夏普比率(年化): {metrics['sharpe']:.2f}",
            f"- 卡玛比率(年化): {metrics.get('calmar', 0.0):.2f}",
            f"- 年度分解: {yearly_text}",
            f"- 胜率: {metrics['win_rate'] * 100:.2f}%",
            f"- 开仓次数: {int(metrics['trades'])}",
            f"- 平均持仓数: {metrics.get('avg_active_positions', 0.0):.2f}",
            f"- 最大持仓数: {metrics.get('max_active_positions', 0.0):.0f} / 限制 {int(metrics.get('max_positions', 1))}",
            f"- 资金利用率: 平均已投资资金={metrics.get('avg_capital_utilization', 0.0) * 100:.2f}%",
            f"- 单票约束: 上限={metrics.get('max_single_weight_limit', 1.0) * 100:.2f}% / 实际峰值={metrics.get('max_single_weight_used', 0.0) * 100:.2f}%",
            f"- 成本模型: 手续费={metrics.get('fee_rate', 0.0) * 100:.2f}% / 滑点={metrics.get('slippage_bps', 0.0):.1f}bps",
            f"- 交易约束: 最小持仓={int(metrics.get('min_hold_days', 1))}天 / 信号确认={int(metrics.get('signal_confirm_days', 1))}天",
            f"- 风控规则: 止损={metrics.get('stop_loss_pct', 0.0) * 100:.2f}% / 止盈={metrics.get('take_profit_pct', 0.0) * 100:.2f}% / 风控平仓={int(metrics.get('risk_exits', 0))}",
            f"- 回撤熔断: 阈值={metrics.get('drawdown_circuit_pct', 0.0) * 100:.2f}% / 冷却={int(metrics.get('circuit_cooldown_days', 0))}天 / 触发={int(metrics.get('drawdown_circuit_triggers', 0))}",
            f"- 行业约束: 上限={metrics.get('max_industry_weight_limit', 1.0) * 100:.2f}% / 实际峰值={metrics.get('max_industry_weight_used', 0.0) * 100:.2f}% / 拒绝开仓={int(metrics.get('industry_blocked_entries', 0))}",
        ]
    )
