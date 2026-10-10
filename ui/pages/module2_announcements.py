"""模块2：公告快读（抓近30天公告 -> AI 提取核心变化 -> 高亮实质性变化）。"""
import streamlit as st

from core.engine import get_engine


def render(code: str):
    e = get_engine()
    with st.spinner("抓取近 30 天公告..."):
        anns = e.announcements(code, days=30)

    if anns is None or anns.empty:
        st.info("暂无公告数据（接口可能较慢或该股票近期无公告）")
        return

    title_col = "公告标题" if "公告标题" in anns.columns else None
    date_col = "公告日期" if "公告日期" in anns.columns else None
    if title_col is None:
        st.info("公告数据格式异常")
        return

    titles = anns[title_col].astype(str).tolist()
    dates = anns[date_col].astype(str).tolist() if date_col else [""] * len(titles)

    st.subheader(f"近 30 天公告（{len(titles)} 条）")

    if st.button("AI 提取核心变化", type="primary"):
        with st.spinner("AI 分析中..."):
            try:
                results = e.announcement_analysis(code, days=30, max_items=20)
            except Exception as ex:  # noqa: BLE001
                st.error(f"AI 调用失败：{ex}")
                return

        if not results:
            st.warning("AI 分析返回为空")
            return

        for i, r in enumerate(results):
            substantive = r.get("substantive", "否") == "是"
            title = r.get("title", titles[i] if i < len(titles) else "")
            category = r.get("category", "")
            core = r.get("core_change", "")
            if substantive:
                st.markdown(f"### {title}")
                st.markdown(f"**类型**：`{category}`　**核心变化**：{core}")
                st.markdown("**:red[实质性变化]**")
            else:
                st.markdown(f"**{title}**")
                st.markdown(f"类型：`{category}`　核心变化：{core}")
            st.markdown("---")
