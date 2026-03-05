import os
from dataclasses import dataclass
from typing import Dict


def _expand(path: str) -> str:
    return os.path.expanduser(path)


@dataclass(frozen=True)
class AppConfig:
    base_dir: str = _expand(os.getenv("OPENCLAW_FINANCE_HOME", "~/openclaw-finance"))
    portfolio_file: str = _expand(os.getenv("PORTFOLIO_FILE", "~/openclaw-finance/portfolio.json"))
    chart_dir: str = _expand(os.getenv("CHART_DIR", "~/openclaw-finance/charts"))
    data_dir: str = _expand(os.getenv("DATA_DIR", "~/openclaw-finance/data"))
    backtest_output_dir: str = _expand(os.getenv("BACKTEST_OUTPUT_DIR", "~/openclaw-finance/data/backtests"))
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "http://127.0.0.1:11434/v1")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen2.5:32b")
    qwen_api_key: str = os.getenv("QWEN_API_KEY", "EMPTY")
    qwen_timeout: int = int(os.getenv("QWEN_TIMEOUT", "120"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    score_weight_trend: float = float(os.getenv("SCORE_WEIGHT_TREND", "0.35"))
    score_weight_volume_price: float = float(os.getenv("SCORE_WEIGHT_VOLUME_PRICE", "0.30"))
    score_weight_volatility: float = float(os.getenv("SCORE_WEIGHT_VOLATILITY", "0.15"))
    score_weight_turnover: float = float(os.getenv("SCORE_WEIGHT_TURNOVER", "0.20"))

    @property
    def ashare_snapshot_dir(self) -> str:
        return os.path.join(self.data_dir, "ashare_snapshots")

    @property
    def ashare_latest_file(self) -> str:
        return os.path.join(self.ashare_snapshot_dir, "ashare_latest.csv")

    @property
    def score_weights(self) -> Dict[str, float]:
        raw = {
            "trend": max(self.score_weight_trend, 0.0),
            "volume_price": max(self.score_weight_volume_price, 0.0),
            "volatility": max(self.score_weight_volatility, 0.0),
            "turnover": max(self.score_weight_turnover, 0.0),
        }
        total = sum(raw.values())
        if total <= 0:
            # Safe fallback when misconfigured.
            return {"trend": 0.35, "volume_price": 0.30, "volatility": 0.15, "turnover": 0.20}
        return {k: v / total for k, v in raw.items()}


CONFIG = AppConfig()
