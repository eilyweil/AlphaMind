"""模块5：策略回测（技术指标个股 + 沪深300 截面动量组合）。"""
import plotly.graph_objects as go
import streamlit as st

from analysis import backtest as bt
from analysis import factor_backtest as ft
from core.engine import get_engine

_PERIODS = {"近 1 年": 365, "近 2 年": 730, "近 3 年": 1095, "近 5 年": 1825}

# 各策略参数：(key, 标签, 最小, 最大, 默认, 步长)
_PARAM_UI = {
    "双均线（MA）": [("short", "短周期", 2, 30, 5, 1), ("long", "长周期", 10, 120, 20, 1)],
    "MACD": [("fast", "快线 EMA", 8, 20, 12, 1), ("slow", "慢线 EMA", 20, 40, 26, 1),
             ("signal", "信号线", 5, 15, 9, 1)],
    "RSI 超买超卖": [("period", "RSI 周期", 6, 30, 14, 1), ("low", "超卖阈值", 10, 40, 30, 1),
                    ("high", "超买阈值", 60, 90, 70, 1)],
    "布林带（BOLL）": [("period", "周期", 10, 60, 20, 1), ("k", "标准差倍数", 1.0, 3.0, 2.0, 0.5)],
}

# 因子回测固定区间与参数
_FACTOR_START = "2015-01-01"
_FACTOR_END = "2025-12-31"
_WINDOWS = {"12-1（经典）": "12-1", "6-1": "6-1", "12-6": "12-6"}
_BENCHMARKS = {"全收益 H00300（推荐）": "total_return", "价格指数 000300": "price"}
_STRATEGIES = {
    "多因子增强（动量+低波+趋势风控）（推荐）": "enhanced",
    "经典 12-1 动量": "momentum",
}
# 风险偏好 → 波动率目标（年化）
_RISK = {"保守（10%）": 0.10, "均衡（15%）": 0.15, "进取（20%）": 0.20}


def _pct(v):
    return f"{v * 100:+.2f}%" if v is not None else "-"


# ---------- 技术指标（个股） ----------
def _equity_chart(df) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["equity"], name="策略净值",
                             line=dict(color="#0066ff", width=2.2)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["bench"], name="买入持有",
                             line=dict(color="#c3cedd", width=1.6, dash="dash")))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0),
                      yaxis_title="净值（元）", hovermode="x unified")
    return fig


def _trade_chart(df, buy_idx, sell_idx) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线", increasing_line_color="#e5484d", decreasing_line_color="#2f9e63",
    ))
    if buy_idx:
        fig.add_trace(go.Scatter(
            x=df["date"].iloc[buy_idx], y=df["low"].iloc[buy_idx] * 0.98,
            mode="markers", name="买入",
            marker=dict(symbol="triangle-up", color="#e5484d", size=12, line=dict(width=1, color="white")),
        ))
    if sell_idx:
        fig.add_trace(go.Scatter(
            x=df["date"].iloc[sell_idx], y=df["high"].iloc[sell_idx] * 1.02,
            mode="markers", name="卖出",
            marker=dict(symbol="triangle-down", color="#2f9e63", size=12, line=dict(width=1, color="white")),
        ))
    fig.update_layout(height=420, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0),
                      hovermode="x unified")
    return fig


def _render_technical_result(res: dict):
    m = res["metrics"]
    c1 = st.columns(4)
    c1[0].metric("总收益率", _pct(m["总收益率"]))
    c1[1].metric("年化收益率", _pct(m["年化收益率"]))
    c1[2].metric("最大回撤", f"{m['最大回撤'] * 100:.2f}%")
    c1[3].metric("夏普比率", f"{m['夏普比率']:.2f}")

    c2 = st.columns(4)
    c2[0].metric("交易次数", f"{m['交易次数']} 次")
    c2[1].metric("胜率", f"{m['胜率'] * 100:.1f}%")
    c2[2].metric("买入持有收益", _pct(m["买入持有收益"]))
    c2[3].metric("期末资金", f"{m['期末资金'] / 1e4:.2f} 万")
    st.caption(f"回测 {m['回测天数']} 个交易日 · 前复权 · 单边佣金万 2.5 · 全仓买卖")

    diff = m["总收益率"] - m["买入持有收益"]
    sign = "跑赢" if diff >= 0 else "跑输"
    st.markdown(f"**策略 {sign} 买入持有 {abs(diff) * 100:.2f} 个百分点**")

    st.subheader("净值曲线（策略 vs 买入持有）")
    st.plotly_chart(_equity_chart(res["df"]), width="stretch")

    st.subheader("K 线 · 买卖点标注")
    st.plotly_chart(_trade_chart(res["df"], res["buy_idx"], res["sell_idx"]), width="stretch")

    if st.button("AI 解读回测结果"):
        with st.spinner("AI 分析中..."):
            try:
                answer = get_engine().backtest_interpretation(res)
            except Exception as ex:  # noqa: BLE001
                st.error(f"AI 调用失败：{ex}")
                return
        st.markdown(answer)


def _render_technical(code: str):
    st.markdown("#### 选择一个策略回测历史表现，验证「分析 → 决策」闭环")

    c1, c2, c3 = st.columns([1.3, 1.1, 1.1])
    with c1:
        strategy = st.selectbox("策略", list(bt.STRATEGIES.keys()))
    with c2:
        period = st.selectbox("回测区间", list(_PERIODS.keys()), index=1)
    with c3:
        initial_wan = st.number_input("初始资金（万元）", 1, 1000, 10, step=1)

    params = {}
    specs = _PARAM_UI[strategy]
    pcols = st.columns(len(specs))
    for i, (key, label, lo, hi, default, step) in enumerate(specs):
        params[key] = pcols[i].slider(label, lo, hi, default, step=step)

    if st.button("开始回测", type="primary"):
        result = get_engine().backtest(code, strategy, params, _PERIODS[period], initial_wan)
        if result is None:
            st.warning("该标的行情数据不足（<40 个交易日），无法回测，请换标的或拉长区间")
            return
        st.session_state["bt"] = result

    if "bt" in st.session_state:
        _render_technical_result(st.session_state["bt"])


# ---------- 因子动量（沪深300 组合） ----------
def _factor_nav_chart(nav, log=True, bench_label="沪深300") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=nav["date"], y=nav["strategy"], name="策略",
                             line=dict(color="#0066ff", width=2.2)))
    fig.add_trace(go.Scatter(x=nav["date"], y=nav["bench"], name=bench_label,
                             line=dict(color="#c3cedd", width=1.6)))
    fig.update_layout(height=380, yaxis_type="log" if log else "linear",
                      yaxis_title="净值（对数轴）" if log else "净值（元）",
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0),
                      hovermode="x unified")
    return fig


def _factor_excess_chart(nav) -> go.Figure:
    s = nav["strategy"] / nav["strategy"].iloc[0]
    b = nav["bench"] / nav["bench"].iloc[0]
    excess = s - b
    color = "#e5484d" if excess.iloc[-1] >= 0 else "#2f9e63"
    fig = go.Figure(go.Scatter(x=nav["date"], y=excess, name="累计超额",
                               line=dict(color=color, width=1.8)))
    fig.add_hline(y=0, line=dict(color="#c3cedd", width=1))
    fig.update_layout(height=300, yaxis_title="累计超额（归一化净值差）",
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
    return fig


def _factor_dd_chart(nav, bench_label="基准") -> go.Figure:
    dds = (nav["strategy"] / nav["strategy"].cummax() - 1) * 100
    ddb = (nav["bench"] / nav["bench"].cummax() - 1) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=nav["date"], y=dds, name="策略回撤",
                             fill="tozeroy", line=dict(color="#e5484d", width=1.2)))
    fig.add_trace(go.Scatter(x=nav["date"], y=ddb, name=f"{bench_label}回撤",
                             line=dict(color="#c3cedd", width=1.2)))
    fig.update_layout(height=300, yaxis_title="回撤（%）",
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0),
                      hovermode="x unified")
    return fig


def _factor_sens_chart(sens: dict) -> go.Figure:
    fig = go.Figure()
    for slip_bp, item in sens.items():
        fig.add_trace(go.Scatter(x=item["nav"]["date"], y=item["nav"]["strategy"],
                                 name=f"{slip_bp} bp", line=dict(width=1.8)))
    fig.update_layout(height=360, yaxis_type="log", yaxis_title="净值（对数轴）",
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0),
                      hovermode="x unified")
    return fig


def _render_factor_result(res: dict, sens=None, benchmark: str = "total_return"):
    m = res["metrics"]
    total_return = benchmark == "total_return"
    bench_label = "沪深300全收益" if total_return else "沪深300"
    strategy = res.get("strategy", "enhanced")
    if strategy == "enhanced":
        st.markdown("**策略：多因子增强** —— 质量动量（动量+低波）选股 · 趋势风控 · 波动率目标")
    else:
        st.markdown("**策略：经典 12-1 动量** —— 纯动量，等权持有")
    st.markdown("#### 指标汇总")
    c1 = st.columns(4)
    c1[0].metric("年化超额", _pct(m["年化超额"]))
    c1[1].metric("年化收益率", _pct(m["年化收益率"]))
    c1[2].metric("夏普比率", f"{m['夏普比率']:.2f}")
    c1[3].metric("最大回撤", f"{m['最大回撤'] * 100:.2f}%")
    c2 = st.columns(4)
    c2[0].metric("年化波动", f"{m['年化波动'] * 100:.2f}%")
    c2[1].metric("Calmar", f"{m['Calmar']:.2f}")
    c2[2].metric("月胜率", f"{m['月胜率'] * 100:.1f}%")
    c2[3].metric("单边年换手", f"{m['单边年换手']:.1f} 倍")
    if total_return:
        st.caption("基准为沪深300全收益指数(H00300，含股息再投)，与策略前复权口径一致。首末年份为不完整年度。")
    else:
        st.caption("基准为沪深300价格指数(000300)；策略按前复权含股息再投，超额含约2%/年的股息口径差。首末年份为不完整年度。")

    checks = ft.pass_fail(m)
    passed = sum(1 for _, ok in checks if ok)
    verdict = "✅ 通过" if passed == len(checks) else f"❌ 未通过（{passed}/{len(checks)}）"
    st.markdown(f"**结论：{verdict}**")
    for desc, ok in checks:
        st.markdown(f"{'✅' if ok else '❌'} {desc}")

    st.subheader(f"净值曲线（对数轴 · 策略 vs {bench_label}）")
    st.plotly_chart(_factor_nav_chart(res["nav"], log=True, bench_label=bench_label), width="stretch")

    st.subheader("累计超额收益")
    st.plotly_chart(_factor_excess_chart(res["nav"]), width="stretch")

    st.subheader(f"回撤（策略 vs {bench_label}）")
    st.plotly_chart(_factor_dd_chart(res["nav"], bench_label=bench_label), width="stretch")

    st.subheader("分年度收益")
    ann = res["annual"].copy()
    for col in ["策略", "基准", "超额"]:
        ann[col] = (ann[col] * 100).round(2)
    st.dataframe(ann, hide_index=True, width="stretch")

    if sens:
        st.subheader("成本敏感性（四档滑点 0/15/30/50 bp）")
        st.plotly_chart(_factor_sens_chart(sens), width="stretch")
        rows = [{"滑点(bp)": bp, "夏普": f"{it['夏普']:.2f}",
                 "年化": _pct(it["年化"]), "最大回撤": f"{it['最大回撤'] * 100:.2f}%"}
                for bp, it in sens.items()]
        st.dataframe(rows, hide_index=True, width="stretch")


def _render_factor():
    st.markdown("#### 沪深300 截面组合（月频 · 等权 · 真实成本）")
    st.caption("月末按因子排序选前 N 只，次月首日开盘等权买入。数据为当前成分近似（含幸存者偏差），结论口径已注明。")

    c1, c2, c3 = st.columns(3)
    with c1:
        strategy_label = st.selectbox("策略", list(_STRATEGIES.keys()))
    with c2:
        top_n = st.selectbox("选股数", [20, 30, 50], index=1)
    with c3:
        window = st.selectbox("动量窗口", list(_WINDOWS.keys()))

    c4, c5, c6 = st.columns(3)
    with c4:
        benchmark_label = st.selectbox("基准口径", list(_BENCHMARKS.keys()))
    with c5:
        risk_label = st.selectbox("风险偏好", list(_RISK.keys()), index=1)
    with c6:
        initial_wan = st.number_input("初始资金（万元）", 10, 10000, 100, step=10)

    strategy = _STRATEGIES[strategy_label]
    benchmark = _BENCHMARKS[benchmark_label]
    vol_target = _RISK[risk_label]

    sensitivity = st.checkbox("同时跑四档成本敏感性（0/15/30/50 bp）", value=False)

    if st.button("开始回测", type="primary", key="run_factor"):
        with st.spinner("拉取沪深300成分股历史行情并回测（首次约几分钟，之后缓存秒开）…"):
            bar = st.progress(0.0, text="拉取历史行情…")

            def prog(done, total):
                bar.progress(min(done / total, 1.0), text=f"拉取历史行情 {done}/{total}")

            try:
                result = get_engine().factor_backtest(
                    _FACTOR_START, _FACTOR_END, top_n=top_n,
                    window=_WINDOWS[window], initial_wan=initial_wan, progress=prog,
                    benchmark=benchmark, strategy=strategy, vol_target=vol_target,
                )
                sens = None
                if sensitivity:
                    sens = get_engine().factor_backtest_sensitivity(
                        _FACTOR_START, _FACTOR_END, top_n=top_n,
                        window=_WINDOWS[window], initial_wan=initial_wan, progress=prog,
                        benchmark=benchmark, strategy=strategy, vol_target=vol_target,
                    )
            except Exception as ex:  # noqa: BLE001
                st.error(f"回测失败：{ex}")
                bar.empty()
                return
            bar.empty()

        if result is None:
            st.warning("数据不足，无法回测")
            return
        st.session_state["factor_bt"] = {"res": result, "sens": sens, "benchmark": benchmark}

    if "factor_bt" in st.session_state:
        _render_factor_result(
            st.session_state["factor_bt"]["res"], st.session_state["factor_bt"]["sens"],
            st.session_state["factor_bt"].get("benchmark", "total_return"),
        )


def render(code: str):
    mode = st.radio("回测模式", ["技术指标（个股）", "因子动量（沪深300）"], horizontal=True)
    if mode == "因子动量（沪深300）":
        _render_factor()
    else:
        _render_technical(code)
