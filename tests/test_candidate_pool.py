import os
import tempfile
import unittest

import pandas as pd

from data.providers.market_data import normalize_universe
from data.repository.snapshot_store import (
    SCORE_COLUMNS,
    export_candidate_pool,
    screen_ashare_snapshot,
)


def _sample_snapshot_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "000001",
                "name": "平安银行",
                "price": 12.3,
                "pct_change": 1.6,
                "turnover": 3.2,
                "total_market_cap": 2.4e11,
                "volume": 12_000_000,
                "amount": 1.4e9,
                "volume_ratio": 1.3,
                "amplitude": 2.1,
                "pct_change_60d": 9.2,
                "snapshot_time": "2026-03-05 18:00:00",
            },
            {
                "symbol": "000002",
                "name": "万科A",
                "price": 8.4,
                "pct_change": -0.6,
                "turnover": 1.1,
                "total_market_cap": 9.1e10,
                "volume": 9_000_000,
                "amount": 7.9e8,
                "volume_ratio": 0.7,
                "amplitude": 1.5,
                "pct_change_60d": -5.0,
                "snapshot_time": "2026-03-05 18:00:00",
            },
            {
                "symbol": "600519",
                "name": "贵州茅台",
                "price": 1666.0,
                "pct_change": 2.2,
                "turnover": 0.5,
                "total_market_cap": 2.0e12,
                "volume": 800_000,
                "amount": 1.3e9,
                "volume_ratio": 1.6,
                "amplitude": 1.0,
                "pct_change_60d": 15.0,
                "snapshot_time": "2026-03-05 18:00:00",
            },
            {
                "symbol": "600000",
                "name": "浦发银行",
                "price": 7.1,
                "pct_change": 0.1,
                "turnover": 0.7,
                "total_market_cap": 8.5e10,
                "volume": 7_000_000,
                "amount": 5.0e8,
                "volume_ratio": 0.9,
                "amplitude": 0.8,
                "pct_change_60d": 1.2,
                "snapshot_time": "2026-03-05 18:00:00",
            },
        ]
    )


class CandidatePoolTestCase(unittest.TestCase):
    def test_normalize_universe_aliases(self) -> None:
        self.assertEqual(normalize_universe("沪深300"), "hs300")
        self.assertEqual(normalize_universe("000905"), "zz500")
        self.assertEqual(normalize_universe("all"), "all")

    def test_screen_snapshot_with_universe_and_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = os.path.join(tmpdir, "snapshot.csv")
            _sample_snapshot_df().to_csv(snapshot_file, index=False, encoding="utf-8-sig")

            out = screen_ashare_snapshot(
                snapshot_file=snapshot_file,
                universe="hs300",
                universe_symbols={"000001", "600519"},
                sort_by="score_total",
                top_n=10,
            )

            self.assertEqual(set(out["symbol"].tolist()), {"000001", "600519"})
            self.assertTrue(set(SCORE_COLUMNS).issubset(set(out.columns)))
            self.assertGreaterEqual(out.iloc[0]["score_total"], out.iloc[-1]["score_total"])
            self.assertEqual(int(out["score_rank"].min()), 1)

    def test_export_candidate_pool_writes_csv_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = os.path.join(tmpdir, "snapshot.csv")
            _sample_snapshot_df().to_csv(snapshot_file, index=False, encoding="utf-8-sig")
            screened = screen_ashare_snapshot(
                snapshot_file=snapshot_file,
                universe="all",
                sort_by="score_total",
                top_n=3,
            )

            csv_path, md_path = export_candidate_pool(
                screened,
                universe="hs300",
                output_dir=tmpdir,
            )

            self.assertIsNotNone(csv_path)
            self.assertIsNotNone(md_path)
            self.assertTrue(os.path.exists(str(csv_path)))
            self.assertTrue(os.path.exists(str(md_path)))

            with open(str(md_path), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Candidate Pool (hs300)", content)
            self.assertIn("score_total", content)


if __name__ == "__main__":
    unittest.main()
