"""各模块的 prompt 模板。"""

SYSTEM = "你是一名专业的 A 股投研分析助手，输出严谨、客观、结构化，所有结论必须基于给定的数据，不臆造数据。"


def build_assistant_prompt(question: str, context: str, sentiment: str) -> list[dict]:
    """模块4 AI 研报助手 prompt。"""
    system = (
        f"{SYSTEM}\n"
        "请按以下结构输出（用 Markdown）：\n"
        "## 结论\n（一句话核心判断）\n"
        "## 支撑数据\n（引用给出的数据）\n"
        "## 风险点\n（列出主要风险）\n"
        "## 置信度\n（高/中/低，并说明理由）\n"
        "## 社区情绪\n（基于给定情绪数据的看多/看空判断）"
    )
    user = (
        f"【用户提问】\n{question}\n\n"
        f"【基础数据】\n{context}\n\n"
        f"【社区情绪数据】\n{sentiment}\n\n"
        "请基于以上数据回答，不要编造未给出的数据。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_announcement_prompt(title: str, content: str) -> list[dict]:
    """模块2 公告快读 prompt：提取核心变化。"""
    system = (
        f"{SYSTEM}\n"
        "请以 JSON 输出，字段为：\n"
        '{"category": "公告类型", "core_change": "一句话核心变化", '
        '"substantive": "是否为实质性变化(增减发/股权变动/高管离职/定增/股权激励等), 是或否", '
        '"reason": "判断依据"}'
    )
    user = f"【公告标题】\n{title}\n\n【公告内容】\n{content[:3000]}\n\n请提取该公告的核心变化点。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_factor_backtest_interpretation_prompt(strategy: str, summary: str) -> list[dict]:
    """模块5 因子组合回测的「大白话」四段解读（只传结构化指标，不传行情）。"""
    system = (
        f"{SYSTEM}\n"
        "你是量化回测解读助手。请基于给出的结构化回测指标，用中文大白话解读，让非程序员也能看懂。"
        "只使用给定数字，不臆造数据；结论仅供参考，不替代硬性检验；"
        "必须提示「历史回测不代表未来收益」，不要给出确定性的买卖建议。"
    )
    user = (
        f"【策略】{strategy}\n"
        f"【回测指标（结构化数字）】\n{summary}\n\n"
        "请严格按以下四段输出（用 Markdown 标题）：\n"
        "## 结论\n（一句话：这个策略到底行不行）\n"
        "## 亮点\n（超额从哪来、哪块表现好）\n"
        "## 风险\n（回撤 / 过拟合 / 动量崩溃等风险）\n"
        "## 建议\n（要不要继续用、该怎么改）"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_financial_prompt(financials: str, forecast: str, last_year: str) -> list[dict]:
    """模块3 财报速解 prompt。"""
    system = (
        f"{SYSTEM}\n"
        "请以 JSON 输出，字段为：\n"
        '{"summary": "本期业绩一句话总结", "vs_consensus": "相对一致预期: 超预期/符合/低于预期", '
        '"vs_last_year": "相对上年同期变化", "guidance": "管理层指引变化(若无则写无)", '
        '"risk": "需关注的风险点"}'
    )
    user = (
        f"【本期财务数据】\n{financials}\n\n"
        f"【一致预期(盈利预测)】\n{forecast}\n\n"
        f"【上年同期数据】\n{last_year}\n\n"
        "请分析本期业绩。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_portfolio_prompt(context: str) -> list[dict]:
    """模块6 组合综合评估 prompt：集中度 / 估值 / 盈利质量 / 情绪 / 风险。"""
    system = (
        f"{SYSTEM}\n"
        "你是组合分析助手。请基于给定的持仓组合数据，从集中度、估值、盈利质量、社区情绪、风险角度做组合级研判。\n"
        "以 JSON 输出，字段为：\n"
        '{"summary":"组合一句话概括", "concentration_risk":"集中度风险分析", '
        '"valuation":"组合估值水平判断", "sentiment":"组合情绪面观察(无情绪数据时写:未纳入)", '
        '"risk":"组合主要风险点", "conclusion":"组合整体结论与观察"}'
    )
    user = (
        f"【我的持仓组合】\n{context}\n\n"
        "请客观分析这个组合，不要编造未给出的数据；结论须提示「不构成投资建议」。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_backtest_prompt(strategy: str, params: str, summary: str, stock: str) -> list[dict]:
    """模块5 策略回测解读 prompt。"""
    system = (
        f"{SYSTEM}\n"
        "请基于回测结果给出客观、克制的解读，必须提示「历史回测不代表未来收益」，"
        "不要给出确定性的买卖建议。"
    )
    user = (
        f"【标的】{stock}\n"
        f"【策略】{strategy}（参数 {params}）\n"
        f"【回测结果】\n{summary}\n\n"
        "请分四段输出（用 Markdown）：\n"
        "## 历史表现解读\n"
        "## 与买入持有的对比\n"
        "## 主要风险与局限\n"
        "## 结论与提示"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
