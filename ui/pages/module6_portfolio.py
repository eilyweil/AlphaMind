"""模块6：组合总览（多持仓明细 + 集中度 + 组合综合评估）。"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _fmt_money(v):
    return f"{v / 1e4:.2f} 万" if v is not None else "—"


def _overview_table(ov: dict) -> pd.DataFrame:
    rows = []
    for p in ov["positions"]:
        rows.append({
            "代码": p["code"],
            "名称": p["name"],
            "现价": f"{p['price']:.2f}" if p["price"] is not None else "—",
            "股数": int(p["shares"]) if p["shares"] else "—",
            "成本": f"{p['cost']:.2f}" if p["cost"] is not None else "—",
            "市值": _fmt_money(p["market_value"]),
            "权重": f"{p['weight'] * 100:.1f}%" if p.get("weight") is not None else "—",
            "浮盈亏": f"{p['pnl_pct'] * 100:+.2f}%" if p["pnl_pct"] is not None else "—",
        })
    return pd.DataFrame(rows)


def _weight_chart(ov: dict) -> go.Figure:
    labels = [p["name"] for p in ov["positions"]]
    values = [round((p.get("weight") or 0) * 100, 2) for p in ov["positions"]]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        textinfo="label+percent",
        marker=dict(colors=["#0066ff", "#7c9fe0", "#a9c1e8", "#c3cedd", "#5a8ae0", "#9db4d6"],
                    line=dict(color="#ffffff", width=1)),
    ))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=-0.25))
    return fig


def render(portfolio):
    ov = portfolio.overview()
    positions = ov["positions"]

    if not positions:
        st.info("暂无持仓。请在左侧「我的持仓」添加股票代码，即可查看组合明细与综合评估。")
        return

    st.markdown("#### 我的持仓组合")

    st.subheader("持仓明细")
    st.dataframe(_overview_table(ov), width="stretch", hide_index=True)

    st.subheader("组合汇总")
    c1 = st.columns(4)
    c1[0].metric("总市值", _fmt_money(ov["total_market_value"]) if ov["total_market_value"] else "等权")
    c1[1].metric("总成本", _fmt_money(ov["total_cost"]))
    c1[2].metric("整体浮盈亏", f"{ov['pnl_pct'] * 100:+.2f}%" if ov["pnl_pct"] is not None else "—")
    c1[3].metric("加权 PE 分位", f"{ov['weighted_pe_percentile']}%" if ov["weighted_pe_percentile"] is not None else "—")

    c2 = st.columns(3)
    c2[0].metric("HHI 集中度", f"{ov['hhi']:.4f}")
    c2[1].metric("第一大持仓占比", f"{ov['top1_weight'] * 100:.1f}%")
    c2[2].metric("持仓数量", f"{len(positions)} 只")
    st.caption("未填股数时按等权口径计算集中度与加权估值分位。")

    st.subheader("持仓集中度分布")
    st.plotly_chart(_weight_chart(ov), width="stretch")

    st.markdown("---")
    st.subheader("组合综合评估")
    include_sent = st.checkbox("纳入社区情绪（多一次批量分析，稍慢）", value=False)
    if st.button("生成组合研判", type="primary"):
        with st.spinner("正在聚合各持仓数据并研判..."):
            try:
                result = portfolio.overall_analysis(include_sentiment=include_sent)
            except Exception as ex:  # noqa: BLE001
                st.error(f"AI 调用失败：{ex}")
                return
        if not result:
            st.warning("AI 分析返回为空")
            return
        st.markdown(f"**组合概括**：{result.get('summary', '')}")
        st.markdown(f"**集中度风险**：{result.get('concentration_risk', '')}")
        st.markdown(f"**估值水平**：{result.get('valuation', '')}")
        st.markdown(f"**情绪面**：{result.get('sentiment', '')}")
        st.markdown(f"**主要风险**：{result.get('risk', '')}")
        st.markdown(f"**结论与观察**：{result.get('conclusion', '')}")
        st.caption("本平台输出为投资研究参考，不构成投资建议。")
