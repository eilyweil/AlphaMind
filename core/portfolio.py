"""组合层：多持仓 + 集中度 + 组合估值分位（「投研体 → 投顾体」的第一步）。

现状 demo 以单票演示。组合层把多个持仓的个股研判叠加为组合维度的综合分析，
兑现「我的组合整体贵不贵、风险集中在哪」的长期愿景。本模块不依赖 streamlit。
"""
import json
import os


class Portfolio:
    """个人持仓组合。holdings 元素：{"code", "name", "shares", "cost"}。"""

    def __init__(self, engine=None):
        from core.engine import get_engine

        self.engine = engine or get_engine()
        self.holdings = []

    def add(self, code: str, shares: float = 0, cost: float = None) -> None:
        """添加 / 更新一只持仓（按 code 去重）。"""
        for h in self.holdings:
            if h["code"] == code:
                h["shares"] = shares
                if cost is not None:
                    h["cost"] = cost
                return
        self.holdings.append({
            "code": code,
            "name": self.engine.stock_name(code),
            "shares": shares,
            "cost": cost,
        })

    def remove(self, code: str) -> None:
        self.holdings = [h for h in self.holdings if h["code"] != code]

    def to_dict(self) -> list:
        """序列化持仓（用于落盘 JSON）。"""
        return [dict(h) for h in self.holdings]

    @classmethod
    def from_dict(cls, data, engine=None) -> "Portfolio":
        """从 JSON 数据恢复持仓。"""
        p = cls(engine=engine)
        p.holdings = [dict(h) for h in (data or [])]
        return p

    def _positions(self) -> list:
        """每只持仓的最新价 / 市值 / 成本 / 浮盈亏。"""
        out = []
        for h in self.holdings:
            snap = self.engine.snapshot(h["code"])
            price = snap.get("最新价")
            mv = price * h["shares"] if price is not None and h["shares"] else None
            cost_val = h["cost"]
            pnl = (price - cost_val) / cost_val if (price is not None and cost_val) else None
            out.append({
                "code": h["code"],
                "name": snap.get("名称") or h["name"],
                "price": price,
                "shares": h["shares"],
                "cost": cost_val,
                "market_value": mv,
                "pnl_pct": pnl,
            })
        return out

    def overview(self) -> dict:
        """组合全景：个股持仓明细 + 组合汇总（总市值 / 集中度 / 加权估值分位 / 浮盈亏）。

        口径：填了股数 → 市值加权；未填股数（shares=0）→ 等权回退（weight=1/n），
        此时市值 / 成本 / 浮盈亏返回 None，由界面显示「— / 等权」。
        """
        positions = self._positions()
        total_mv = sum((p["market_value"] or 0) for p in positions)
        total_cost = sum((p["cost"] or 0) * (p["shares"] or 0) for p in positions)

        n = len(positions)
        if total_mv > 0:
            for p in positions:
                p["weight"] = round((p["market_value"] or 0) / total_mv, 4)
        elif n:
            for p in positions:
                p["weight"] = round(1.0 / n, 4)

        # 集中度：HHI（赫芬达尔指数，1=完全集中，越接近 0 越分散）+ 第一大持仓占比
        hhi = sum(p["weight"] ** 2 for p in positions) if positions else 0
        top1 = max((p["weight"] for p in positions), default=0)

        # 加权估值分位（以 PE 历史分位为代理，按 weight 加权；仅统计有分位数据的持仓）
        acc, w_sum = 0.0, 0.0
        for p in positions:
            pe_pct = (self.engine.valuation(p["code"]).get("pe") or {}).get("pct")
            if pe_pct is not None:
                acc += pe_pct * p["weight"]
                w_sum += p["weight"]
        weighted_pe_pct = round(acc / w_sum, 1) if w_sum else None

        pnl_pct = (total_mv - total_cost) / total_cost if total_cost else None

        return {
            "positions": positions,
            "total_market_value": total_mv or None,
            "total_cost": total_cost or None,
            "pnl_pct": pnl_pct,
            "hhi": round(hhi, 4),
            "top1_weight": round(top1, 4),
            "weighted_pe_percentile": weighted_pe_pct,
        }

    # ---------- 组合综合评估（AI） ----------
    def _portfolio_context(self, ov: dict, sent: dict = None) -> str:
        """把组合全景拼成给大模型的上下文文本。sent 为 {code: 情绪}，可空。"""
        sent = sent or {}
        lines = []
        for p in ov["positions"]:
            w = p.get("weight")
            w_str = f"{w * 100:.1f}%" if w is not None else "—"
            pe_pct = (self.engine.valuation(p["code"]).get("pe") or {}).get("pct")
            pe_str = f"PE历史分位 {pe_pct}%" if pe_pct is not None else "暂无"
            roe = (self.engine.quality(p["code"]).get("roe") or {}).get("latest")
            roe_str = f"{roe:.2f}%" if roe is not None else "暂无"
            pnl = p.get("pnl_pct")
            pnl_str = f"{pnl * 100:+.2f}%" if pnl is not None else "未设成本"
            parts = [f"{p['name']}({p['code']}) 权重{w_str}", pe_str, f"ROE {roe_str}", f"浮盈亏 {pnl_str}"]
            s = sent.get(p["code"])
            if s:
                parts.append(f"情绪 看多{s['bull']}%/看空{s['bear']}%")
            lines.append(" | ".join(parts))

        mv = ov["total_market_value"]
        mv_str = f"{mv / 1e4:.2f} 万" if mv else "未填股数(等权)"
        pnl = ov["pnl_pct"]
        pnl_str = f"{pnl * 100:+.2f}%" if pnl is not None else "未设成本"
        pe = ov["weighted_pe_percentile"]
        pe_str = f"{pe}%" if pe is not None else "暂无"
        lines.append(
            f"\n组合汇总：总市值 {mv_str}，整体浮盈亏 {pnl_str}，"
            f"HHI集中度 {ov['hhi']}，第一大持仓占比 {ov['top1_weight'] * 100:.1f}%，加权PE历史分位 {pe_str}"
        )
        return "\n".join(lines)

    def overall_analysis(self, include_sentiment: bool = False) -> dict:
        """组合综合评估：聚合各持仓后交给大模型，输出结构化研判。

        include_sentiment=True 时额外批量抓取各持仓社区情绪（一次 LLM 分类，非逐票）。
        """
        from ai.client import chat_json
        from ai.prompts import build_portfolio_prompt

        ov = self.overview()
        if not ov["positions"]:
            return None
        sent = None
        if include_sentiment:
            from analysis import sentiment as sent_mod
            sent = sent_mod.analyze_sentiment_batch([p["code"] for p in ov["positions"]])
        return chat_json(build_portfolio_prompt(self._portfolio_context(ov, sent)))


def load_portfolio(path: str, engine=None) -> Portfolio:
    """从 JSON 文件读取持仓（不存在则返回空组合）。"""
    data = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:  # noqa: BLE001
            print(f"[portfolio] 读取失败: {ex}")
    return Portfolio.from_dict(data, engine=engine)


def save_portfolio(path: str, portfolio: Portfolio) -> None:
    """把持仓落盘 JSON（非关键路径，失败仅告警不阻断）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(portfolio.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as ex:  # noqa: BLE001
        print(f"[portfolio] 保存失败: {ex}")
