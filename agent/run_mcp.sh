#!/bin/bash
# AlphaMind MCP 服务启动器：切换到项目根目录后，用 invest 环境的 Python 启动 stdio MCP 服务。
# 供 Hermes 通过 `hermes mcp add alphamind --command .../run_mcp.sh` 注册。
set -euo pipefail
cd "$(dirname "$0")/.."
exec /Users/gaojianan/miniconda3/envs/invest/bin/python -m agent.mcp_server
