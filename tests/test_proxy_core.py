from __future__ import annotations

from pathlib import Path

from llm_debug_proxy.main import (
    SSEFinishReasonParser,
    build_upstream_url,
    forward_headers,
    load_provider_from_ftre_config,
    read_log_events,
    summarize_requests,
)


def test_sse_parser_handles_split_finish_reason_line():
    parser = SSEFinishReasonParser()

    assert parser.feed(b'data: {"choices":[{"delta":{}') == []
    reasons = parser.feed(b',"finish_reason":"stop"}]}\n\n')

    assert reasons == ["stop"]


def test_forward_headers_replaces_authorization():
    headers = {
        "Authorization": "Bearer client-key",
        "X-LLM-Debug-Source": "ftre",
        "Connection": "keep-alive",
    }

    forwarded = forward_headers(headers, "upstream-key")

    assert forwarded["Authorization"] == "Bearer upstream-key"
    assert forwarded["X-LLM-Debug-Source"] == "ftre"
    assert "Connection" not in forwarded


def test_build_upstream_url():
    assert (
        build_upstream_url("https://example.test/v1", "/chat/completions", "a=1")
        == "https://example.test/v1/chat/completions?a=1"
    )


def test_build_upstream_url_deduplicates_v1_prefix():
    assert (
        build_upstream_url("https://example.test/v1", "/v1/chat/completions", "")
        == "https://example.test/v1/chat/completions"
    )


def test_load_provider_from_invalid_ftre_config(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
        {
          "providers": {
            "target": {
              "api_key": "sk-target",
              "api_base": "https://llm-gateway.mlamp.cn/v1"
            },
            "broken": {"api_key": "unterminated
          }
        }
        """,
        encoding="utf-8",
    )

    api_base, api_key = load_provider_from_ftre_config(
        config_path,
        "https://llm-gateway.mlamp.cn/v1",
    )

    assert api_base == "https://llm-gateway.mlamp.cn/v1"
    assert api_key == "sk-target"


def test_read_and_summarize_log_events(tmp_path: Path):
    log_path = tmp_path / "llm-proxy-20260623.jsonl"
    log_path.write_text(
        "\n".join(
            [
                '{"ts":"2026-06-23T10:00:00.000","type":"request","request_id":"r1","source":"ftre","model":"qwen","path":"/v1/chat/completions","messages":[{"role":"user","content":"hi"}],"tools":[{"type":"function"}]}',
                '{"ts":"2026-06-23T10:00:01.000","type":"finish_reason","request_id":"r1","source":"ftre","finish_reason":"stop"}',
                '{"ts":"2026-06-23T10:00:01.100","type":"response_complete","request_id":"r1","source":"ftre","status_code":200,"finish_reasons":["stop"],"saw_stop":true,"elapsed_ms":1100}',
            ]
        ),
        encoding="utf-8",
    )

    sessions = summarize_requests(read_log_events(tmp_path, limit=10))

    assert sessions[0]["request_id"] == "r1"
    assert sessions[0]["source"] == "ftre"
    assert sessions[0]["finish_reasons"] == ["stop"]
    assert sessions[0]["message_count"] == 1
    assert sessions[0]["tool_count"] == 1
