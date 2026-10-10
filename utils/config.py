"""配置加载：从 .env 或 Streamlit Cloud secrets 读取 DeepSeek 等配置。

优先顺序：Streamlit Cloud secrets（在线部署）→ 环境变量 → 项目根 .env（本地）。
密钥永不进入代码仓库，只通过 .env / secrets 注入。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """读取配置：优先 st.secrets（Streamlit Cloud），其次环境变量。"""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001  非 Streamlit 环境（agent/MCP/tests）无 st.secrets
        pass
    return os.getenv(key, default)


class Config:
    DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-chat")

    # 演示登录账号（仅用于 demo 展示，生产环境务必替换为真实鉴权）
    DEMO_USERS = {"admin": "admin"}


def normalize_code(code: str) -> str:
    """归一化 6 位 A 股代码（去掉交易所后缀/空白）。"""
    c = str(code).strip().lower()
    for suffix in (".sh", ".sz", ".bj"):
        if c.endswith(suffix):
            c = c[: -len(suffix)]
    return c.zfill(6) if c.isdigit() else c


def code_to_market(code: str) -> str:
    """6 位代码 -> 交易所 market（用于 ak 接口）。"""
    code = normalize_code(code)
    if code.startswith("6"):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    if code.startswith(("4", "8", "9")):
        return "bj"
    return "sz"
