"""飞书消息卡片构建器（卡片 JSON v2 schema，接入飞书时使用，无需凭证即可编写/测试）。

返回的是飞书「interactive」卡片消息体，供 Hermes 网关或 lark-oapi 直接发送。
"""
_DISCLAIMER = "本内容为投资研究参考，不构成投资建议；历史回测不预示未来收益。"


def _md(content: str) -> dict:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def simple_text(text: str) -> dict:
    """纯文本卡片（兜底用）。"""
    return {
        "config": {"wide_screen_mode": True},
        "elements": [_md(text)],
    }


def valuation_card(name: str, val: dict) -> dict:
    """估值指标卡片：PE/PB/PS/PCF 及历史分位。"""
    rows = []
    for key in ("pe", "pb", "ps", "pcf"):
        v = (val or {}).get(key, {})
        value = v.get("value")
        pct = v.get("pct")
        if value is None:
            rows.append(f"**{key.upper()}**：暂无")
        elif pct is not None:
            rows.append(f"**{key.upper()}**：{value:.2f}（历史分位 {pct}%）")
        else:
            rows.append(f"**{key.upper()}**：{value:.2f}")
    body = "\n".join(rows) or "暂无估值数据"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"{name} · 估值"}, "template": "blue"},
        "elements": [_md(body), {"tag": "note", "elements": [{"tag": "plain_text", "content": _DISCLAIMER}]}],
    }


def research_card(name: str, answer: str) -> dict:
    """综合研判卡片：直接渲染 Markdown 结论。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"{name} · 研判"}, "template": "blue"},
        "elements": [
            _md(answer),
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": _DISCLAIMER}]},
        ],
    }


def announcement_card(results: list) -> dict:
    """公告快读卡片：高亮实质性变化。"""
    lines = []
    for r in results:
        substantive = r.get("substantive") == "是"
        title = r.get("title", "")
        core = r.get("core_change", "")
        if substantive:
            lines.append(f"🔴 **{title}**\n　{core}（实质性变化）")
        else:
            lines.append(f"**{title}**\n　{core}")
    body = "\n\n".join(lines) if lines else "暂无公告"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "公告快读"}, "template": "red"},
        "elements": [_md(body)],
    }
