"""模块4：社区情绪（抓东财股吧帖子 -> DeepSeek 分类看多/看空）。"""
import re

import requests


def fetch_guba_posts(code: str, limit: int = 20) -> list[str]:
    """抓取东财股吧帖子标题。失败返回空列表。"""
    try:
        url = f"https://guba.eastmoney.com/list,{code}.html"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Referer": "https://guba.eastmoney.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        # 帖子标题在 /news,{code},{id}.html">标题 结构中
        pattern = re.compile(r'/news,' + re.escape(code) + r',\d+\.html"[^>]*>\s*([^<]{2,120})')
        titles = pattern.findall(resp.text)
        seen, out = set(), []
        for t in titles:
            t = t.strip()
            if t in seen:
                continue
            seen.add(t)
            if re.search(r"举报|反诈|网警|征信|首页|下一页|违法", t):
                continue
            out.append(t)
            if len(out) >= limit:
                break
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[sentiment] 抓取股吧失败: {e}")
        return []


def analyze_sentiment(posts: list[str]) -> dict:
    """用 DeepSeek 将帖子标题分类为看多/看空/中性。"""
    if not posts:
        return {"bull": 0, "bear": 0, "neutral": 0, "samples": 0, "views": [], "summary": "社区情绪数据暂不可用"}

    from ai.client import chat_json
    from ai.prompts import SYSTEM

    user = (
        "下面是一些股票论坛的帖子标题，请判断每条是【看多】、【看空】还是【中性】，"
        "并以 JSON 输出。格式："
        '{"results": [{"title": "原标题", "sentiment": "看多/看空/中性"}], '
        '"summary": "一句话总结整体情绪倾向"}\n\n'
        "帖子标题列表：\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(posts))
    )
    messages = [
        {"role": "system", "content": SYSTEM + " 只输出 JSON。"},
        {"role": "user", "content": user},
    ]
    data = chat_json(messages)
    if not data or "results" not in data:
        return {"bull": 0, "bear": 0, "neutral": 0, "samples": len(posts), "views": [], "summary": "情绪分析失败"}

    results = data["results"]
    bull = sum(1 for r in results if "多" in r.get("sentiment", ""))
    bear = sum(1 for r in results if "空" in r.get("sentiment", ""))
    neutral = len(results) - bull - bear
    n = max(len(results), 1)
    return {
        "bull": round(bull / n * 100, 1),
        "bear": round(bear / n * 100, 1),
        "neutral": round(neutral / n * 100, 1),
        "samples": len(results),
        "views": results[:8],
        "summary": data.get("summary", ""),
    }


def analyze_sentiment_batch(codes: list[str], limit: int = 15) -> dict:
    """批量抓取多只股票的社区情绪，一次 LLM 调用分类所有帖子。

    与 analyze_sentiment 逐票调 LLM 不同，这里把多只股票的帖子拼进同一次调用，
    把 N 次 LLM 降为 1 次，供组合级研判使用。
    返回 {code: {bull, bear, neutral, samples, summary}}；抓取失败的股票不在结果中。
    """
    from ai.client import chat_json
    from ai.prompts import SYSTEM

    # 1. 抓帖（纯 HTTP，无 LLM）
    per_code = {c: fetch_guba_posts(c, limit=limit) for c in codes}
    active = {c: posts for c, posts in per_code.items() if posts}
    if not active:
        return {}

    # 2. 一次 LLM 调用分类所有帖子（每条带 [代码] 标注）
    lines = []
    for c, posts in active.items():
        for t in posts:
            lines.append(f"[{c}] {t}")
    user = (
        "下面是多只股票的论坛帖子标题，每条前面的 [代码] 是股票归属。"
        "请判断每条是【看多】【看空】还是【中性】，并以 JSON 输出。格式："
        '{"results":[{"code":"代码","title":"原标题","sentiment":"看多/看空/中性"}],'
        '"summary":{"代码":"一句话整体情绪倾向"}}'
        "\n\n帖子列表：\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(lines))
    )
    messages = [{"role": "system", "content": SYSTEM + " 只输出 JSON。"}, {"role": "user", "content": user}]
    data = chat_json(messages)
    if not data or "results" not in data:
        return {}

    results = data.get("results", [])
    summaries = data.get("summary", {})

    def _norm(x):
        s = str(x or "").strip()
        return s[-6:] if s else ""

    out = {}
    for c in active:
        rs = [r for r in results if _norm(r.get("code")) == c]
        if not rs:
            continue
        bull = sum(1 for r in rs if "多" in r.get("sentiment", ""))
        bear = sum(1 for r in rs if "空" in r.get("sentiment", ""))
        n = max(len(rs), 1)
        out[c] = {
            "bull": round(bull / n * 100, 1),
            "bear": round(bear / n * 100, 1),
            "neutral": round((len(rs) - bull - bear) / n * 100, 1),
            "samples": len(rs),
            "summary": summaries.get(c, ""),
        }
    return out
