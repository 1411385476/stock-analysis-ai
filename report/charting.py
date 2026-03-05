import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

from app.config import CONFIG


def generate_chart(df: pd.DataFrame, symbol: str) -> str:
    os.makedirs(CONFIG.chart_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    chart_path = os.path.join(CONFIG.chart_dir, f"{symbol}_{ts}.png")

    plt.figure(figsize=(13, 7))
    plt.plot(df.index, df["Close"], label="Close", linewidth=1.8)

    if "MA20" in df.columns:
        plt.plot(df.index, df["MA20"], label="MA20", alpha=0.9)
    if "MA60" in df.columns:
        plt.plot(df.index, df["MA60"], label="MA60", alpha=0.9)
    if all(c in df.columns for c in ["BBL", "BBU"]):
        plt.fill_between(df.index, df["BBL"], df["BBU"], alpha=0.12, label="Bollinger Band")

    plt.title(f"{symbol} Daily Price + Indicators")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return chart_path
