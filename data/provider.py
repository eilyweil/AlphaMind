"""数据源适配器抽象接口。

所有模块只依赖 DataProvider 抽象，不直接依赖 akshare，
后续切换聚宽（JoinQuant）时只需新增一个 provider 实现。
"""
from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    name = "base"

    @abstractmethod
    def get_snapshot(self, code: str) -> dict:
        """实时行情快照：最新价/涨跌幅/成交量/成交额/市值等。"""

    @abstractmethod
    def get_history(self, code: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        """日线历史行情。"""

    @abstractmethod
    def get_valuation(self, code: str) -> pd.DataFrame:
        """估值指标：PE/PB/PS/PCF + 历史分位。"""

    @abstractmethod
    def get_financials(self, code: str) -> pd.DataFrame:
        """财务指标：ROE/毛利率/净利率/营收增速等。"""

    @abstractmethod
    def get_fund_flow(self, code: str) -> pd.DataFrame:
        """个股资金流：主力/超大单/大单/中单/小单净流入。"""

    @abstractmethod
    def get_announcements(self, code: str, days: int = 30) -> pd.DataFrame:
        """近期公告列表：标题/日期/链接。"""

    @abstractmethod
    def get_profit_forecast(self, code: str) -> pd.DataFrame:
        """券商盈利预测（一致预期的近似）。"""
