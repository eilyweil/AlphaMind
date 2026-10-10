"""AlphaMind · 基于 AI 大模型的个人投研决策辅助平台（主入口）。

深色金融终端风格：顶部 Tab 导航 + 动态行情看板 + 侧边栏标的搜索。
"""
import streamlit as st

st.set_page_config(
    page_title="AlphaMind · 智能投研终端",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
/* ===== 设计 token（瑞士仪表 · 红涨绿跌） ===== */
:root {
    --bg: #f4f5f7; --surface: #ffffff; --ink: #1d1d1f; --ink-2: #6e6e73; --ink-3: #aeaeb2;
    --line: #e4e4e9; --line-strong: #d2d2d7; --surface-2: #fafbfc;
    --accent: #0066ff; --accent-ink: #0052cc; --accent-soft: #eaf1ff;
    --up: #e5484d; --down: #2f9e63; --navy: #0b1220;
}

/* ===== 全局 ===== */
html, body, .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-synthesis: none;
}
.stApp { background: var(--bg); color: var(--ink); }
.block-container { padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1280px; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: rgba(255,255,255,.72); backdrop-filter: saturate(180%) blur(20px); }
h4 { color: var(--ink-2); font-weight: 600; }

/* ===== 侧边栏 ===== */
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
.brand { font-size: 1.4rem; font-weight: 800; color: var(--ink); letter-spacing: -.01em; }
.brand .dot { color: var(--accent); }
.brand-sub { font-size: 0.82rem; color: var(--ink-2); margin-top: 0.15rem; line-height: 1.5; }
.nav-title { font-size: 0.72rem; letter-spacing: 1.5px; color: var(--ink-3); margin-bottom: 0.3rem; font-weight: 600; }

/* ===== 顶部行情看板（机构交易台 · 深色点睛） ===== */
.quote-bar {
    background: radial-gradient(120% 160% at 88% -20%, rgba(56,217,255,.14), transparent 55%),
                linear-gradient(135deg, #0b1220 0%, #0e1a30 55%, #0b1220 100%);
    border: 1px solid #1c2a44;
    border-radius: 16px;
    padding: 1.3rem 1.8rem;
    margin-bottom: 1.1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 2px 6px rgba(16,24,40,.06), 0 18px 44px rgba(16,24,40,.12);
    position: relative;
    overflow: hidden;
}
.quote-bar::before {
    content: "";
    position: absolute; inset: 0;
    background-image: linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
    background-size: 26px 26px;
    pointer-events: none;
}
.qb-main, .qb-stats { position: relative; }
.qb-name { font-size: 1.1rem; color: #fff; font-weight: 600; }
.qb-code { color: rgba(255,255,255,.5); font-size: .82rem; margin-left: .6rem; letter-spacing: .08em; font-variant-numeric: tabular-nums; }
.qb-price { font-size: 2.4rem; color: #fff; font-weight: 700; margin-top: .2rem; line-height: 1.1; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.qb-chg { font-size: 1.1rem; margin-left: .8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.qb-chg.up { color: #ff7b7f; }
.qb-chg.down { color: #5ee6a8; }
.qb-chg.flat { color: rgba(255,255,255,.5); }
.qb-stats { display: flex; gap: 2.2rem; }
.qb-item span { display: block; color: rgba(255,255,255,.52); font-size: .75rem; margin-bottom: .2rem; }
.qb-item b { color: #fff; font-size: 1.1rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.qb-item b.up { color: #ff7b7f; }
.qb-item b.down { color: #5ee6a8; }

/* ===== 顶部 Tab 导航 ===== */
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--line); }
[data-testid="stTabs"] button[data-baseweb="tab"] {
    background: transparent;
    color: var(--ink-2);
    border-radius: 0;
    padding: 0.55rem 1.1rem;
    font-weight: 500;
    font-size: 0.95rem;
}
[data-testid="stTabs"] button[data-baseweb="tab"]:hover { color: var(--ink); }
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--ink);
    font-weight: 600;
    border-bottom: 2px solid var(--accent);
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--accent); }

/* ===== Metric 卡片 ===== */
[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 0.95rem 1.05rem;
    box-shadow: 0 1px 2px rgba(16,24,40,.03);
}
[data-testid="stMetricLabel"] { color: var(--ink-2) !important; font-size: 0.8rem; }
[data-testid="stMetricValue"] { color: var(--ink) !important; font-variant-numeric: tabular-nums; }
[data-testid="stMetricDelta"] .metric-delta-up { color: var(--up) !important; }
[data-testid="stMetricDelta"] .metric-delta-down { color: var(--down) !important; }

/* ===== 模块标题 ===== */
h3 { border-left: 3px solid var(--accent); padding-left: 0.65rem; color: var(--ink); font-weight: 700; margin-top: 1.2rem; }

/* ===== 按钮 ===== */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    background: var(--surface);
    color: var(--accent);
    border: 1px solid var(--line-strong);
    border-radius: 8px;
    padding: 0.45rem 1.2rem;
    font-weight: 600;
    transition: border-color 0.15s, color 0.15s;
}
.stButton > button:hover, .stFormSubmitButton > button:hover { border-color: var(--accent); color: var(--accent-ink); }
.stButton > button:focus, .stFormSubmitButton > button:focus { box-shadow: 0 0 0 1px var(--accent); }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {
    background: var(--accent);
    color: #fff;
    border: none;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
    background: var(--accent-ink); color: #fff; border: none;
}

/* ===== 输入框 ===== */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {
    border-radius: 8px;
    border: 1px solid var(--line-strong);
    background: var(--surface);
    color: var(--ink);
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

/* ===== 数据表格 ===== */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid var(--line); }

/* ===== 社区情绪（牛熊对决） ===== */
.sentiment { border: 1px solid var(--line); border-radius: 12px; padding: 1.2rem 1.4rem; background: var(--surface); }
.sent-mascots { display: flex; align-items: flex-end; justify-content: space-between; gap: 8px; margin-bottom: 1rem; }
.sent-side { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.sent-vs { align-self: center; font-size: .72rem; color: var(--ink-3); font-weight: 600; letter-spacing: .1em; padding-bottom: .6rem; writing-mode: vertical-rl; }
.sent-num { font-size: 1.4rem; font-weight: 700; letter-spacing: -.02em; line-height: 1; font-variant-numeric: tabular-nums; }
.sent-num.up { color: var(--up); }
.sent-num.down { color: var(--down); }
.sent-label { font-size: .78rem; color: var(--ink-2); }
.mascot { width: 58px; height: 58px; display: block; filter: drop-shadow(0 2px 4px rgba(16,24,40,.10)); }
.sent-bar { position: relative; height: 14px; border-radius: 999px; overflow: hidden; background: var(--down); }
.sent-bar span { position: absolute; left: 0; top: 0; bottom: 0; background: var(--up); }
.sent-labels { display: flex; justify-content: space-between; margin-top: .6rem; font-size: .8rem; }
.sent-labels .up { color: var(--up); font-weight: 600; }
.sent-labels .down { color: var(--down); font-weight: 600; }
.sent-labels .muted { color: var(--ink-3); }
.sent-caption { font-size: .78rem; color: var(--ink-3); margin-top: .4rem; }

/* ===== 智能体推理轨迹（信号流 · 抽象科技画风） ===== */
.trace-head { font-size: .78rem; color: var(--ink-2); font-weight: 600; margin: .4rem 0 .7rem; }
.tl { position: relative; padding-left: 2.6rem; border-radius: 14px; background: radial-gradient(90% 45% at 0% 0%, rgba(0,102,255,.045), transparent 60%); }
.tl::before { content: ""; position: absolute; left: 1rem; top: 1.2rem; bottom: .9rem; width: 2px; background: linear-gradient(180deg, var(--line-strong), var(--line)); }
.tl::after { content: ""; position: absolute; left: 1rem; top: 0; width: 8px; height: 8px; transform: translateX(-50%); border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px var(--accent); animation: flow 2.8s cubic-bezier(.45,.05,.55,.95) infinite; }
.tstep { --c: var(--accent); --c-soft: var(--accent-soft); position: relative; margin-bottom: .72rem; animation: traceIn .55s cubic-bezier(.22,.61,.36,1) both; }
.tnode { position: absolute; left: -2.6rem; top: 1rem; width: 2rem; height: 2rem; border-radius: 50%; background: var(--c); color: #fff; font-size: .72rem; font-weight: 700; display: grid; place-items: center; box-shadow: 0 0 0 4px var(--c-soft); font-variant-numeric: tabular-nums; animation: nodeGlow 3.2s ease-in-out infinite; }
.tbody { border: 1px solid var(--line); border-left: 3px solid var(--c); border-radius: 12px; background: var(--surface); padding: .66rem 1rem .7rem; box-shadow: 0 1px 2px rgba(16,24,40,.03); transition: transform .18s cubic-bezier(.22,.61,.36,1), box-shadow .18s, border-color .18s; }
.tbody:hover { transform: translateX(5px); border-color: var(--c); box-shadow: 0 6px 18px var(--c-soft); }
.trow { display: flex; align-items: center; gap: .55rem; }
.ttool { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .86rem; color: var(--c); font-weight: 700; letter-spacing: -.01em; }
.tlabel { font-size: .72rem; color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--line); padding: .1rem .5rem; border-radius: 999px; font-weight: 600; }
.tsum { margin-top: .32rem; font-size: .82rem; color: var(--ink); line-height: 1.45; }
.tsum.err { color: var(--up); }
@keyframes traceIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes flow { 0% { top: 0; opacity: 0; } 8% { opacity: 1; } 92% { opacity: 1; } 100% { top: 100%; opacity: 0; } }
@keyframes nodeGlow { 0%, 100% { box-shadow: 0 0 0 4px var(--c-soft); } 50% { box-shadow: 0 0 0 9px transparent; } }
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)

from data.akshare_provider import get_provider  # noqa: E402
from utils.config import Config, ROOT, normalize_code  # noqa: E402
from core.portfolio import load_portfolio, save_portfolio  # noqa: E402

_PORTFOLIO_PATH = str(ROOT / "data" / "portfolio_admin.json")

_MODULES = ["数据仪表盘", "公告快读", "财报速解", "AI 研报助手", "策略回测"]


def _login() -> None:
    """演示登录门：admin / admin。"""
    st.markdown("### 登录 AlphaMind")
    st.caption("演示账号：admin ｜ 密码：admin")
    with st.form("login_form"):
        username = st.text_input("用户名", value="admin")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
    if submitted:
        if Config.DEMO_USERS.get(username.strip()) == password:
            st.session_state["authed"] = True
            st.session_state["user"] = username.strip()
            st.rerun()
        else:
            st.error("用户名或密码错误（演示账号 admin / admin）")


def _sidebar(portfolio) -> str:
    with st.sidebar:
        st.markdown('<div class="brand">AlphaMind<span class="dot">.</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-sub">面向个人投资者的<br>智能投研终端</div>', unsafe_allow_html=True)
        st.markdown("---")
        st.markdown('<div class="nav-title">我的持仓</div>', unsafe_allow_html=True)

        with st.form("add_holding", clear_on_submit=True):
            c1, c2 = st.columns(2)
            code_raw = c1.text_input("股票代码", placeholder="600519")
            shares = c2.number_input("股数（可空）", min_value=0, value=None, step=100)
            cost = st.number_input("成本价（可空）", min_value=0.0, value=None, step=0.5)
            add = st.form_submit_button("添加持仓")
        if add:
            code = normalize_code(code_raw)
            if code.isdigit() and len(code) == 6:
                portfolio.add(code, shares=shares or 0, cost=cost or None)
                save_portfolio(_PORTFOLIO_PATH, portfolio)
                st.session_state["analysis_target"] = code  # 新增后自动切到最新这只
                st.rerun()
            else:
                st.error("请输入 6 位 A 股代码")

        if portfolio.holdings:
            for h in list(portfolio.holdings):
                col1, col2 = st.columns([4, 1])
                col1.markdown(f"**{h['name']}**")
                if col2.button("×", key=f"rm_{h['code']}", help="移除持仓"):
                    portfolio.remove(h["code"])
                    save_portfolio(_PORTFOLIO_PATH, portfolio)
                    st.session_state.pop("analysis_target", None)
                    st.rerun()
        else:
            st.caption("暂无持仓，添加后即可查看组合")

        st.markdown("---")
        st.markdown('<div class="nav-title">当前分析标的</div>', unsafe_allow_html=True)
        labels = {h["code"]: h["name"] for h in portfolio.holdings}
        if labels:
            opts = list(labels) + ["__manual__"]
            if st.session_state.get("analysis_target") not in opts:
                st.session_state["analysis_target"] = opts[0]
            choice = st.selectbox(
                "选择股票", opts, key="analysis_target",
                format_func=lambda c: "（手动输入）" if c == "__manual__" else labels[c],
            )
            if choice == "__manual__":
                selected = normalize_code(st.text_input("股票代码", value="600519"))
            else:
                selected = choice
        else:
            selected = normalize_code(
                st.text_input("股票代码", value="600519", help="输入 6 位 A 股代码，如 600519（贵州茅台）")
            )

        st.markdown("---")
        if st.button("刷新实时数据"):
            from data import cache
            cache.clear()
            st.cache_data.clear()
            st.rerun()
        st.caption("数据源：新浪 · 百度 · 同花顺 · 巨潮")

        st.markdown("---")
        st.caption(f"已登录：{st.session_state.get('user', 'admin')}")
        if st.button("退出登录"):
            st.session_state["authed"] = False
            st.session_state.pop("portfolio", None)
            st.session_state.pop("analysis_target", None)
            st.session_state.pop("agent_result", None)
            st.rerun()

        return selected


def _header(snap: dict):
    """顶部动态行情看板：名称 + 代码 + 最新价 + 涨跌幅（红涨绿跌）。"""
    name = snap.get("名称") or "—"
    code = snap.get("代码") or ""
    price = snap.get("最新价")
    chg = snap.get("涨跌幅")
    chg_amt = snap.get("涨跌额")
    amt = snap.get("成交额")
    vol = snap.get("成交量")

    price_str = f"{price:.2f}" if price is not None else "—"
    if chg is not None and chg > 0:
        cls, arrow = "up", "▲"
    elif chg is not None and chg < 0:
        cls, arrow = "down", "▼"
    else:
        cls, arrow = "flat", ""
    chg_str = f"{arrow} {chg:+.2f}%" if chg is not None else "—"
    chg_amt_str = f"{chg_amt:+.2f}" if chg_amt is not None else "—"
    amt_str = f"{amt/1e8:.2f} 亿" if amt else "—"
    vol_str = f"{vol/1e6:.2f} 万手" if vol else "—"

    st.markdown(
        f"""
        <div class="quote-bar">
          <div class="qb-main">
            <div class="qb-name">{name}<span class="qb-code">{code}</span></div>
            <div class="qb-price">{price_str}<span class="qb-chg {cls}">{chg_str}</span></div>
          </div>
          <div class="qb-stats">
            <div class="qb-item"><span>涨跌额</span><b class="{cls}">{chg_amt_str}</b></div>
            <div class="qb-item"><span>成交额</span><b>{amt_str}</b></div>
            <div class="qb-item"><span>成交量</span><b>{vol_str}</b></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---- 登录门（演示账号：admin / admin）----
if not st.session_state.get("authed"):
    _login()
    st.stop()

# ---- 持仓组合（会话内持有，变更即落盘 JSON）----
if "portfolio" not in st.session_state:
    st.session_state["portfolio"] = load_portfolio(_PORTFOLIO_PATH)
portfolio = st.session_state["portfolio"]

selected_code = _sidebar(portfolio)

# 行情看板：读本地缓存快照，秒开（akshare 懒加载，缓存命中不 import）
p = get_provider()
_header(p.get_snapshot(selected_code))

tabs = st.tabs(_MODULES + ["组合总览"])
with tabs[0]:
    from ui.pages import module1_dashboard
    module1_dashboard.render(selected_code)
with tabs[1]:
    from ui.pages import module2_announcements
    module2_announcements.render(selected_code)
with tabs[2]:
    from ui.pages import module3_financials
    module3_financials.render(selected_code)
with tabs[3]:
    from ui.pages import module4_assistant
    module4_assistant.render(selected_code)
with tabs[4]:
    from ui.pages import module5_backtest
    module5_backtest.render(selected_code)
with tabs[5]:
    from ui.pages import module6_portfolio
    module6_portfolio.render(portfolio)
