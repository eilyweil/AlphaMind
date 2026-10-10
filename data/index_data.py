"""指数数据层：沪深300 成分股（可插拔）+ 基准日线 + 成分股批量历史行情。

成分股取数抽象为 get_constituents(date) -> list[str]，便于后续从「当前成分近似」
无缝切换到 point-in-time 严谨数据（tushare index_weight）：
  - CurrentConstituentsProvider：当前成分近似（默认，先跑通；含幸存者偏差，结论注明）
  - TushareConstituentsProvider：point-in-time 严谨数据（需 TUSHARE_TOKEN，2000 积分起）
"""
import datetime as dt

import pandas as pd

from . import cache


class CurrentConstituentsProvider:
    """所有时点都返回「今天」的沪深300成分（近似口径，存在幸存者偏差）。"""

    def __init__(self, symbol: str = "000300"):
        self.symbol = symbol
        self._codes = None
        self._names = None

    def _load(self):
        if self._codes is None:
            import akshare as ak
            df = ak.index_stock_cons_csindex(symbol=self.symbol)
            self._codes = [str(c).zfill(6) for c in df["成分券代码"]]
            self._names = dict(zip(self._codes, df["成分券名称"]))
        return self._codes, self._names

    def get_constituents(self, date=None) -> list:
        codes, _ = self._load()
        return list(codes)

    def names(self) -> dict:
        _, names = self._load()
        return dict(names)


class TushareConstituentsProvider:
    """point-in-time 严谨成分（需 TUSHARE_TOKEN + tushare，2000 积分起）。留实现位。"""

    def __init__(self, symbol: str = "000300.SH"):
        self.symbol = symbol

    def get_constituents(self, date) -> list:
        raise NotImplementedError("需配置 TUSHARE_TOKEN 并安装 tushare 后启用 index_weight")


def get_constituent_provider():
    """默认用当前成分近似；接入 tushare 后在此切换实现。"""
    return CurrentConstituentsProvider()


# ---- 基准（沪深300 价格指数，新浪）----
def get_benchmark(start=None, end=None) -> pd.DataFrame:
    def _fetch():
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df["date"] = pd.to_datetime(df["date"])
        return df

    df = cache.load("index_sh000300")
    if df is None:
        df = _fetch()
        if df is not None and not df.empty:
            cache.save("index_sh000300", df)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    return df.sort_values("date").reset_index(drop=True)


# ---- 基准（沪深300 全收益指数 H00300，中证官网）----
def get_total_return_benchmark(start=None, end=None) -> pd.DataFrame:
    """沪深300 全收益指数（H00300，含股息再投），返回 date/close 两列。

    与策略（前复权、含股息再投）口径一致，消除价格指数造成的约 2%/年股息口径差。
    """
    def _fetch():
        import akshare as ak
        df = ak.stock_zh_index_hist_csindex(symbol="H00300", start_date="20050101", end_date="20301231")
        df = df.dropna(subset=["收盘"]).copy()
        df = df[["日期", "收盘"]].rename(columns={"日期": "date", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"])
        # 剔除中证官网在起始日填充的非交易日占位行（周末无交易）
        df = df[df["date"].dt.weekday < 5]
        df = df.drop_duplicates(subset="date", keep="last")
        return df

    df = cache.load("index_h00300")
    if df is None:
        df = _fetch()
        if df is not None and not df.empty:
            cache.save("index_h00300", df)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    return df.sort_values("date").reset_index(drop=True)


_BENCHMARKS = {
    "price": get_benchmark,                # 000300 价格指数
    "total_return": get_total_return_benchmark,  # H00300 全收益指数（推荐）
}


def get_benchmark_by_kind(kind: str, start=None, end=None) -> pd.DataFrame:
    """按口径取基准：'price' 价格指数 / 'total_return' 全收益指数。"""
    return _BENCHMARKS.get(kind, get_benchmark)(start, end)


# ---- 成分股批量历史：拼成 close/open 宽表 ----
def build_panel(provider, codes, start=None, end=None, progress=None):
    """拉取所有成分股前复权日线，返回 (close, open) 宽表（index=日期，columns=代码）。

    progress: 可选回调 progress(done, total)，用于 UI 进度条。
    """
    close_frames, open_frames = [], []
    total = len(codes)
    for i, c in enumerate(codes, 1):
        df = provider.get_history(c, start, end)
        if df is None or df.empty:
            if progress:
                progress(i, total)
            continue
        df = df[["date", "open", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        close_frames.append(df["close"].rename(c))
        open_frames.append(df["open"].rename(c))
        if progress:
            progress(i, total)

    close = pd.concat(close_frames, axis=1) if close_frames else pd.DataFrame()
    open_ = pd.concat(open_frames, axis=1) if open_frames else pd.DataFrame()
    return close, open_
