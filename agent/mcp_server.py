"""AlphaMind 的 MCP（Model Context Protocol）服务：把投研引擎暴露为标准工具。

Hermes Agent 支持「Connect any MCP server」，本服务用 stdio 传输、JSON-RPC 2.0
逐行分隔（无需任何第三方依赖）。启动：python agent/mcp_server.py。

MCP 客户端（Hermes / Claude Code 等）连接后即可获得 tools/list 里列出的投研工具。
"""
import json
import sys

from .tools import TOOLS, dispatch

_SERVER_INFO = {"name": "alphamind", "version": "0.1.0"}


def _read_message():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _send(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(req):
    mid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": _SERVER_INFO,
        }}
    if method == "tools/list":
        tools = [
            {"name": t["function"]["name"],
             "description": t["function"]["description"],
             "inputSchema": t["function"]["parameters"]}
            for t in TOOLS
        ]
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tools}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = dispatch(name, args)
            text = json.dumps(result, ensure_ascii=False, default=str)
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as ex:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"错误: {ex}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    # 通知（无 id）不响应
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    while True:
        req = _read_message()
        if req is None:
            break
        resp = _handle(req)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
