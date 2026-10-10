"""模块1：估值指标 + 历史分位。"""
import pandas as pd

from . import find_col, to_float

# 各估值指标的候选列名（乐咕 stock_a_indicator_lg）
_CAND = {
    "pe": ["pe_ttm", "pe", "市盈率"],
    "pb": ["pb", "市净率"],
    "ps": ["ps_ttm", "ps", "市销率"],
    "pcf": ["pcf", "pcf_ttm", "市现率"],
}


def _percentile(series: pd.Series, value: float):
    """当前值在历史序列中的分位（0-100，越低越便宜）。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty or value is None or pd.isna(value):
        return None
    return round(float((s <= value).mean() * 100), 1)


def compute_valuation(df: pd.DataFrame) -> dict:
    """返回 {pe: {value, pct}, pb: {...}, ps: {...}, pcf: {...}, mv: {...}}。"""
    if df is None or df.empty:
        return {}
    result = {}
    for key, cands in _CAND.items():
        col = find_col(df, cands)
        if col is None:
            result[key] = {"value": None, "pct": None}
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        latest = None
        for v in series[::-1]:
            if pd.notna(v):
                latest = float(v)
                break
        pct = _percentile(series, latest)
        result[key] = {"value": latest, "pct": pct}

    # 总市值
    mv_col = find_col(df, ["total_mv", "总市值"])
    if mv_col is not None:
        result["total_mv"] = to_float(df[mv_col].iloc[-1])

    # 最新交易日
    date_col = find_col(df, ["trade_date", "date", "日期"])
    if date_col is not None:
        result["date"] = str(df[date_col].iloc[-1])
    return result
