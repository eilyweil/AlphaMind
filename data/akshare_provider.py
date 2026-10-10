"""akshare 数据源实现（已适配当前网络环境 + 本地缓存秒开）。

说明：东财域名（eastmoney.com push/push2his）在当前网络不可达，
故全部切换到可用数据源：新浪（行情/财务）、百度（估值）、同花顺（资金流/盈利预测）、巨潮（公告）。
所有方法均走本地缓存：命中缓存直接返回（秒开），未命中才抓取并落盘。
"""
import os

# 强制直连国内数据源，绕过系统代理（避免 Clash 对国内域名的分流不稳定）
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

import datetime as dt  # noqa: E402

import pandas as pd  # noqa: E402

from . import cache  # noqa: E402
from .provider import DataProvider  # noqa: E402
from utils.config import normalize_code, code_to_market  # noqa: E402


def _to_float(v):
    try:
        if v is None:
            return None
        return float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_amount(v):
    """解析 '3.99亿' / '399000000' / '399万' 等为元(float)。"""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("亿"):
            return float(s[:-1]) * 1e8
        if s.endswith("万"):
            return float(s[:-1]) * 1e4
        return float(s)
    except ValueError:
        return None


def _empty(result) -> bool:
    if result is None:
        return True
    if isinstance(result, pd.DataFrame):
        return result.empty
    if isinstance(result, dict):
        return not result
    return False


class AkshareProvider(DataProvider):
    name = "akshare"

    def __init__(self):
        self._ak = None

    @property
    def ak(self):
        """懒加载 akshare：缓存命中时无需 import，保证打开秒开。"""
        if self._ak is None:
            import akshare as ak
            self._ak = ak
        return self._ak

    def _cached(self, key: str, fn):
        """读缓存 → 未命中抓取 → 落盘缓存。"""
        cached = cache.load(key)
        if cached is not None:
            return cached
        result = fn()
        if not _empty(result):
            cache.save(key, result)
        return result

    # ---- 实时快照（新浪全市场：全量下载一次后按代码过滤，避免逐股重复拉全市场）----
    def _spot_df(self) -> pd.DataFrame:
        return self._cached("spot_all", self._fetch_spot_df)

    def _fetch_spot_df(self) -> pd.DataFrame:
        try:
            return self.ak.stock_zh_a_spot()
        except Exception as e:  # noqa: BLE001
            print(f"[akshare] stock_zh_a_spot 失败: {e}")
            return pd.DataFrame()

    def get_snapshot(self, code: str) -> dict:
        code = normalize_code(code)
        df = self._spot_df()
        if df is None or df.empty:
            return {}
        row = df[df["代码"].astype(str).str[-6:] == code]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "代码": code,
            "名称": r.get("名称", ""),
            "最新价": _to_float(r.get("最新价")),
            "涨跌幅": _to_float(r.get("涨跌幅")),
            "涨跌额": _to_float(r.get("涨跌额")),
            "成交量": _to_float(r.get("成交量")),
            "成交额": _to_float(r.get("成交额")),
        }

    # ---- 历史行情（新浪，英文字段，缓存全历史后按日期过滤）----
    def get_history(self, code: str, start: str = None, end: str = None, adjust: str = "qfq") -> pd.DataFrame:
        code = normalize_code(code)
        df = self._cached(f"history_{code}_{adjust}", lambda: self._fetch_history(code, adjust))
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])
        if start:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df

    def _fetch_history(self, code: str, adjust: str) -> pd.DataFrame:
        symbol = code_to_market(code) + code
        try:
            df = self.ak.stock_zh_a_daily(symbol=symbol, adjust=adjust)
            if df is None or df.empty:
                return pd.DataFrame()
            df["date"] = pd.to_datetime(df["date"])
            return df
        except Exception as e:  # noqa: BLE001
            print(f"[akshare] get_history({code}) 失败: {e}")
            return pd.DataFrame()

    # ---- 估值指标（百度，含历史，可算分位）----
    def get_valuation(self, code: str) -> pd.DataFrame:
        code = normalize_code(code)
        return self._cached(f"valuation_{code}", lambda: self._fetch_valuation(code))

    def _fetch_valuation(self, code: str) -> pd.DataFrame:
        indicators = {"pe": "市盈率(TTM)", "pb": "市净率", "ps": "市销率", "pcf": "市现率"}
        merged = pd.DataFrame()
        for key, ind in indicators.items():
            try:
                df = self.ak.stock_zh_valuation_baidu(symbol=code, indicator=ind, period="近一年")
                if df is None or df.empty:
                    continue
                merged[key] = pd.to_numeric(df["value"], errors="coerce").reset_index(drop=True)
                if "date" not in merged.columns:
                    merged["date"] = df["date"].astype(str).reset_index(drop=True)
            except Exception as e:  # noqa: BLE001
                print(f"[akshare] get_valuation[{key}]({code}) 失败: {e}")
        return merged

    # ---- 财务指标（新浪，中文列）----
    def get_financials(self, code: str) -> pd.DataFrame:
        code = normalize_code(code)
        return self._cached(f"financials_{code}", lambda: self._fetch_financials(code))

    def _fetch_financials(self, code: str) -> pd.DataFrame:
        try:
            return self.ak.stock_financial_analysis_indicator(symbol=code, start_year="2020")
        except Exception as e:  # noqa: BLE001
            print(f"[akshare] get_financials({code}) 失败: {e}")
            return pd.DataFrame()

    # ---- 资金流（同花顺 5 日排行：全量下载一次后按代码过滤）----
    def _fundflow_df(self) -> pd.DataFrame:
        return self._cached("fundflow_5day_all", self._fetch_fundflow_df)

    def _fetch_fundflow_df(self) -> pd.DataFrame:
        try:
            return self.ak.stock_fund_flow_individual(symbol="5日排行")
        except Exception as e:  # noqa: BLE001
            print(f"[akshare] stock_fund_flow_individual 失败: {e}")
            return pd.DataFrame()

    def get_fund_flow(self, code: str) -> dict:
        code = normalize_code(code)
        df = self._fundflow_df()
        if df is None or df.empty:
            return {}
        # 同花顺会去掉前导零（002415 -> 2415），zfill 还原为 6 位代码
        row = df[df["股票代码"].astype(str).str.zfill(6) == code]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "股票简称": r.get("股票简称", ""),
            "资金流入净额": _parse_amount(r.get("资金流入净额")),
            "阶段涨跌幅": _to_float(r.get("阶段涨跌幅")),
            "连续换手率": _to_float(r.get("连续换手率")),
        }

    # ---- 公告（巨潮，逐日拉取全市场后过滤个股）----
    def get_announcements(self, code: str, days: int = 30) -> pd.DataFrame:
        code = normalize_code(code)
        return self._cached(f"announcements_{code}_{days}", lambda: self._fetch_announcements(code, days))

    def _fetch_announcements(self, code: str, days: int) -> pd.DataFrame:
        """巨潮资讯网（cninfo）直连，按证券代码 + 日期区间查询公告。

        说明：原 stock_notice_report 走东方财富公告接口，东财域名在当前网络不可达，
        故改用巨潮 cninfo 直连：searchkey=代码 精确过滤、seDate 支持区间一次查询。
        """
        import re
        import requests

        code = normalize_code(code)
        start = dt.date.today() - dt.timedelta(days=days)
        end = dt.date.today()
        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "http://www.cninfo.com.cn/new/disclosure",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        se = f"{start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')}"

        rows = []
        page = 1
        total = None
        while True:
            payload = {
                "pageNum": str(page), "pageSize": "30", "column": "szse",
                "tabName": "fulltext", "stock": "", "searchkey": code, "secid": "",
                "category": "", "trade": "", "plate": "",
                "seDate": se, "sortName": "", "sortType": "", "isHLtitle": "true",
            }
            try:
                data = requests.post(url, data=payload, headers=headers, timeout=20).json()
            except Exception as e:  # noqa: BLE001
                print(f"[cninfo] 公告查询失败({code}): {e}")
                break
            if total is None:
                total = int(data.get("totalAnnouncement") or 0)
            for a in data.get("announcements") or []:
                if a.get("secCode") != code:
                    continue
                title = re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "")
                ts = a.get("announcementTime")
                date_str = ""
                if ts:
                    try:
                        date_str = dt.datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
                    except (TypeError, ValueError, OSError):
                        date_str = ""
                adjunct = a.get("adjunctUrl") or ""
                rows.append({
                    "代码": a.get("secCode"),
                    "名称": a.get("secName"),
                    "公告标题": title,
                    "公告日期": date_str,
                    "公告链接": f"http://static.cninfo.com.cn/{adjunct}" if adjunct else "",
                })
            page += 1
            if total is not None and page * 30 >= total:
                break
            if page > 100:  # 安全上限，防止死循环
                break

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).drop_duplicates(subset=["公告标题"])

    # ---- 券商盈利预测（同花顺，一致预期近似）----
    def get_profit_forecast(self, code: str) -> pd.DataFrame:
        code = normalize_code(code)
        return self._cached(f"forecast_{code}", lambda: self._fetch_profit_forecast(code))

    def _fetch_profit_forecast(self, code: str) -> pd.DataFrame:
        try:
            return self.ak.stock_profit_forecast_ths(symbol=code, indicator="预测年报每股收益")
        except Exception as e:  # noqa: BLE001
            print(f"[akshare] get_profit_forecast({code}) 失败: {e}")
            return pd.DataFrame()


def get_provider() -> DataProvider:
    """全局 provider 单例。"""
    return AkshareProvider()
