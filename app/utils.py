import os
from typing import Optional


def normalize_symbol(symbol: str) -> str:
    raw = symbol.strip().upper()
    if "." in raw:
        return raw
    if raw.isdigit() and len(raw) < 5:
        return raw.zfill(6)
    return raw


def detect_network_restriction_hint() -> Optional[str]:
    if os.getenv("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        return (
            "当前会话处于沙箱禁网模式（CODEX_SANDBOX_NETWORK_DISABLED=1）。"
            "请在 OpenClaw/Codex 启动时改为允许联网模式后重试。"
        )
    return None


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out
