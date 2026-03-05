import os
from dataclasses import dataclass


def _expand(path: str) -> str:
    return os.path.expanduser(path)


@dataclass(frozen=True)
class AppConfig:
    base_dir: str = _expand(os.getenv("OPENCLAW_FINANCE_HOME", "~/openclaw-finance"))
    portfolio_file: str = _expand(os.getenv("PORTFOLIO_FILE", "~/openclaw-finance/portfolio.json"))
    chart_dir: str = _expand(os.getenv("CHART_DIR", "~/openclaw-finance/charts"))
    data_dir: str = _expand(os.getenv("DATA_DIR", "~/openclaw-finance/data"))
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "http://127.0.0.1:11434/v1")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen2.5:32b")
    qwen_api_key: str = os.getenv("QWEN_API_KEY", "EMPTY")
    qwen_timeout: int = int(os.getenv("QWEN_TIMEOUT", "120"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def ashare_snapshot_dir(self) -> str:
        return os.path.join(self.data_dir, "ashare_snapshots")

    @property
    def ashare_latest_file(self) -> str:
        return os.path.join(self.ashare_snapshot_dir, "ashare_latest.csv")


CONFIG = AppConfig()
