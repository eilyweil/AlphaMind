"""AlphaMind 投研引擎：把「取数 + 计算 + AI 研判」统一封装为 UI 无关的服务层。

Streamlit 页面与飞书 / Hermes 侧都调用这一层，保证结论同源、可回溯。
本模块不依赖 streamlit，可在任意 Python 运行时（含 Hermes 工具）中直接调用。
"""
import datetime as dt

import pandas as pd

from ai.client import chat, chat_json
from ai.prompts import SYSTEM, build_assistant_prompt, build_backtest_prompt
from analysis import backtest as bt
from analysis import factor_backtest as ft
from analysis import find_col
from analysis import fundflow as ff_mod
from analysis import quality as qual_mod
from analysis import sentiment as sent_mod
from analysis import valuation as val_mod
from data import index_data
from data.akshare_provider import get_provider


class ResearchEngine:
    """面向单票的投研引擎，对外暴露五个维度 + 综合研判。"""

    def __init__(self, provider=None):
        self.provider = provider or get_provider()

    # ---------- 行情 ----------
    def snapshot(self, code: str) -> dict:
        """实时行情快照。"""
        return self.provider.get_snapshot(code) or {}

    def stock_name(self, code: str) -> str:
        """返回 '名称(代码)'，无名称时回退为代码。"""
        name = self.snapshot(code).get("名称") or ""
        return f"{name}({code})" if name else code

    def history(self, code: str, start: str = None, end: str = None) -> pd.DataFrame:
        """前复权日线历史行情。"""
        return self.provider.get_history(code, start, end)

    # ---------- 估值 ----------
    def valuation(self, code: str) -> dict:
        """PE / PB / PS / PCF 及近一年历史分位。"""
        return val_mod.compute_valuation(self.provider.get_valuation(code))

    # ---------- 财务 ----------
    def quality(self, code: str) -> dict:
        """盈利质量（ROE / 毛利率 / 净利率 / 营收增速 / 净利增速 + 趋势）。"""
        return qual_mod.compute_quality(self.provider.get_financials(code))

    def financials(self, code: str) -> dict:
        """财务全景：盈利质量 + 原始财报 + 券商盈利预测。"""
        fin = self.provider.get_financials(code)
        return {
            "quality": qual_mod.compute_quality(fin),
            "financials": fin,
            "forecast": self.provider.get_profit_forecast(code),
        }

    def financial_analysis(self, code: str) -> dict:
        """财报速解（预期差分析）：AI 输出 summary / vs_consensus / vs_last_year / guidance / risk。"""
        data = self.financials(code)
        fin_text = self._financial_text(data["quality"], data["financials"])
        forecast = data["forecast"]
        fore_text = forecast.to_string(index=False) if forecast is not None and not forecast.empty else "（无）"
        return self._financial_analyze(fin_text, fore_text)

    # ---------- 公告 ----------
    def announcements(self, code: str, days: int = 30) -> pd.DataFrame:
        """近 N 天公告列表。"""
        return self.provider.get_announcements(code, days=days)

    def announcement_analysis(self, code: str, days: int = 30, max_items: int = 20) -> list:
        """公告快读：AI 逐条标注类型 / 核心变化 / 是否实质性变化。"""
        anns = self.announcements(code, days)
        if anns is None or anns.empty:
            return []
        title_col = "公告标题" if "公告标题" in anns.columns else None
        if title_col is None:
            return []
        titles = anns[title_col].astype(str).tolist()
        return self._analyze_batch(titles[:max_items])

    # ---------- 情绪 ----------
    def sentiment(self, code: str, limit: int = 15) -> dict:
        """东财股吧情绪：看多 / 看空 / 中性比例 + 代表观点。"""
        posts = sent_mod.fetch_guba_posts(code, limit=limit)
        return sent_mod.analyze_sentiment(posts)

    # ---------- 资金面 ----------
    def fundflow(self, code: str, days: int = 5) -> dict:
        """同花顺资金流（资金流入净额 / 阶段涨跌幅 / 连续换手率）。"""
        return ff_mod.compute_fundflow(self.provider.get_fund_flow(code), days=days)

    # ---------- 回测 ----------
    def backtest(self, code: str, strategy: str = "双均线（MA）", params: dict = None,
                 period_days: int = 730, initial_wan: float = 10) -> dict:
        """策略回测：返回 metrics + 回测 df + 买卖点。行情不足（<40 交易日）返回 None。"""
        start = (dt.date.today() - dt.timedelta(days=period_days)).strftime("%Y-%m-%d")
        end = dt.date.today().strftime("%Y-%m-%d")
        df = self.history(code, start, end)
        if df is None or df.empty or len(df) < 40:
            return None
        df = df.sort_values("date").reset_index(drop=True)
        params = dict(params) if params else dict(bt.STRATEGIES[strategy]["params"])
        pos = bt.STRATEGIES[strategy]["fn"](df, **params)
        metrics, back_df, trades = bt.run_backtest(df, pos, initial=initial_wan * 1e4)
        return {
            "metrics": metrics,
            "df": back_df,
            "buy_idx": trades["buy_idx"],
            "sell_idx": trades["sell_idx"],
            "strategy": strategy,
            "params": params,
            "name": self.stock_name(code),
        }

    def backtest_interpretation(self, result: dict) -> str:
        """回测 AI 解读（克制，附风险提示）。"""
        m = result["metrics"]
        summary = (
            f"总收益率 {m['总收益率'] * 100:+.2f}%，年化 {m['年化收益率'] * 100:+.2f}%，"
            f"最大回撤 {m['最大回撤'] * 100:.2f}%，夏普 {m['夏普比率']:.2f}，"
            f"交易 {m['交易次数']} 次、胜率 {m['胜率'] * 100:.1f}%；"
            f"买入持有同期 {m['买入持有收益'] * 100:+.2f}%。"
        )
        return chat(build_backtest_prompt(result["strategy"], str(result["params"]), summary, result["name"]))

    # ---------- 因子组合回测（沪深300 截面动量，月频） ----------
    def _factor_panel(self, start: str, end: str, progress=None, benchmark: str = "total_return"):
        """拉取成分股 + 基准 + 批量历史，构建回测宽表（首次慢，之后走缓存）。"""
        prov = index_data.get_constituent_provider()
        names = prov.names()
        constituents = prov.get_constituents()
        # 动量窗口 + 趋势均线需向前多取约一年预热（基准同样前移，保证 MA/波动率可算）
        pre_start = (dt.date.fromisoformat(start) - dt.timedelta(days=400)).strftime("%Y-%m-%d")
        bench = index_data.get_benchmark_by_kind(benchmark, pre_start, end)
        close, open_ = index_data.build_panel(self.provider, constituents, pre_start, end, progress)
        return names, constituents, bench, close, open_

    def factor_backtest(self, start: str = "2015-01-01", end: str = "2025-12-31",
                        top_n: int = 30, window: str = "12-1", slippage: float = 0.001,
                        initial_wan: float = 100, progress=None,
                        benchmark: str = "total_return", strategy: str = "enhanced",
                        vol_target: float = 0.15) -> dict:
        """沪深300 截面组合月频回测。

        strategy: 'enhanced' 多因子增强（动量+低波+趋势风控+波动率目标）/ 'momentum' 经典动量。
        数据不足返回 None。
        """
        names, constituents, bench, close, open_ = self._factor_panel(start, end, progress, benchmark)
        if close.empty or bench.empty:
            return None
        windows = {"6-1": (126, 21), "12-1": (252, 21), "12-6": (252, 126)}
        lookback, skip = windows.get(window, (252, 21))
        if strategy == "momentum":
            res = ft.run_factor_backtest(
                close, open_, bench, constituents, names=names,
                top_n=top_n, lookback=lookback, skip_recent=skip,
                initial=initial_wan * 1e4, slippage=slippage,
            )
        else:
            res = ft.run_enhanced_backtest(
                close, open_, bench, constituents, names=names,
                top_n=top_n, lookback=lookback, skip_recent=skip,
                initial=initial_wan * 1e4, slippage=slippage, vol_target=vol_target,
            )
        nav = res["nav"]
        nav = nav[(nav["date"] >= pd.to_datetime(start)) & (nav["date"] <= pd.to_datetime(end))]
        res["nav"] = nav.reset_index(drop=True)
        if not nav.empty:
            ni = nav.set_index("date")
            res["metrics"] = ft._compute_metrics(ni, initial_wan * 1e4, res["turnover_sell"])
            res["annual"] = ft._annual_table(ni)
        res["strategy"] = strategy
        return res

    def factor_backtest_sensitivity(self, start: str = "2015-01-01", end: str = "2025-12-31",
                                    top_n: int = 30, window: str = "12-1",
                                    initial_wan: float = 100, progress=None,
                                    benchmark: str = "total_return", strategy: str = "enhanced",
                                    vol_target: float = 0.15) -> dict:
        """四档成本敏感性（滑点 0/15/30/50 bp），面板只拉一次。"""
        names, constituents, bench, close, open_ = self._factor_panel(start, end, progress, benchmark)
        if close.empty or bench.empty:
            return None
        windows = {"6-1": (126, 21), "12-1": (252, 21), "12-6": (252, 126)}
        lookback, skip = windows.get(window, (252, 21))
        out = {}
        for slip_bp in [0, 15, 30, 50]:
            if strategy == "momentum":
                res = ft.run_factor_backtest(
                    close, open_, bench, constituents, names=names,
                    top_n=top_n, lookback=lookback, skip_recent=skip,
                    initial=initial_wan * 1e4, slippage=slip_bp / 1e4,
                )
            else:
                res = ft.run_enhanced_backtest(
                    close, open_, bench, constituents, names=names,
                    top_n=top_n, lookback=lookback, skip_recent=skip,
                    initial=initial_wan * 1e4, slippage=slip_bp / 1e4, vol_target=vol_target,
                )
            nav = res["nav"]
            nav = nav[(nav["date"] >= pd.to_datetime(start)) & (nav["date"] <= pd.to_datetime(end))]
            ni = nav.set_index("date")
            m = ft._compute_metrics(ni, initial_wan * 1e4, res["turnover_sell"])
            out[slip_bp] = {
                "nav": ni.reset_index(),
                "夏普": m["夏普比率"], "年化": m["年化收益率"], "最大回撤": m["最大回撤"],
            }
        return out

    # ---------- 综合研判（AI 研报助手） ----------
    def report(self, code: str, question: str) -> dict:
        """综合研判：聚合基本面 + 社区情绪，输出结构化研判。"""
        snap = self.snapshot(code)
        val = self.valuation(code)
        quality = self.quality(code)
        flow = self.fundflow(code, days=5)
        context = self._build_context(code, snap, val, quality, flow)
        sent = self.sentiment(code)
        sent_str = (
            f"看多 {sent['bull']}% / 看空 {sent['bear']}% / 中性 {sent['neutral']}%"
            f"（样本 {sent['samples']} 条）\n整体倾向：{sent.get('summary', '')}"
        )
        answer = chat(build_assistant_prompt(question, context, sent_str))
        return {"answer": answer, "sentiment": sent, "context": context}

    # ---------- 私有：上下文 / 文本 / AI 抽取 ----------
    def _build_context(self, code: str, snap: dict, val: dict, quality: dict, flow: dict) -> str:
        lines = []
        if snap:
            lines.append(f"股票：{snap.get('名称')}({snap.get('代码')})")
            amt = snap.get("成交额")
            amt_str = f"{amt/1e8:.2f} 亿" if amt else "未知"
            lines.append(f"最新价 {snap.get('最新价')}，涨跌幅 {snap.get('涨跌幅')}%，成交额 {amt_str}")
        if val:
            parts = []
            for key in ("pe", "pb", "ps", "pcf"):
                v = val.get(key, {})
                if v.get("value") is not None:
                    parts.append(f"{key.upper()}={v['value']:.2f}(历史分位 {v.get('pct')}%)")
            if parts:
                lines.append("估值：" + "，".join(parts))
        if quality:
            parts = []
            for key in ("roe", "gross_margin", "net_margin", "revenue_growth", "profit_growth"):
                item = quality.get(key)
                if item and item.get("latest") is not None:
                    parts.append(f"{item['label']}={item['latest']:.2f}%")
            if parts:
                lines.append("盈利质量：" + "，".join(parts))
        if flow:
            parts = []
            net = flow.get("资金流入净额")
            if net is not None:
                parts.append(f"资金流入净额 {net/1e8:.2f} 亿")
            if flow.get("阶段涨跌幅") is not None:
                parts.append(f"阶段涨跌幅 {flow['阶段涨跌幅']:.2f}%")
            if flow.get("连续换手率") is not None:
                parts.append(f"连续换手率 {flow['连续换手率']:.2f}%")
            if parts:
                lines.append("资金面（近 5 日）：" + "，".join(parts))
        return "\n".join(lines) if lines else "（无可用数据）"

    def _financial_text(self, quality: dict, financials: pd.DataFrame) -> str:
        dates = quality.get("dates") or []
        recent = min(3, len(dates))
        parts = []
        for key in ("roe", "gross_margin", "net_margin", "revenue_growth", "profit_growth"):
            item = quality.get(key)
            if item and item.get("series"):
                series = item["series"][-recent:]
                ds = dates[-recent:]
                pairs = ", ".join(f"{d}: {v:.2f}%" for d, v in zip(ds, series) if v is not None)
                parts.append(f"{item['label']}: {pairs}")
        eps_col = find_col(financials, ["摊薄每股收益", "加权每股收益", "每股收益"])
        if eps_col:
            eps = pd.to_numeric(financials[eps_col], errors="coerce").tail(recent).tolist()
            ds = dates[-recent:]
            parts.append("每股收益(元): " + ", ".join(f"{d}: {v:.2f}" for d, v in zip(ds, eps) if pd.notna(v)))
        return "\n".join(parts) if parts else "（无财务数据）"

    def _financial_analyze(self, financials_text: str, forecast_text: str) -> dict:
        user = (
            "以下是某 A 股公司最近几个报告期的财务数据与券商盈利预测，请做财报速解。"
            "以 JSON 输出："
            '{"summary":"本期业绩一句话总结","vs_consensus":"相对一致预期: 超预期/符合/低于预期/无法判断",'
            '"vs_last_year":"相对上年同期变化","guidance":"管理层指引变化(数据中无则写: 未披露)",'
            '"risk":"需关注的风险点"}'
            f"\n\n【财务数据（最近报告期，含历史对比）】\n{financials_text}\n\n"
            f"【券商盈利预测(一致预期近似)】\n{forecast_text}"
        )
        messages = [{"role": "system", "content": SYSTEM + " 只输出 JSON。"}, {"role": "user", "content": user}]
        return chat_json(messages)

    def _analyze_batch(self, titles: list) -> list:
        user = (
            "下面是某 A 股公司近期的公告标题列表，请对每条公告判断：类型、核心变化、是否为实质性变化"
            "（实质性变化指：增减发/股权变动/高管离职/定增/股权激励/重大资产重组等对股价有实质影响的事项）。"
            "以 JSON 输出："
            '{"results":[{"title":"原标题","category":"公告类型","core_change":"一句话核心变化",'
            '"substantive":"是/否"}]}\n\n'
            "公告标题：\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        )
        messages = [{"role": "system", "content": SYSTEM + " 只输出 JSON。"}, {"role": "user", "content": user}]
        data = chat_json(messages)
        return data.get("results", []) if data else []


_engine = None


def get_engine() -> ResearchEngine:
    """全局引擎单例。"""
    global _engine
    if _engine is None:
        _engine = ResearchEngine()
    return _engine
