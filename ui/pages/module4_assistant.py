"""模块4：AI 研报助手（智能体：自然语言 → 多轮工具调用 → 可视化推理轨迹 + 社区情绪）。"""
import html

import streamlit as st

from agent.loop import run_traced
from core.engine import get_engine

_QUICK = ["当前估值贵吗？", "现在适合买入吗？", "这家公司赚钱能力如何？", "近期有什么风险？"]

_TOOL_LABELS = {
    "snapshot": "实时行情",
    "valuation": "估值分位",
    "quality": "盈利质量",
    "fundflow": "资金面",
    "financial_analysis": "财报速解",
    "announcement_analysis": "公告快读",
    "sentiment": "社区情绪",
    "backtest": "策略回测",
    "report": "综合研判",
    "portfolio_overview": "组合全景",
    "portfolio_analysis": "组合研判",
}

# 每个工具的抽象配色（信号流画风：冷色系光谱，语义化点缀）
_TOOL_COLORS = {
    "snapshot": "#0066ff",
    "valuation": "#0891b2",
    "quality": "#0d9488",
    "fundflow": "#6366f1",
    "financial_analysis": "#8b5cf6",
    "announcement_analysis": "#0284c7",
    "sentiment": "#e5484d",
    "backtest": "#d97706",
    "report": "#0b1220",
    "portfolio_overview": "#475569",
    "portfolio_analysis": "#059669",
}
_DEFAULT_COLOR = "#0066ff"


def _clip(s, n=42):
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def _summarize(name: str, result) -> str:
    """把每个工具的结构化返回压成一行「人话摘要」，替代前台直接裸露 JSON。"""
    if isinstance(result, dict) and "error" in result:
        return f"调用失败：{result['error']}"

    # 公告快读返回 list，先单独处理
    if name == "announcement_analysis":
        items = result if isinstance(result, list) else []
        n = len(items)
        subs = sum(1 for x in items if isinstance(x, dict) and x.get("substantive") == "是")
        if not n:
            return "未抓取到公告"
        s = f"共 {n} 条公告 · {subs} 条实质性变化"
        first = items[0].get("title", "") if isinstance(items[0], dict) else ""
        if first:
            s += f" · 如《{_clip(first, 18)}》"
        return s

    if not isinstance(result, dict):
        return _clip(str(result)) if result not in (None, "", [], {}) else "完成"

    if name == "snapshot":
        parts = []
        if result.get("名称"):
            parts.append(str(result["名称"]))
        if result.get("最新价") is not None:
            parts.append(f"{result['最新价']:.2f}")
        if result.get("涨跌幅") is not None:
            parts.append(f"{result['涨跌幅']:+.2f}%")
        if result.get("成交额"):
            parts.append(f"成交额 {result['成交额']/1e8:.2f} 亿")
        return " · ".join(parts) or "已获取实时行情"

    if name == "valuation":
        parts = []
        for k in ("pe", "pb", "ps", "pcf"):
            v = result.get(k) or {}
            if v.get("value") is not None:
                pct = f" 分位{v['pct']}%" if v.get("pct") is not None else ""
                parts.append(f"{k.upper()} {v['value']:.2f}{pct}")
        return " · ".join(parts) or "已获取估值数据"

    if name == "quality":
        parts = []
        for k in ("roe", "gross_margin", "net_margin", "revenue_growth", "profit_growth"):
            item = result.get(k)
            if item and item.get("latest") is not None:
                parts.append(f"{item.get('label', k)} {item['latest']:.2f}%")
        return " · ".join(parts) or "已获取盈利质量"

    if name == "fundflow":
        parts = []
        net = result.get("资金流入净额")
        if net is not None:
            parts.append(f"净流入 {net/1e8:+.2f} 亿")
        if result.get("阶段涨跌幅") is not None:
            parts.append(f"阶段 {result['阶段涨跌幅']:+.2f}%")
        return " · ".join(parts) or "已获取资金面"

    if name == "financial_analysis":
        s = result.get("summary")
        return _clip(s) if s else "已生成财报速解"

    if name == "sentiment":
        b, r, neu, samples = result.get("bull"), result.get("bear"), result.get("neutral"), result.get("samples")
        if b is not None:
            s = f"看多 {b}% · 看空 {r}% · 中性 {neu}%"
            if samples:
                s += f"（样本 {samples} 条）"
            return s
        return "已获取社区情绪"

    if name == "backtest":
        m = result.get("metrics") or {}
        parts = []
        if m.get("总收益率") is not None:
            parts.append(f"总收益 {m['总收益率']*100:+.2f}%")
        if m.get("最大回撤") is not None:
            parts.append(f"最大回撤 {m['最大回撤']*100:.2f}%")
        if m.get("夏普比率") is not None:
            parts.append(f"夏普 {m['夏普比率']:.2f}")
        return " · ".join(parts) or "已完成回测"

    if name == "report":
        return "已聚合基本面与情绪，生成综合研判"

    if name == "portfolio_overview":
        pos = result.get("positions") or []
        parts = [f"{len(pos)} 只持仓"]
        mv = result.get("total_market_value")
        if mv:
            parts.append(f"总市值 {mv/1e4:.2f} 万")
        parts.append(f"集中度 {result.get('hhi', 0)}")
        return " · ".join(parts)

    if name == "portfolio_analysis":
        s = result.get("summary")
        return _clip(s) if s else "已生成组合研判"

    return "完成"


def _render_trace(trace: list) -> None:
    st.markdown(
        f'<div class="trace-head">智能体推理轨迹 · 共 {len(trace)} 次工具调用</div>',
        unsafe_allow_html=True,
    )
    if not trace:
        st.caption("本次回答未调用工具，智能体直接作答。")
        return

    # 只展示「人话摘要」，不再把结构化 JSON 暴露到前台
    cards = []
    for i, t in enumerate(trace, 1):
        name = t.get("name", "?")
        label = _TOOL_LABELS.get(name, name)
        summ = html.escape(_summarize(name, t.get("result")))
        is_err = isinstance(t.get("result"), dict) and "error" in t.get("result")
        c = _TOOL_COLORS.get(name, _DEFAULT_COLOR)
        cards.append(
            f'<div class="tstep" style="--c:{c};--c-soft:{c}1f;animation-delay:{i * 60}ms">'
            f'<div class="tnode">{i}</div>'
            f'<div class="tbody"><div class="trow">'
            f'<span class="ttool">{html.escape(name)}</span>'
            f'<span class="tlabel">{html.escape(label)}</span></div>'
            f'<div class="tsum{" err" if is_err else ""}">{summ}</div></div>'
            f'</div>'
        )
    st.markdown('<div class="tl">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def _render_sentiment(sent: dict) -> None:
    bull = sent.get("bull", 0)
    bear = sent.get("bear", 0)
    neutral = sent.get("neutral", 0)
    st.markdown(
        f"""
        <div class="sentiment">
          <div class="sent-mascots">
            <div class="sent-side">
              <svg class="mascot" viewBox="0 0 72 72" role="img" aria-label="牛市 · 看多">
                <path d="M15 26 C11 15 19 8 26 12 C27 17 27 22 25 26 Z" fill="#f2d07c"/>
                <path d="M57 26 C61 15 53 8 46 12 C45 17 45 22 47 26 Z" fill="#f2d07c"/>
                <ellipse cx="16" cy="36" rx="7.5" ry="10" fill="#d8554f" transform="rotate(-16 16 36)"/>
                <ellipse cx="56" cy="36" rx="7.5" ry="10" fill="#d8554f" transform="rotate(16 56 36)"/>
                <ellipse cx="36" cy="42" rx="23" ry="21" fill="#f0a0a4"/>
                <ellipse cx="36" cy="50" rx="12.5" ry="9.5" fill="#fbe2e2"/>
                <circle cx="31" cy="50" r="1.7" fill="#c94a4d"/>
                <circle cx="41" cy="50" r="1.7" fill="#c94a4d"/>
                <path d="M30 46 Q36 51 42 46" stroke="#c94a4d" stroke-width="2" fill="none" stroke-linecap="round"/>
                <circle cx="28" cy="36" r="3" fill="#4a2f2f"/>
                <circle cx="44" cy="36" r="3" fill="#4a2f2f"/>
                <circle cx="29.1" cy="34.9" r="1" fill="#fff"/>
                <circle cx="45.1" cy="34.9" r="1" fill="#fff"/>
                <circle cx="23" cy="42" r="3.2" fill="#e97a7d" opacity=".45"/>
                <circle cx="49" cy="42" r="3.2" fill="#e97a7d" opacity=".45"/>
              </svg>
              <div class="sent-num up">{bull}%</div>
              <div class="sent-label">看多</div>
            </div>
            <div class="sent-vs">牛熊对决</div>
            <div class="sent-side">
              <svg class="mascot" viewBox="0 0 72 72" role="img" aria-label="熊市 · 看空">
                <circle cx="20" cy="22" r="10.5" fill="#7cc49c"/>
                <circle cx="20" cy="22" r="5" fill="#b7e2c9"/>
                <circle cx="52" cy="22" r="10.5" fill="#7cc49c"/>
                <circle cx="52" cy="22" r="5" fill="#b7e2c9"/>
                <circle cx="36" cy="42" r="22" fill="#7cc49c"/>
                <ellipse cx="36" cy="50" rx="12.5" ry="9.5" fill="#e3f4e9"/>
                <ellipse cx="36" cy="46.5" rx="3.3" ry="2.5" fill="#3a6b4f"/>
                <path d="M36 49 L36 52" stroke="#3a6b4f" stroke-width="1.7" stroke-linecap="round"/>
                <path d="M32 52 Q36 56 40 52" stroke="#3a6b4f" stroke-width="1.7" fill="none" stroke-linecap="round"/>
                <circle cx="28" cy="36" r="3" fill="#3a2a2a"/>
                <circle cx="44" cy="36" r="3" fill="#3a2a2a"/>
                <circle cx="29.1" cy="34.9" r="1" fill="#fff"/>
                <circle cx="45.1" cy="34.9" r="1" fill="#fff"/>
                <circle cx="23" cy="43" r="3.2" fill="#5aa578" opacity=".35"/>
                <circle cx="49" cy="43" r="3.2" fill="#5aa578" opacity=".35"/>
              </svg>
              <div class="sent-num down">{bear}%</div>
              <div class="sent-label">看空</div>
            </div>
          </div>
          <div class="sent-bar"><span style="width:{bull}%"></span></div>
          <div class="sent-labels">
            <span class="up">看多 {bull}%</span>
            <span class="muted">中性 {neutral}%</span>
            <span class="down">看空 {bear}%</span>
          </div>
        </div>
        <p class="sent-caption">样本 {sent.get('samples', 0)} 条 · 东方财富股吧</p>
        """,
        unsafe_allow_html=True,
    )
    if sent.get("views"):
        st.markdown("**代表观点**")
        for v in sent["views"]:
            st.markdown(f"- `{v.get('sentiment', '')}`　{v.get('title', '')}")


def _extract_sentiment(trace: list):
    """优先复用轨迹里智能体已调用的 sentiment 结果，避免重复抓取。"""
    for t in trace:
        if t.get("name") == "sentiment":
            result = t.get("result")
            if isinstance(result, dict) and "bull" in result:
                return result
    return None


def render(code: str):
    st.markdown("#### 用自然语言提问，智能体自动调用投研工具，逐步推理并给出研判")

    if "q" not in st.session_state:
        st.session_state.q = ""

    quick = st.columns(len(_QUICK))
    for i, qs in enumerate(_QUICK):
        if quick[i].button(qs, key=f"quick_{i}"):
            st.session_state.q = qs

    question = st.text_area(
        "你的问题",
        key="q",
        height=130,
        placeholder="例如：这只股票当前估值贵吗？现在适合买入吗？",
    )

    if st.button("生成研判", type="primary"):
        if not question.strip():
            st.warning("请先输入问题")
            return

        prompt = question.strip()
        if code:
            prompt = f"当前 Web 页面选中的分析标的是 {code}。{prompt}"

        with st.spinner("智能体正在调用投研工具推理…"):
            try:
                out = run_traced(prompt, max_steps=5)
            except Exception as ex:  # noqa: BLE001
                st.error(f"智能体调用失败：{ex}")
                return

        # 持久化到 session_state，避免任意交互导致轨迹与结论消失
        st.session_state["agent_result"] = {"out": out, "code": code}

    res = st.session_state.get("agent_result")
    if not res or res.get("code") != code:
        return

    trace = res["out"].get("trace") or []
    answer = res["out"].get("answer") or ""

    _render_trace(trace)

    st.markdown("#### 研判结论")
    st.markdown(answer)

    st.markdown("---")
    st.subheader("社区情绪（东方财富股吧）")
    sent = _extract_sentiment(trace)
    if sent is None:
        with st.spinner("抓取社区情绪…"):
            try:
                sent = get_engine().sentiment(code)
            except Exception:  # noqa: BLE001
                sent = None
    if sent:
        _render_sentiment(sent)
    else:
        st.info("暂无社区情绪数据")
