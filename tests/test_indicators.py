import unittest

import numpy as np
import pandas as pd

from factors.indicators import add_indicators
from strategy.signal_engine import strategy_signals


def _sample_ohlcv(rows: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    close = 100 + np.sin(np.linspace(0, 12, rows)) * 5 + np.linspace(0, 8, rows)
    open_ = close + np.random.default_rng(7).normal(0, 0.4, rows)
    high = np.maximum(open_, close) + 0.7
    low = np.minimum(open_, close) - 0.7
    volume = np.full(rows, 1_000_000.0)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


class IndicatorsTestCase(unittest.TestCase):
    def test_add_indicators_adds_expected_columns(self) -> None:
        df = _sample_ohlcv()
        out = add_indicators(df)
        expected = {"MA20", "MA60", "EMA12", "EMA26", "RSI14", "MACD", "MACD_SIGNAL", "BBL", "BBM", "BBU"}
        self.assertTrue(expected.issubset(out.columns))
        self.assertTrue(pd.notna(out.iloc[-1]["MA20"]))
        self.assertTrue(pd.notna(out.iloc[-1]["MA60"]))
        self.assertTrue(pd.notna(out.iloc[-1]["RSI14"]))

    def test_strategy_signals_returns_complete_fields(self) -> None:
        df = add_indicators(_sample_ohlcv())
        signals = strategy_signals(df)
        self.assertEqual(set(signals.keys()), {"trend", "macd_signal", "rsi_signal", "boll_signal", "summary"})
        self.assertTrue(all(isinstance(v, str) for v in signals.values()))


if __name__ == "__main__":
    unittest.main()
