import csv
from typing import Optional


_SYMBOL_KEYS = {"symbol", "code", "ticker", "股票代码", "证券代码", "代码"}
_INDUSTRY_KEYS = {"industry", "行业", "industry_name", "行业名称"}
_INDUSTRY_L1_KEYS = {"industry_l1", "一级行业", "行业一级", "sw_l1", "申万一级行业"}
_INDUSTRY_L2_KEYS = {"industry_l2", "二级行业", "行业二级", "sw_l2", "申万二级行业"}


def _pick_industry_column(fieldnames: list[str], level: str) -> Optional[str]:
    normalized = {col: str(col).strip().lower() for col in fieldnames}
    if level == "l1":
        priorities = [_INDUSTRY_L1_KEYS, _INDUSTRY_KEYS]
    elif level == "l2":
        priorities = [_INDUSTRY_L2_KEYS, _INDUSTRY_L1_KEYS, _INDUSTRY_KEYS]
    else:
        priorities = [_INDUSTRY_KEYS, _INDUSTRY_L1_KEYS, _INDUSTRY_L2_KEYS]

    for keyset in priorities:
        for col, lower in normalized.items():
            if col in keyset or lower in keyset:
                return col
    return None


def load_industry_map(path: str, level: str = "auto") -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path:
        return mapping

    normalized_level = str(level or "auto").strip().lower()
    if normalized_level not in {"auto", "l1", "l2"}:
        raise ValueError("industry level 仅支持 auto/l1/l2")

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return mapping
        symbol_col: Optional[str] = None
        industry_col: Optional[str] = _pick_industry_column(reader.fieldnames, normalized_level)
        for col in reader.fieldnames:
            key = str(col).strip().lower()
            if symbol_col is None and (key in _SYMBOL_KEYS or col in _SYMBOL_KEYS):
                symbol_col = col
        if symbol_col is None or industry_col is None:
            raise ValueError("行业映射文件缺少 symbol/industry 列")

        for row in reader:
            raw_symbol = str(row.get(symbol_col, "")).strip()
            raw_industry = str(row.get(industry_col, "")).strip()
            if not raw_symbol or not raw_industry:
                continue
            symbol = "".join(ch for ch in raw_symbol if ch.isdigit())
            if len(symbol) == 6:
                mapping[symbol] = raw_industry
            else:
                mapping[raw_symbol.upper()] = raw_industry
    return mapping
