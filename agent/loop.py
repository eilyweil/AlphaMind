"""最小 Agent 循环：DeepSeek function calling 驱动 AlphaMind 工具。

无需 Hermes / 飞书即可跑通「自然语言 → 工具调用 → 结构化研判」，
验证 tools.py 的工具封装正确。后续接入 Hermes/MCP 时复用同一套 TOOLS。

用法：
    from agent.loop import run
    print(run("600519 现在估值贵吗？"))
"""
import json

from ai.client import get_client
from utils.config import Config

from .tools import TOOLS, SYSTEM, dispatch


def _finalize(client, model: str, messages: list) -> str:
    resp = client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content or ""


def run_traced(query: str, model: str = None, max_steps: int = 5) -> dict:
    """执行一轮 Agent 循环，返回 {"answer": 最终结论, "trace": 工具调用轨迹}。

    trace 每项为 {"name": 工具名, "args": 入参, "result": 工具返回}，供 Web 端可视化。
    """
    client = get_client()
    model = model or Config.DEEPSEEK_MODEL
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": query},
    ]
    trace: list = []

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"answer": msg.content or "", "trace": trace}

        # 记录 assistant 的 tool_calls 消息
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        # 逐个执行工具并回填结果，同时记录轨迹
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = dispatch(tc.function.name, args)
            except Exception as ex:  # noqa: BLE001
                result = {"error": str(ex)}
            trace.append({"name": tc.function.name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    # 达到步数上限仍未收尾：补一次不带工具的调用，让它给出结论
    return {"answer": _finalize(client, model, messages), "trace": trace}


def run(query: str, model: str = None, max_steps: int = 5) -> str:
    """执行一轮 Agent 循环，返回最终自然语言结论（兼容旧接口）。"""
    return run_traced(query, model=model, max_steps=max_steps)["answer"]


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "600519 现在估值贵吗？"
    print(run(q))
