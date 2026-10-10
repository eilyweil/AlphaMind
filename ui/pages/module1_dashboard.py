"""模块1：股票数据仪表盘。"""
import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.engine import get_engine


@st.cache_data(ttl=600, show_spinner="加载数据中...")
def _fetch(code: str, start: str, end: str) -> dict:
    e = get_engine()
    return {
        "valuation": e.valuation(code),
        "quality": e.quality(code),
        "fundflow": e.fundflow(code),
        "history": e.history(code, start, end),
    }


def _hist_chart(df: pd.DataFrame) -> go.Figure:
    if df is None or df.empty:
        return None
    df = df.copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线", increasing_line_color="#e5484d", decreasing_line_color="#2f9e63",
    ))
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"], name="成交量", yaxis="y2",
        marker_color="rgba(110,110,115,0.35)",
    ))
    fig.update_layout(
        height=420, xaxis_rangeslider_visible=False,
        yaxis2=dict(overlaying="y", side="right", showgrid=False, showticklabels=False),
        margin=dict(l=10, r=10, t=25, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )
    return fig


def _quality_chart(quality: dict) -> go.Figure:
    if not quality or "dates" not in quality:
        return None
    fig = go.Figure()
    dates = quality.get("dates") or []
    for key in ("roe", "gross_margin", "net_margin"):
        item = quality.get(key)
        if not item or not item.get("series"):
            continue
        fig.add_trace(go.Scatter(x=dates, y=item["series"], mode="lines+markers", name=item["label"]))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=25, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0))
    return fig


def _fmt_yi(v):
    return f"{v/1e8:.2f}亿" if v is not None else "-"


def _fmt_wan(v):
    return f"{v/1e6:.2f}万手" if v is not None else "-"


def render(code: str):
    end = dt.date.today().strftime("%Y-%m-%d")
    start = (dt.date.today() - dt.timedelta(days=365)).strftime("%Y-%m-%d")
    data = _fetch(code, start, end)

    # ---- 1. 估值指标（最新价/涨跌幅已由顶部行情看板展示）----
    st.subheader("估值指标（历史分位，近一年）")
    val = data["valuation"]
    if val:
        cols = st.columns(4)
        for i, key in enumerate(["pe", "pb", "ps", "pcf"]):
            v = val.get(key, {})
            val_str = f"{v['value']:.2f}" if v.get("value") is not None else "暂无"
            pct = v.get("pct")
            delta = f"历史分位 {pct}%" if pct is not None else None
            cols[i].metric(f"{key.upper()}", val_str, delta)
        if val.get("date"):
            st.caption(f"估值数据截至：{val['date']}（数据来源：百度股市通）")
    else:
        st.info("暂无估值数据")

    # ---- 2. 盈利质量 ----
    st.subheader("盈利质量")
    quality = data["quality"]
    if quality:
        c2 = st.columns(5)
        for i, key in enumerate(["roe", "gross_margin", "net_margin", "revenue_growth", "profit_growth"]):
            item = quality.get(key)
            label = item["label"] if item else key
            val_str = f"{item['latest']:.2f}%" if item and item.get("latest") is not None else "-"
            c2[i].metric(label, val_str)
        fig = _quality_chart(quality)
        if fig:
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("暂无财务数据")

    # ---- 3. 资金面 ----
    st.subheader("资金面（近 5 日）")
    flow = data["fundflow"]
    if flow:
        c3 = st.columns(3)
        c3[0].metric("资金流入净额", _fmt_yi(flow["资金流入净额"]))
        c3[1].metric("阶段涨跌幅", f"{flow['阶段涨跌幅']}%" if flow["阶段涨跌幅"] is not None else "-")
        c3[2].metric("连续换手率", f"{flow['连续换手率']}%" if flow["连续换手率"] is not None else "-")
        st.caption("数据来源：同花顺资金流向（5 日排行）")
    else:
        st.info("暂无资金流数据")

    # ---- 4. 股价走势 ----
    st.subheader("股价走势与成交量（近一年，前复权）")
    fig = _hist_chart(data["history"])
    if fig:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("暂无行情数据")
