"""模块1：资金面（同花顺资金流排名 -> 个股资金流入净额）。"""
from . import to_float


def compute_fundflow(flow: dict, days: int = 5) -> dict:
    """从 provider 返回的 dict 直接格式化。

    返回 {资金流入净额: float(元), 阶段涨跌幅: float(%), 连续换手率: float(%), 股票简称: str}
    """
    if not flow:
        return {}
    net = flow.get("资金流入净额")
    return {
        "资金流入净额": to_float(net),
        "阶段涨跌幅": to_float(flow.get("阶段涨跌幅")),
        "连续换手率": to_float(flow.get("连续换手率")),
        "股票简称": flow.get("股票简称", ""),
    }
