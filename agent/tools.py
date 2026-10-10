"""AlphaMind 工具注册表：把投研引擎暴露为 LLM 可调用的工具（OpenAI function-calling 格式）。

TOOLS 是一份与运行框架无关的工具清单（Hermes / DeepSeek / MCP / OpenAI 都能消费），
dispatch() 是执行器，把工具名 + 参数映射到 core.engine 的方法。

关键约束（沿用 AlphaMind 的幻觉抑制设计）：工具只返回真实取到的数据，
Agent 只负责读数据 + 组织语言 + 决策，绝不自由编造数字。
"""
from core.engine import get_engine
from core.portfolio import load_portfolio
from utils.config import ROOT

# ---- 系统人设（与 agent/soul.md 保持一致）----
SYSTEM = (
    "你是 AlphaMind，一名面向 A 股个人投资者的专业投研分析助手。"
    "你可以调用工具查询实时行情、估值分位、盈利质量、资金面、财报速解、公告、社区情绪、策略回测、"
    "持仓组合全景与组合研判，并基于工具返回的数据给出结构化研判。\n"
    "严格规则：\n"
    "1. 只依据工具返回的数据作答，绝不编造未给出的数字；无数据就明说「暂无」。\n"
    "2. 结论要区分「事实（有数据支撑）」与「判断（你的分析）」，并标注风险点与置信度。\n"
    "3. 涉及买卖的提问，必须提示「本平台输出不构成投资建议，历史回测不预示未来收益」。\n"
    "4. 用简体中文、Markdown 结构输出。"
)

# ---- 工具定义（OpenAI function-calling 兼容）----
def _tool(name, desc, props, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
    }


_CODE = {"type": "string", "description": "6 位 A 股代码，如 600519（贵州茅台）"}

# 组合持仓与 Web 端共用同一份落盘文件（data/portfolio_admin.json）。
# agent 每次调用重新加载，保证飞书/agent 问到的持仓与用户在界面配置的一致。
_PORTFOLIO_PATH = str(ROOT / "data" / "portfolio_admin.json")


def _get_portfolio():
    """加载当前持仓组合（无状态：每次从 JSON 重读）。"""
    return load_portfolio(_PORTFOLIO_PATH)

TOOLS = [
    _tool("snapshot", "查询某只 A 股的实时行情快照：最新价、涨跌幅、成交额、成交量。", {"code": _CODE}, ["code"]),
    _tool("valuation", "查询某只 A 股的 PE/PB/PS/PCF 估值及近一年历史分位，用于判断当前贵贱。", {"code": _CODE}, ["code"]),
    _tool("quality", "查询某只 A 股的盈利质量：ROE、毛利率、净利率、营收增速、净利增速及趋势。", {"code": _CODE}, ["code"]),
    _tool("fundflow", "查询某只 A 股近 5 日主力资金流入净额、阶段涨跌幅、连续换手率。", {"code": _CODE}, ["code"]),
    _tool("financial_analysis", "对某只 A 股做财报速解（预期差分析）：本期业绩 vs 一致预期 vs 上年同期 + 风险点。", {"code": _CODE}, ["code"]),
    _tool("announcement_analysis", "抓取某只 A 股近 30 天公告，AI 标注每条的类型、核心变化、是否实质性变化（增减发/减持/离职等）。", {"code": _CODE}, ["code"]),
    _tool("sentiment", "查询某只 A 股的东财股吧社区情绪：看多/看空/中性比例及代表观点。", {"code": _CODE}, ["code"]),
    _tool("backtest", "对某只 A 股做策略回测：双均线/MACD/RSI/布林带，返回收益率、最大回撤、夏普、胜率等指标。", {
        "code": _CODE,
        "strategy": {"type": "string", "enum": ["双均线（MA）", "MACD", "RSI 超买超卖", "布林带（BOLL）"], "description": "回测策略，默认双均线（MA）"},
        "period_days": {"type": "integer", "description": "回测区间天数，默认 730（近 2 年）"},
    }, ["code"]),
    _tool("report", "对某只 A 股做一次完整的综合研判：聚合基本面 + 社区情绪，输出结论/支撑数据/风险点/置信度。", {
        "code": _CODE,
        "question": {"type": "string", "description": "用户关心的问题，如「现在估值贵吗」「适合买入吗」"},
    }, ["code", "question"]),
    _tool("portfolio_overview", "查询当前持仓组合全景：持仓明细、总市值、HHI 集中度、第一大持仓占比、加权 PE 历史分位、整体浮盈亏。", {}, []),
    _tool("portfolio_analysis", "对当前持仓组合做综合研判：集中度、估值、盈利质量、社区情绪、风险与结论。", {
        "include_sentiment": {"type": "boolean", "description": "是否纳入社区情绪（额外批量抓取各持仓股吧帖子，稍慢，默认 false）"},
    }, []),
]


def dispatch(name: str, args: dict):
    """执行一个工具调用，返回 JSON 可序列化的结果。未知工具抛 ValueError。"""
    e = get_engine()
    code = args.get("code", "")

    if name == "snapshot":
        return e.snapshot(code)
    if name == "valuation":
        return e.valuation(code)
    if name == "quality":
        return e.quality(code)
    if name == "fundflow":
        return e.fundflow(code, days=args.get("days", 5))
    if name == "financial_analysis":
        return e.financial_analysis(code)
    if name == "announcement_analysis":
        return e.announcement_analysis(code, days=args.get("days", 30), max_items=args.get("max_items", 20))
    if name == "sentiment":
        return e.sentiment(code, limit=args.get("limit", 15))
    if name == "backtest":
        result = e.backtest(
            code,
            strategy=args.get("strategy", "双均线（MA）"),
            params=args.get("params"),
            period_days=args.get("period_days", 730),
            initial_wan=args.get("initial_wan", 10),
        )
        # 去掉回测 DataFrame，只保留可序列化的指标与买卖点
        return {k: v for k, v in result.items() if k != "df"} if result else result
    if name == "report":
        return e.report(code, args["question"])
    if name == "portfolio_overview":
        ov = _get_portfolio().overview()
        return ov if ov["positions"] else {"message": "当前暂无持仓，请先在 Web 端「我的持仓」添加股票代码。"}
    if name == "portfolio_analysis":
        result = _get_portfolio().overall_analysis(include_sentiment=bool(args.get("include_sentiment", False)))
        return result if result else {"message": "当前暂无持仓，无法生成组合研判。"}
    raise ValueError(f"未知工具: {name}")
