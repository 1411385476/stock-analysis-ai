import sys
import unittest
from unittest.mock import patch

from app.cli import main


class CliExitCodeTestCase(unittest.TestCase):
    @patch("app.cli.setup_logging")
    @patch("app.cli.analyze_stock")
    def test_single_analysis_error_returns_nonzero(self, mock_analyze_stock, _mock_setup_logging) -> None:
        mock_analyze_stock.return_value = ("[E_DATA_FETCH] test error", None, None, None, None, None)
        argv = ["stock_analyzer.py", "600519", "--analysis-save"]
        with patch.object(sys, "argv", argv):
            code = main()
        self.assertEqual(code, 1)

    @patch("app.cli.setup_logging")
    @patch("app.cli.analyze_portfolio")
    def test_portfolio_error_returns_nonzero(self, mock_analyze_portfolio, _mock_setup_logging) -> None:
        mock_analyze_portfolio.return_value = "[E_DATA_FETCH] portfolio test error"
        argv = ["stock_analyzer.py", "--portfolio-symbols", "600519,000001", "--backtest"]
        with patch.object(sys, "argv", argv):
            code = main()
        self.assertEqual(code, 1)

    @patch("app.cli.setup_logging")
    @patch("app.cli.export_standard_snapshot")
    def test_standard_json_export_returns_zero(self, mock_export_standard_snapshot, _mock_setup_logging) -> None:
        mock_export_standard_snapshot.return_value = {
            "json_path": "/tmp/standard_snapshot.json",
            "latest_path": "/tmp/standard_snapshot.json",
        }
        argv = ["stock_analyzer.py", "--standard-json-export"]
        with patch.object(sys, "argv", argv):
            code = main()
        self.assertEqual(code, 0)
        mock_export_standard_snapshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
