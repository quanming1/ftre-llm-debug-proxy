# LLM Debug Proxy

独立的 OpenAI-compatible 本地代理，用来抓取、记录和对比不同项目发给模型供应商的请求和返回。

通过在项目与上游 LLM 网关之间插入一层透明代理，实时记录每次请求的完整 messages / tools / response，并在内置 Web 页面中查看和搜索，方便调试 prompt、对比模型行为、排查异常。

## 功能

- **透明代理**：兼容 OpenAI Chat Completions API（`/v1/chat/completions`），支持流式和非流式
- **JSONL 日志**：按天滚动，记录请求体、finish_reason、响应状态码、耗时
- **Web 日志查看器**：内置搜索、按来源过滤、请求详情展开、一键复制 messages / 原始事件
- **多项目区分**：通过 `X-LLM-Debug-Source` 请求头标记来源，日志页可按来源筛选
- **安全脱敏**：日志中不记录 Authorization / API key 等敏感头
- **自动读取 key**：支持从 ftre `config.json` 中匹配 provider 并提取 api_key，无需手动填写

## 快速开始

### 安装

```powershell
cd E:\ftre-llm-debug-proxy
pip install -e .
```

### 方式一：手动指定 upstream 和 key

```powershell
$env:LLM_PROXY_UPSTREAM_BASE = "https://llm-gateway.mlamp.cn/v1"
$env:LLM_PROXY_API_KEY = "你的真实 key"
py -3.12 -m llm_debug_proxy.main --port 19570 --log-dir .\logs
```

### 方式二：从 ftre config.json 自动读取 key

```powershell
py -3.12 -m llm_debug_proxy.main `
  --port 19570 `
  --from-ftre-config "$env:USERPROFILE\.ftre\config.json" `
  --provider-api-base "https://llm-gateway.mlamp.cn/v1" `
  --log-dir .\logs
```

代理会在 config.json 的 `providers` 中匹配 `api_base` 等于 `--provider-api-base` 的条目，自动提取 `api_key`。即使 config.json 不是合法 JSON（如包含注释/尾逗号），也能通过 targeted extraction fallback 提取。

启动后访问 `http://127.0.0.1:19570/` 即可打开日志查看器。

## 接入项目

把任意项目的 OpenAI `base_url` / `api_base` 指向代理地址：

```text
http://127.0.0.1:19570/v1
```

API key 可以继续填原项目里的值；代理不会使用客户端传来的 key，而是用启动时配置的 upstream key 转发。

为了区分不同项目，建议在请求头中标记来源：

```text
X-LLM-Debug-Source: ftre
```

如果不方便加 header，日志里仍会记录 `user-agent`、路径、模型、请求 ID，可在 Web 页面中搜索区分。

## 命令行参数

| 参数 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `--host` | — | `127.0.0.1` | 监听地址 |
| `--port` | — | `19570` | 监听端口 |
| `--upstream-base` | `LLM_PROXY_UPSTREAM_BASE` | `https://llm-gateway.mlamp.cn/v1` | 上游 API 地址 |
| `--api-key` | `LLM_PROXY_API_KEY` | — | 上游 API key |
| `--log-dir` | `LLM_PROXY_LOG_DIR` | `logs` | 日志输出目录 |
| `--source-header` | `LLM_PROXY_SOURCE_HEADER` | `X-LLM-Debug-Source` | 来源标识请求头名称 |
| `--from-ftre-config` | — | — | 从 ftre config.json 读取 key |
| `--provider-api-base` | — | 同 `--upstream-base` | 在 config.json 中匹配的 provider api_base |

## 日志格式

JSONL 日志按天滚动，文件名 `logs/llm-proxy-YYYYMMDD.jsonl`，每行一个 JSON 事件：

### `request` — 请求到达

```json
{
  "ts": "2026-06-23T10:00:00.000",
  "type": "request",
  "request_id": "r1",
  "source": "ftre",
  "method": "POST",
  "path": "/v1/chat/completions",
  "model": "tencent/glm-5.2",
  "stream": true,
  "messages": [...],
  "tools": [...],
  "max_tokens": 8192,
  "temperature": 0.7
}
```

### `finish_reason` — 流式返回中的 finish_reason

```json
{
  "ts": "2026-06-23T10:00:01.000",
  "type": "finish_reason",
  "request_id": "r1",
  "source": "ftre",
  "finish_reason": "stop"
}
```

### `response_complete` — 响应结束

```json
{
  "ts": "2026-06-23T10:00:01.100",
  "type": "response_complete",
  "request_id": "r1",
  "source": "ftre",
  "status_code": 200,
  "finish_reasons": ["stop"],
  "saw_stop": true,
  "elapsed_ms": 1100,
  "response_bytes": 2048
}
```

### `proxy_error` — 代理调用上游失败

```json
{
  "ts": "2026-06-23T10:00:02.000",
  "type": "proxy_error",
  "request_id": "r1",
  "source": "ftre",
  "error": "ConnectionRefusedError",
  "elapsed_ms": 50
}
```

> **安全**：日志不会记录 `Authorization`、`api-key`、`x-api-key` 等敏感请求头。

## Web 日志查看器

访问 `http://127.0.0.1:19570/` 打开内置日志查看页面：

- **左侧列表**：按时间倒序展示最近的请求，显示模型名、来源、finish_reason 标签、耗时
- **搜索框**：按 model / request_id / message 内容实时过滤
- **来源筛选**：按 `X-LLM-Debug-Source` 值过滤
- **右侧详情**：展示选中请求的完整 messages、tools、finish_reason、响应状态码、耗时
- **复制按钮**：一键复制 Messages（格式化 JSON）、单条 message、原始事件

## 项目结构

```
ftre-llm-debug-proxy/
├── src/llm_debug_proxy/
│   ├── __init__.py
│   └── main.py          # 代理服务 + 日志查看器 + 配置读取
├── tests/
│   └── test_proxy_core.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## 技术栈

- Python 3.12+
- FastAPI + Uvicorn（HTTP 服务）
- httpx（上游请求转发）
- 无前端依赖（Web 页面内嵌 HTML/CSS/JS）
