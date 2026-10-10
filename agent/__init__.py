"""AlphaMind 的 Agent 层：工具注册 + 最小 Agent 循环 + 飞书卡片 + MCP 桥接。

把 core.engine 的能力暴露为可被 LLM 调用的工具，用于接入 Hermes / 飞书，
让项目从「人点按钮」升级为「自然语言驱动的智能体」。本包不依赖 streamlit。
"""
from .tools import TOOLS, dispatch

__all__ = ["TOOLS", "dispatch"]
