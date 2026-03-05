import json
import os
from typing import Dict

from app.config import CONFIG


def load_portfolio() -> Dict:
    if os.path.exists(CONFIG.portfolio_file):
        with open(CONFIG.portfolio_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"holdings": []}


def save_portfolio(data: Dict) -> None:
    with open(CONFIG.portfolio_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
