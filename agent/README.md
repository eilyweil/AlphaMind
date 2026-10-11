# AlphaMind · Agent 层（Hermes / 飞书 接入的中间层）

把 `core.engine` 的投研能力暴露为 LLM 可调用的工具，让 AlphaMind 从「人点按钮」
升级为「自然语言驱动的智能体」。本目录不依赖 streamlit，可在任意 Python 运行时调用。

## 目录

| 文件 | 作用 |
|---|---|
| `tools.py` | 工具注册表（`TOOLS`）+ 执行器（`dispatch`）+ 系统人设（`SYSTEM`） |
| `loop.py` | 最小 Agent 循环：DeepSeek function calling 驱动工具 |
| `mcp_server.py` | MCP（Model Context Protocol）服务：把工具暴露给 Hermes 等 MCP 客户端 |
| `cards.py` | 飞书消息卡片构建器 |
| `soul.md` | 系统人设（Hermes SOUL.md 格式） |

> **组合能力**：`portfolio_overview` / `portfolio_analysis` 两个工具读取与 Web 端相同的
> `data/portfolio_admin.json`（在界面「我的持仓」里配置），因此 agent / 飞书问到的持仓即为同一份。
> 登录（admin/admin）仅作用于 Web 端，不影响 MCP / Hermes（其鉴权由 `FEISHU_ALLOWED_USERS` 控制）。

## 现在就能跑（无需 Hermes / 飞书）

```bash
# 1. 自然语言 → 工具调用 → 结构化研判（走 DeepSeek，用现有 .env 的 key）
python -m agent.loop "600519 现在估值贵吗？"

# 2. 直接调用单个工具
python -c "from agent.tools import dispatch; print(dispatch('valuation', {'code': '600519'}))"

# 3. 启动 MCP 服务（供 Hermes / Claude Code 等 MCP 客户端连接）
python -m agent.mcp_server
```

## 接入 Hermes 的三条路径

1. **MCP（推荐，已跑通）**：Hermes 支持「Connect any MCP server」，把 `agent/mcp_server.py`
   作为 MCP 服务注册进 Hermes，12 个投研工具即出现在 Hermes 的工具清单里。
2. **人设（SOUL.md）**：把 `soul.md` 内容放到 `~/.hermes/SOUL.md`，让 Hermes 以
   AlphaMind 的身份（铁律 + 行为风格）回答。
3. **直连飞书**：用 `cards.py` 的卡片模板 + `lark-oapi` 自己写 bot（不推荐，重复造轮子）。

## Hermes 安装 + 飞书接入（已跑通的实际步骤）

```bash
# 1. 安装（跳过浏览器/computer-use 等重依赖）
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup --skip-browser --skip-computer-use
# 安装后 hermes 在 ~/.local/bin/hermes，需 export PATH="$HOME/.local/bin:$PATH"

# 2. 配置模型 provider 为 DeepSeek（OpenAI 兼容）
hermes config set model.provider custom
hermes config set model.base_url "https://api.deepseek.com"
hermes config set model.default "deepseek-chat"
hermes config set model.key_env "DEEPSEEK_API_KEY"
# 并把 DEEPSEEK_API_KEY 写入 ~/.hermes/.env

# 3. 装飞书 SDK（websocket 长连接依赖）
~/.hermes/bin/uv pip install --python ~/.hermes/hermes-agent/venv/bin/python lark-oapi

# 4. 注册 AlphaMind 的 MCP 工具（12 个投研工具）
hermes mcp add alphamind --command "$PWD/agent/run_mcp.sh"   # 提示时选 Y

# 5. 人设
cp agent/soul.md ~/.hermes/SOUL.md

# 6. 飞书凭证写入 ~/.hermes/.env（FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_DOMAIN=feishu /
#    FEISHU_CONNECTION_MODE=websocket / FEISHU_ALLOWED_USERS=<你的 open_id> / FEISHU_GROUP_POLICY=allowlist）

# 7. 启动网关
hermes gateway run
```

飞书侧（open.feishu.cn，需人工完成）：创建企业自建应用 → 加「机器人」能力 →
权限 `im:message` / `im:message:send_as_bot` / `im:resource` / `im:chat` / `im:chat:readonly`
→ 事件订阅 `im.message.receive_v1`（连接方式选**长连接 WebSocket**）→ 创建版本并发布。

## 安全

- Hermes 的凭证放 `~/.hermes/.env`，不进仓库、不进 zip。
- `FEISHU_ALLOWED_USERS` 填自己的 open_id 白名单；**留空 = 配对模式**（首次私聊需
  `hermes pairing approve` 批准）。切勿长期开 `FEISHU_ALLOW_ALL_USERS=true`。
- 项目根 `.env`（含 DeepSeek key）继续保持不提交、不打包。
