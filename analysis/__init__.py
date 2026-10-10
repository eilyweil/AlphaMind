"""分析层共享工具。"""


def find_col(df, candidates):
    """从 DataFrame 列名中匹配候选列名（先精确后包含），返回列名或 None。"""
    if df is None or df.empty:
        return None
    cols = {str(c): c for c in df.columns}
    lower = {k.lower(): v for k, v in cols.items()}
    for cand in candidates:
        c = cand.lower()
        if c in lower:
            return lower[c]
    for cand in candidates:
        c = cand.lower()
        for k, v in lower.items():
            if c in k:
                return v
    return None


def to_float(v):
    """安全转 float，失败返回 None。"""
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
