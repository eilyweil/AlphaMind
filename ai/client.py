"""DeepSeek 客户端封装（OpenAI 兼容接口）。"""
from openai import OpenAI

from utils.config import Config

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url=Config.DEEPSEEK_BASE_URL,
        )
    return _client


def chat(messages, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """一次对话补全，返回文本。"""
    client = get_client()
    resp = client.chat.completions.create(
        model=Config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def chat_json(messages, temperature: float = 0.2, max_tokens: int = 2000):
    """要求模型返回 JSON，解析失败返回 None。"""
    import json

    resp = get_client().chat.completions.create(
        model=Config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content
    try:
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"[ai] JSON 解析失败: {e}\n原始: {text}")
        return None
