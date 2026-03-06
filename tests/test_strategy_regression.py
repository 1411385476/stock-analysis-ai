import copy
import unittest

from report.strategy_regression import (
    SNAPSHOT_KEYS,
    build_regression_snapshot,
    compare_regression_snapshots,
)


class StrategyRegressionTestCase(unittest.TestCase):
    def test_build_regression_snapshot_contains_expected_metrics(self) -> None:
        snapshot = build_regression_snapshot()
        self.assertIn("case", snapshot)
        self.assertIn("metrics", snapshot)
        metrics = snapshot["metrics"]
        self.assertTrue(set(SNAPSHOT_KEYS).issubset(metrics.keys()))
        self.assertGreater(float(metrics.get("trades", 0.0)), 0.0)
        self.assertGreater(float(metrics.get("rebalance_event_count", 0.0)), 0.0)

    def test_compare_regression_snapshots_detects_drift(self) -> None:
        baseline = build_regression_snapshot()
        current = copy.deepcopy(baseline)
        current["metrics"]["total_return"] = float(current["metrics"]["total_return"]) + 0.10
        drifts = compare_regression_snapshots(current=current, baseline=baseline)
        self.assertTrue(drifts)
        drift_metrics = {str(item.get("metric", "")) for item in drifts}
        self.assertIn("total_return", drift_metrics)

    def test_compare_regression_snapshots_passes_when_same(self) -> None:
        baseline = build_regression_snapshot()
        current = copy.deepcopy(baseline)
        drifts = compare_regression_snapshots(current=current, baseline=baseline)
        self.assertEqual(drifts, [])


if __name__ == "__main__":
    unittest.main()
