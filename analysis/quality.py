"""模块1：盈利质量（ROE/毛利率/净利率/营收增速）+ 趋势。"""
import pandas as pd

from . import find_col, to_float

_INDICATORS = {
    "roe": ["roe", "净资产收益率", "加权净资产收益率"],
    "gross_margin": ["gross_profit_margin", "销售毛利率", "主营业务利润率"],
    "net_margin": ["net_profit_margin", "销售净利率"],
    "revenue_growth": ["main_business_income_growth", "主营业务收入增长率", "营业收入增长率"],
    "profit_growth": ["net_profit_growth", "净利润增长率"],
}

_LABELS = {
    "roe": "ROE(净资产收益率)",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "revenue_growth": "营收增速",
    "profit_growth": "净利润增速",
}


def compute_quality(df: pd.DataFrame) -> dict:
    """返回 {指标key: {label, latest, series(近N期列表), dates}}。

    财务指标接口返回的每行是一个报告期，需要按时间升序排列后取趋势。
    """
    if df is None or df.empty:
        return {}
    date_col = find_col(df, ["date", "日期", "报告期"])
    dates = df[date_col].astype(str).tolist() if date_col else None

    result = {}
    for key, cands in _INDICATORS.items():
        col = find_col(df, cands)
        if col is None:
            continue
        series = pd.to_numeric(df[col], errors="coerce").tolist()
        latest = None
        for v in reversed(series):
            if v is not None and pd.notna(v):
                latest = float(v)
                break
        result[key] = {
            "label": _LABELS[key],
            "latest": latest,
            "series": series,
        }
    result["dates"] = dates
    return result
