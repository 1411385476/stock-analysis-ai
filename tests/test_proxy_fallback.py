import os
import types
import unittest
from unittest.mock import patch

import pandas as pd

from data.providers.market_data import (
    _call_akshare_with_proxy_fallback,
    _fetch_history_akshare,
    _history_provider_order,
    _is_akshare_history_temporarily_disabled,
    _mark_akshare_history_temporarily_disabled,
    _reset_akshare_history_circuit_for_tests,
    _temporary_disable_proxies,
    fetch_ashare_spot_snapshot,
)


class ProxyFallbackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_akshare_history_circuit_for_tests()

    def tearDown(self) -> None:
        _reset_akshare_history_circuit_for_tests()

    def test_temporary_disable_proxies_restores_environment(self) -> None:
        old_http = os.environ.get("HTTP_PROXY")
        old_no_proxy = os.environ.get("NO_PROXY")
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
        os.environ["NO_PROXY"] = "localhost"
        try:
            with _temporary_disable_proxies():
                self.assertNotIn("HTTP_PROXY", os.environ)
                self.assertEqual(os.environ.get("NO_PROXY"), "*")
        finally:
            if old_http is None:
                os.environ.pop("HTTP_PROXY", None)
            else:
                os.environ["HTTP_PROXY"] = old_http

            if old_no_proxy is None:
                os.environ.pop("NO_PROXY", None)
            else:
                os.environ["NO_PROXY"] = old_no_proxy

    def test_call_akshare_with_proxy_fallback_retries_once(self) -> None:
        attempts = {"n": 0}

        def flaky_call() -> pd.DataFrame:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("ProxyError: Unable to connect to proxy")
            return pd.DataFrame({"代码": ["000001"]})

        out = _call_akshare_with_proxy_fallback(flaky_call, "mock_api")
        self.assertEqual(attempts["n"], 2)
        self.assertFalse(out.empty)

    def test_call_akshare_with_proxy_fallback_no_retry_for_non_proxy_error(self) -> None:
        attempts = {"n": 0}

        def failing_call() -> pd.DataFrame:
            attempts["n"] += 1
            raise RuntimeError("connection timed out")

        with self.assertRaises(RuntimeError):
            _call_akshare_with_proxy_fallback(failing_call, "mock_api")
        self.assertEqual(attempts["n"], 1)

    def test_fetch_ashare_spot_snapshot_proxy_fallback_path(self) -> None:
        attempts = {"n": 0}

        def spot_em() -> pd.DataFrame:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("ProxyError: Unable to connect to proxy")
            return pd.DataFrame(
                {
                    "代码": ["1"],
                    "名称": ["平安银行"],
                    "最新价": [12.3],
                    "涨跌幅": [1.2],
                }
            )

        fake_ak = types.SimpleNamespace(stock_zh_a_spot_em=spot_em)
        with patch.dict("sys.modules", {"akshare": fake_ak}):
            out = fetch_ashare_spot_snapshot()

        self.assertEqual(attempts["n"], 2)
        self.assertIn("symbol", out.columns)
        self.assertEqual(out.iloc[0]["symbol"], "000001")
        self.assertIn("snapshot_time", out.columns)

    def test_fetch_ashare_spot_snapshot_fallback_to_sina(self) -> None:
        attempts = {"em": 0, "sina": 0}

        def em_spot() -> pd.DataFrame:
            attempts["em"] += 1
            raise RuntimeError("ConnectionError: eastmoney down")

        def sina_spot() -> pd.DataFrame:
            attempts["sina"] += 1
            return pd.DataFrame(
                {
                    "代码": ["600519"],
                    "名称": ["贵州茅台"],
                    "最新价": [1666.0],
                    "涨跌幅": [1.5],
                    "涨跌额": [24.0],
                    "成交量": [1000000.0],
                    "成交额": [1500000000.0],
                    "今开": [1640.0],
                    "最高": [1670.0],
                    "最低": [1638.0],
                    "昨收": [1642.0],
                }
            )

        fake_ak = types.SimpleNamespace(
            stock_zh_a_spot_em=em_spot,
            stock_zh_a_spot=sina_spot,
        )
        with patch.dict("sys.modules", {"akshare": fake_ak}):
            out = fetch_ashare_spot_snapshot()

        self.assertEqual(attempts["em"], 1)
        self.assertEqual(attempts["sina"], 1)
        self.assertEqual(out.iloc[0]["symbol"], "600519")
        self.assertIn("price", out.columns)

    def test_fetch_ashare_spot_snapshot_all_sources_failed(self) -> None:
        def em_spot() -> pd.DataFrame:
            raise RuntimeError("eastmoney timeout")

        def sina_spot() -> pd.DataFrame:
            raise RuntimeError("sina timeout")

        fake_ak = types.SimpleNamespace(
            stock_zh_a_spot_em=em_spot,
            stock_zh_a_spot=sina_spot,
        )
        with patch.dict("sys.modules", {"akshare": fake_ak}):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_ashare_spot_snapshot()

        self.assertIn("eastmoney", str(ctx.exception))
        self.assertIn("sina", str(ctx.exception))

    def test_history_provider_order_skips_akshare_when_circuit_open(self) -> None:
        _mark_akshare_history_temporarily_disabled("unit-test", cooldown_sec=60)
        order = _history_provider_order("600519")
        self.assertIn("yfinance", order)
        self.assertNotIn("akshare", order)

    def test_fetch_history_akshare_short_circuit_when_circuit_open(self) -> None:
        _mark_akshare_history_temporarily_disabled("unit-test", cooldown_sec=60)
        data, error = _fetch_history_akshare("600519", "2025-01-01", "2025-02-01")
        self.assertTrue(data.empty)
        self.assertIsNotNone(error)
        self.assertIn("熔断中", str(error))

    def test_fetch_history_akshare_marks_circuit_on_network_error(self) -> None:
        def hist(*_, **__) -> pd.DataFrame:
            raise ConnectionError("Remote end closed connection without response")

        fake_ak = types.SimpleNamespace(stock_zh_a_hist=hist)
        with patch.dict("sys.modules", {"akshare": fake_ak}):
            data, error = _fetch_history_akshare("600519", "2025-01-01", "2025-02-01")

        self.assertTrue(data.empty)
        self.assertIn("akshare请求异常", str(error))
        self.assertTrue(_is_akshare_history_temporarily_disabled())


if __name__ == "__main__":
    unittest.main()
