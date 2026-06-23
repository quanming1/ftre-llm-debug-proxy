# LLM Debug Proxy

独立的 OpenAI-compatible 本地代理，用来对比不同项目发给模型供应商的请求和返回。

## 启动

```powershell
cd E:\ftre-llm-debug-proxy
$env:LLM_PROXY_UPSTREAM_BASE = "https://llm-gateway.mlamp.cn/v1"
$env:LLM_PROXY_API_KEY = "你的真实 key"
py -3.12 -m llm_debug_proxy.main --port 19570 --log-dir .\logs
```

如果要从 ftre 配置里读取明略网关 key：

```powershell
py -3.12 -m llm_debug_proxy.main `
  --port 19570 `
  --from-ftre-config "$env:USERPROFILE\.ftre\config.json" `
  --provider-api-base "https://llm-gateway.mlamp.cn/v1" `
  --log-dir .\logs
```

## 接入项目

把任意项目的 OpenAI `base_url` / `api_base` 指向：

```text
http://127.0.0.1:19570/v1
```

API key 可以继续填原项目里的值；代理不会用客户端传来的 key，而是用启动时配置的 upstream key 转发。

为了区分不同项目，建议请求头加：

```text
X-LLM-Debug-Source: ftre
```

如果项目不方便加 header，日志里仍会记录 `user-agent`、路径、模型、请求 ID。

## 日志

JSONL 日志写到 `logs\llm-proxy-YYYYMMDD.jsonl`，每行一个事件：

- `request`：请求体里的 `messages`、`tools`、`model`、`stream`
- `finish_reason`：流式返回中捕获到的 finish reason
- `response_complete`：状态码、耗时、所有 finish reason、是否看到 `stop`
- `proxy_error`：代理调用 upstream 失败

不会记录 Authorization / API key。
