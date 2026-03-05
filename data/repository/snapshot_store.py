import os
import time
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd

from app.config import CONFIG
from app.logging_config import get_logger
from data.providers.market_data import fetch_ashare_spot_snapshot

logger = get_logger(__name__)


def write_snapshot_batches(df: pd.DataFrame, batch_size: int) -> Tuple[str, list[str]]:
    os.makedirs(CONFIG.ashare_snapshot_dir, exist_ok=True)
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_file = os.path.join(CONFIG.ashare_snapshot_dir, f"ashare_snapshot_{run_tag}.csv")
    df.to_csv(run_file, index=False, encoding="utf-8-sig")
    df.to_csv(CONFIG.ashare_latest_file, index=False, encoding="utf-8-sig")

    batch_files: list[str] = []
    safe_batch_size = max(batch_size, 1)
    for batch_idx, start_idx in enumerate(range(0, len(df), safe_batch_size), start=1):
        batch_df = df.iloc[start_idx : start_idx + safe_batch_size].copy()
        batch_file = os.path.join(
            CONFIG.ashare_snapshot_dir,
            f"ashare_snapshot_{run_tag}_batch_{batch_idx:03d}.csv",
        )
        batch_df.to_csv(batch_file, index=False, encoding="utf-8-sig")
        batch_files.append(batch_file)
    return run_file, batch_files


def sync_ashare_snapshots(batch_size: int = 300, interval_seconds: int = 0, runs: int = 1) -> str:
    summaries: list[str] = []
    total_runs = max(runs, 1)

    for run_idx in range(total_runs):
        run_no = run_idx + 1
        try:
            snapshot_df = fetch_ashare_spot_snapshot()
        except Exception as exc:
            err = f"[{run_no}/{total_runs}] 失败: {exc}"
            logger.error(err)
            summaries.append(err)
            break

        if snapshot_df.empty:
            summaries.append(f"[{run_no}/{total_runs}] 结果为空，未写入文件。")
        else:
            run_file, batch_files = write_snapshot_batches(snapshot_df, batch_size=batch_size)
            summaries.append(
                f"[{run_no}/{total_runs}] 已拉取 {len(snapshot_df)} 条，分 {len(batch_files)} 批写入：{run_file}"
            )

        if interval_seconds > 0 and run_no < total_runs:
            summaries.append(f"等待 {interval_seconds} 秒后执行下一轮...")
            time.sleep(interval_seconds)

    return "\n".join(summaries)


def screen_ashare_snapshot(
    snapshot_file: str = CONFIG.ashare_latest_file,
    keyword: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_pct_change: Optional[float] = None,
    max_pct_change: Optional[float] = None,
    min_turnover: Optional[float] = None,
    max_turnover: Optional[float] = None,
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    sort_by: str = "pct_change",
    ascending: bool = False,
    top_n: int = 20,
) -> pd.DataFrame:
    if not os.path.exists(snapshot_file):
        logger.warning("筛选快照文件不存在: %s", snapshot_file)
        return pd.DataFrame()

    df = pd.read_csv(snapshot_file)
    if df.empty:
        return df

    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    if "name" in df.columns:
        df["name"] = df["name"].astype(str)

    for col in ["price", "pct_change", "turnover", "total_market_cap"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    mask = pd.Series(True, index=df.index)
    if keyword:
        keyword_text = str(keyword).strip()
        if keyword_text:
            symbol_match = df["symbol"].astype(str).str.contains(keyword_text, na=False)
            name_match = df["name"].astype(str).str.contains(keyword_text, na=False)
            mask &= symbol_match | name_match

    if min_price is not None and "price" in df.columns:
        mask &= df["price"] >= min_price
    if max_price is not None and "price" in df.columns:
        mask &= df["price"] <= max_price
    if min_pct_change is not None and "pct_change" in df.columns:
        mask &= df["pct_change"] >= min_pct_change
    if max_pct_change is not None and "pct_change" in df.columns:
        mask &= df["pct_change"] <= max_pct_change
    if min_turnover is not None and "turnover" in df.columns:
        mask &= df["turnover"] >= min_turnover
    if max_turnover is not None and "turnover" in df.columns:
        mask &= df["turnover"] <= max_turnover
    if min_market_cap is not None and "total_market_cap" in df.columns:
        mask &= df["total_market_cap"] >= min_market_cap
    if max_market_cap is not None and "total_market_cap" in df.columns:
        mask &= df["total_market_cap"] <= max_market_cap

    out = df.loc[mask].copy()
    if sort_by in out.columns:
        out = out.sort_values(sort_by, ascending=ascending, na_position="last")

    return out.head(max(top_n, 1))


def format_screen_report(df: pd.DataFrame, snapshot_file: str) -> str:
    if df.empty:
        return f"未筛选到符合条件的公司。快照文件: {snapshot_file}"

    cols = [
        "symbol",
        "name",
        "price",
        "pct_change",
        "turnover",
        "total_market_cap",
        "volume",
        "snapshot_time",
    ]
    available_cols = [c for c in cols if c in df.columns]
    table = df[available_cols].to_string(index=False)
    return f"筛选结果（{len(df)}条）:\n{table}"
