"""模块3：财报速解（本期业绩 vs 一致预期 vs 上年同期 + 管理层指引）。"""
import pandas as pd
import streamlit as st

from core.engine import get_engine


@st.cache_data(ttl=300, show_spinner=False)
def _fetch(code: str) -> dict:
    return get_engine().financials(code)


def render(code: str):
    data = _fetch(code)
    quality = data["quality"]
    financials = data["financials"]
    forecast = data["forecast"]

    if quality:
        st.subheader("核心财务指标（最近各报告期）")
        df = pd.DataFrame({"报告期": quality.get("dates") or []})
        for key in ("roe", "gross_margin", "net_margin", "revenue_growth", "profit_growth"):
            item = quality.get(key)
            if item:
                df[item["label"]] = item.get("series")
        st.dataframe(df.tail(8), width="stretch", hide_index=True)

    if forecast is not None and not forecast.empty:
        st.subheader("券商盈利预测（一致预期近似）")
        st.dataframe(forecast, width="stretch", hide_index=True)
    else:
        st.info("暂无盈利预测数据")

    st.markdown("---")
    st.subheader("AI 财报速解")
    if st.button("生成财报速解", type="primary"):
        with st.spinner("AI 分析中..."):
            try:
                result = get_engine().financial_analysis(code)
            except Exception as ex:  # noqa: BLE001
                st.error(f"AI 调用失败：{ex}")
                return
        if not result:
            st.warning("AI 分析返回为空")
            return
        st.markdown(f"**业绩总结**：{result.get('summary', '')}")
        st.markdown(f"**相对一致预期**：{result.get('vs_consensus', '')}")
        st.markdown(f"**相对上年同期**：{result.get('vs_last_year', '')}")
        st.markdown(f"**管理层指引**：{result.get('guidance', '')}")
        st.markdown(f"**风险点**：{result.get('risk', '')}")
