from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

logger = logging.getLogger("llm_debug_proxy")

DEFAULT_UPSTREAM_BASE = "https://llm-gateway.mlamp.cn/v1"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
SENSITIVE_HEADERS = {"authorization", "api-key", "x-api-key"}
LOG_VIEWER_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LLM Debug Proxy</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f5f7;
      --panel: #ffffff;
      --panel-2: #f9fafb;
      --line: #d9dee7;
      --text: #18202f;
      --muted: #687386;
      --accent: #1769aa;
      --accent-2: #16835f;
      --warn: #b76b00;
      --err: #b42318;
      --mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
      --sans: Inter, "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      font-size: 14px;
      overflow: hidden;
    }
    header {
      height: 48px;
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
      white-space: nowrap;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
    }
    input, select, button {
      height: 30px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 0 9px;
      font: inherit;
    }
    input { min-width: 220px; }
    button {
      cursor: pointer;
      font-weight: 600;
    }
    button:hover { border-color: var(--accent); color: var(--accent); }
    .status {
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    main {
      height: calc(100vh - 48px);
      display: grid;
      grid-template-columns: minmax(320px, 38vw) 1fr;
      min-width: 0;
    }
    .list {
      border-right: 1px solid var(--line);
      background: var(--panel);
      overflow: auto;
    }
    .empty {
      padding: 28px 18px;
      color: var(--muted);
    }
    .row {
      width: 100%;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      padding: 11px 12px;
      border: 0;
      border-bottom: 1px solid #eef1f5;
      background: transparent;
      text-align: left;
      border-radius: 0;
      height: auto;
    }
    .row:hover { background: #f3f7fb; }
    .row.active {
      background: #eaf3fb;
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .row-main { min-width: 0; }
    .row-title {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      margin-bottom: 5px;
    }
    .model {
      font-weight: 650;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .source {
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      height: 20px;
      padding: 0 7px;
      border-radius: 999px;
      background: #eef2f7;
      color: #3b4658;
      font-size: 12px;
      white-space: nowrap;
    }
    .pill.stop { background: #e7f5ef; color: var(--accent-2); }
    .pill.err { background: #fdecec; color: var(--err); }
    .pill.warn { background: #fff3dc; color: var(--warn); }
    .detail {
      min-width: 0;
      overflow: auto;
      background: var(--panel-2);
      padding: 14px;
    }
    .section {
      margin-bottom: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .section h2 {
      margin: 0;
      padding: 10px 12px;
      font-size: 13px;
      border-bottom: 1px solid #eef1f5;
      background: #fbfcfe;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .kv {
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 8px;
      padding: 10px 12px;
      border-bottom: 1px solid #f0f2f5;
    }
    .kv:last-child { border-bottom: 0; }
    .k { color: var(--muted); }
    .v {
      min-width: 0;
      overflow-wrap: anywhere;
      font-family: var(--mono);
      font-size: 12px;
    }
    pre {
      margin: 0;
      padding: 12px;
      overflow: auto;
      max-height: 48vh;
      font-family: var(--mono);
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .message {
      border-top: 1px solid #eef1f5;
    }
    .message:first-of-type { border-top: 0; }
    .message-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 9px 12px;
      background: #fbfcfe;
      color: var(--muted);
      font-size: 12px;
    }
    .role {
      font-weight: 700;
      color: var(--text);
    }
    .copy-message {
      height: 24px;
      margin-left: 8px;
      padding: 0 8px;
      font-size: 12px;
      font-weight: 600;
      color: var(--accent);
      border-color: #b9d3ea;
      background: #f4f9fd;
    }
    @media (max-width: 860px) {
      body { overflow: auto; }
      header { height: auto; min-height: 48px; flex-wrap: wrap; padding: 10px; }
      main { height: auto; grid-template-columns: 1fr; }
      .list { max-height: 42vh; border-right: 0; border-bottom: 1px solid var(--line); }
      input { min-width: 0; flex: 1; }
    }
  </style>
</head>
<body>
  <header>
    <h1>LLM Debug Proxy</h1>
    <div class="toolbar">
      <input id="q" placeholder="搜索 model / request_id / message" />
      <select id="source"><option value="">全部来源</option></select>
      <button id="refresh">刷新</button>
      <span id="status" class="status"></span>
    </div>
  </header>
  <main>
    <aside id="list" class="list"></aside>
    <section id="detail" class="detail"></section>
  </main>
  <script>
    const state = {
      sessions: [],
      selected: null,
      selectedFingerprint: "",
      loading: false,
      reloadQueued: false,
      lastDetailInteraction: 0,
    };
    const listEl = document.getElementById("list");
    const detailEl = document.getElementById("detail");
    const sourceEl = document.getElementById("source");
    const qEl = document.getElementById("q");
    const statusEl = document.getElementById("status");

    document.getElementById("refresh").addEventListener("click", () => scheduleLoad());
    qEl.addEventListener("input", debounce(() => scheduleLoad(), 250));
    sourceEl.addEventListener("change", () => scheduleLoad());
    detailEl.addEventListener("scroll", markDetailInteraction, true);
    detailEl.addEventListener("wheel", markDetailInteraction, { passive: true });
    detailEl.addEventListener("pointermove", markDetailInteraction);
    detailEl.addEventListener("pointerdown", markDetailInteraction);
    detailEl.addEventListener("click", handleDetailClick);
    setInterval(() => scheduleLoad(), 5000);

    function debounce(fn, ms) {
      let timer;
      return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
      };
    }

    function scheduleLoad() {
      if (state.loading) {
        state.reloadQueued = true;
        return;
      }
      load().catch(err => {
        statusEl.textContent = err.message || String(err);
      });
    }

    function markDetailInteraction() {
      state.lastDetailInteraction = Date.now();
    }

    function handleDetailClick(event) {
      const button = event.target.closest("[data-copy-message], [data-copy-messages], [data-copy-events]");
      if (!button) {
        return;
      }
      if (button.hasAttribute("data-copy-messages")) {
        const item = state.sessions.find(s => s.request_id === state.selected);
        copyText(JSON.stringify(item?.messages || [], null, 2), "已复制全部 Messages");
        return;
      }
      if (button.hasAttribute("data-copy-events")) {
        const item = state.sessions.find(s => s.request_id === state.selected);
        copyText(JSON.stringify(item?.events || [], null, 2), "已复制原始事件");
        return;
      }
      const key = button.getAttribute("data-copy-message");
      const target = detailEl.querySelector(`[data-scroll-key="${key}"]`);
      copyText(target?.textContent || "", `已复制 ${key}`);
    }

    async function load() {
      state.loading = true;
      const previousSelected = state.selected;
      const listScrollTop = listEl.scrollTop;
      const detailScrollState = captureDetailScrollState();
      try {
        const params = new URLSearchParams({
          limit: "800",
          source: sourceEl.value,
          q: qEl.value.trim(),
        });
        const res = await fetch(`/api/logs?${params}`);
        const data = await res.json();
        state.sessions = data.sessions || [];
        statusEl.textContent = `${state.sessions.length} requests ? ${data.log_dir}`;
        renderSources(data.sources || []);
        if (!state.selected || !state.sessions.some(s => s.request_id === state.selected)) {
          state.selected = state.sessions[0]?.request_id || null;
        }
        const keepScroll = previousSelected === state.selected;
        renderList({ scrollTop: keepScroll ? listScrollTop : 0 });
        renderDetail({
          scrollState: keepScroll ? detailScrollState : null,
          freeze: keepScroll,
        });
      } finally {
        state.loading = false;
        if (state.reloadQueued) {
          state.reloadQueued = false;
          scheduleLoad();
        }
      }
    }

    function renderSources(sources) {
      const current = sourceEl.value;
      sourceEl.innerHTML = `<option value="">全部来源</option>` + sources.map(src =>
        `<option value="${escapeAttr(src)}">${escapeHtml(src)}</option>`
      ).join("");
      sourceEl.value = sources.includes(current) ? current : "";
    }

    function renderList(options = {}) {
      if (!state.sessions.length) {
        listEl.innerHTML = `<div class="empty">暂无日志。让项目通过代理发起一次请求后，这里会自动刷新。</div>`;
        listEl.scrollTop = 0;
        return;
      }
      listEl.innerHTML = state.sessions.map(item => {
        const active = item.request_id === state.selected ? " active" : "";
        const reasons = (item.finish_reasons || []).map(reason =>
          `<span class="pill ${reason === "stop" ? "stop" : "warn"}">${escapeHtml(reason)}</span>`
        ).join("");
        const statusClass = item.error ? "err" : item.status_code >= 400 ? "err" : "";
        return `<button class="row${active}" data-id="${escapeAttr(item.request_id)}">
          <div class="row-main">
            <div class="row-title">
              <span class="model">${escapeHtml(item.model || "(no model)")}</span>
              ${item.error ? `<span class="pill err">error</span>` : ""}
            </div>
            <div class="source">${escapeHtml(item.source || "unknown")}</div>
            <div class="meta">
              <span>${escapeHtml(item.ts || "")}</span>
              <span>${escapeHtml(item.path || "")}</span>
              <span>${item.message_count || 0} messages</span>
              <span>${item.tool_count || 0} tools</span>
            </div>
          </div>
          <div class="meta">
            ${item.status_code ? `<span class="pill ${statusClass}">${item.status_code}</span>` : ""}
            ${reasons}
          </div>
        </button>`;
      }).join("");
      listEl.querySelectorAll(".row").forEach(row => {
        row.addEventListener("click", () => {
          state.selected = row.dataset.id;
          renderList({ scrollTop: listEl.scrollTop });
          state.selectedFingerprint = "";
          renderDetail({ scrollState: null });
        });
      });
      if (typeof options.scrollTop === "number") {
        listEl.scrollTop = options.scrollTop;
      }
    }

    function renderDetail(options = {}) {
      const item = state.sessions.find(s => s.request_id === state.selected);
      if (!item) {
        detailEl.innerHTML = `<div class="empty">选择一条请求查看详情。</div>`;
        detailEl.scrollTop = 0;
        state.selectedFingerprint = "";
        return;
      }
      const fingerprint = JSON.stringify({
        request_id: item.request_id,
        status_code: item.status_code,
        finish_reasons: item.finish_reasons,
        elapsed_ms: item.elapsed_ms,
        error: item.error,
        messages: item.messages,
        tools: item.tools,
        events: item.events,
      });
      if (options.freeze && state.selectedFingerprint) {
        restoreDetailScrollState(options.scrollState);
        return;
      }
      if (fingerprint === state.selectedFingerprint) {
        restoreDetailScrollState(options.scrollState);
        return;
      }
      state.selectedFingerprint = fingerprint;
      detailEl.innerHTML = `
        <div class="section">
          <h2>请求概览</h2>
          ${kv("request_id", item.request_id)}
          ${kv("source", item.source)}
          ${kv("model", item.model)}
          ${kv("path", item.path)}
          ${kv("status", item.status_code ?? "")}
          ${kv("finish_reason", (item.finish_reasons || []).join(", "))}
          ${kv("elapsed_ms", item.elapsed_ms ?? "")}
          ${item.error ? kv("error", item.error) : ""}
        </div>
        <div class="section">
          <h2><span>Messages</span><button class="copy-message" data-copy-messages="1">复制全部</button></h2>
          ${(item.messages || []).map(renderMessage).join("") || "<pre>[]</pre>"}
        </div>
        <div class="section">
          <h2>Tools</h2>
          <pre data-scroll-key="tools">${escapeHtml(JSON.stringify(item.tools || [], null, 2))}</pre>
        </div>
        <div class="section">
          <h2><span>原始事件</span><button class="copy-message" data-copy-events="1">复制</button></h2>
          <pre data-scroll-key="events">${escapeHtml(JSON.stringify(item.events || [], null, 2))}</pre>
        </div>
      `;
      restoreDetailScrollState(options.scrollState);
    }

    function renderMessage(message, index) {
      const content = typeof message.content === "string"
        ? message.content
        : JSON.stringify(message.content, null, 2);
      return `<div class="message">
        <div class="message-head">
          <span><span class="role">${escapeHtml(message.role || "unknown")}</span> #${index + 1}</span>
          <span>
            <span>${content ? content.length : 0} chars</span>
            <button class="copy-message" data-copy-message="message-${index}">复制</button>
          </span>
        </div>
        <pre data-scroll-key="message-${index}">${escapeHtml(content || "")}</pre>
      </div>`;
    }

    async function copyText(text, label) {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.left = "-9999px";
        document.body.appendChild(area);
        area.focus();
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      statusEl.textContent = label;
    }

    function captureDetailScrollState() {
      const blocks = {};
      detailEl.querySelectorAll("[data-scroll-key]").forEach(el => {
        blocks[el.dataset.scrollKey] = {
          top: el.scrollTop,
          left: el.scrollLeft,
        };
      });
      return {
        top: detailEl.scrollTop,
        left: detailEl.scrollLeft,
        blocks,
      };
    }

    function shouldFreezeDetail(scrollState) {
      if (!scrollState) {
        return false;
      }
      if ((scrollState.top || 0) > 0 || (scrollState.left || 0) > 0) {
        return true;
      }
      for (const saved of Object.values(scrollState.blocks || {})) {
        if ((saved.top || 0) > 0 || (saved.left || 0) > 0) {
          return true;
        }
      }
      if (Date.now() - state.lastDetailInteraction < 30000) {
        return true;
      }
      if (detailEl.contains(document.activeElement)) {
        return true;
      }
      const selection = window.getSelection && window.getSelection();
      return Boolean(selection && selection.toString());
    }

    function restoreDetailScrollState(scrollState) {
      if (!scrollState) {
        detailEl.scrollTop = 0;
        detailEl.scrollLeft = 0;
        return;
      }
      const apply = () => {
        detailEl.scrollTop = scrollState.top || 0;
        detailEl.scrollLeft = scrollState.left || 0;
        detailEl.querySelectorAll("[data-scroll-key]").forEach(el => {
          const saved = scrollState.blocks?.[el.dataset.scrollKey];
          if (saved) {
            el.scrollTop = saved.top || 0;
            el.scrollLeft = saved.left || 0;
          }
        });
      };
      apply();
      requestAnimationFrame(apply);
      setTimeout(apply, 0);
    }

    function kv(key, value) {
      return `<div class="kv"><div class="k">${escapeHtml(key)}</div><div class="v">${escapeHtml(String(value ?? ""))}</div></div>`;
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[ch]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    scheduleLoad();
  </script>
</body>
</html>
"""


@dataclass
class ProxySettings:
    upstream_base: str
    api_key: str
    log_dir: Path
    source_header: str = "x-llm-debug-source"

    def __post_init__(self) -> None:
        self.upstream_base = self.upstream_base.rstrip("/")
        self.db_path = (self.log_dir / "proxy.db") if (self.log_dir.is_dir() or not self.log_dir.suffix) else self.log_dir
        self.store = Store(self.db_path)


class Store:
    """SQLite-based storage."""
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, source TEXT, ts TEXT, method TEXT, path TEXT,
                    model TEXT, stream INTEGER,
                    message_count INTEGER DEFAULT 0, tool_count INTEGER DEFAULT 0,
                    messages TEXT, tools TEXT,
                    max_tokens INTEGER, temperature REAL, status_code INTEGER,
                    finish_reasons TEXT, elapsed_ms REAL, error TEXT,
                    request_body TEXT, response_body TEXT
                )
            """)
            # Migration: add columns if missing
            try:
                conn.execute("ALTER TABLE requests ADD COLUMN message_count INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE requests ADD COLUMN tool_count INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL, type TEXT, data TEXT, ts TEXT,
                    FOREIGN KEY (request_id) REFERENCES requests(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_request ON events(request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts DESC)")

    async def write_request(self, rid, source, ts, method, path, model, stream, messages, tools, max_tokens, temperature, request_body):
        import sqlite3
        async with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO requests (id,source,ts,method,path,model,stream,message_count,tool_count,messages,tools,max_tokens,temperature,request_body) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid, source, ts, method, path, model, 1 if stream else 0,
                     len(messages) if isinstance(messages, list) else 0,
                     len(tools) if isinstance(tools, list) else 0,
                     json.dumps(messages, ensure_ascii=False) if messages is not None else None,
                     json.dumps(tools, ensure_ascii=False) if tools is not None else None,
                     max_tokens, temperature,
                     json.dumps(request_body, ensure_ascii=False, default=str) if request_body else None))

    async def write_response(self, rid, status_code, finish_reasons, elapsed_ms, error, response_body):
        import sqlite3
        async with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE requests SET status_code=?,finish_reasons=?,elapsed_ms=?,error=?,response_body=? WHERE id=?",
                    (status_code, json.dumps(finish_reasons or []), elapsed_ms, error,
                     json.dumps(response_body, ensure_ascii=False, default=str) if response_body else None, rid))

    async def write_event(self, rid, event_type, data, ts=None):
        import sqlite3
        async with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO events (request_id,type,data,ts) VALUES (?,?,?,?)",
                    (rid, event_type, json.dumps(data, ensure_ascii=False, default=str),
                     ts or datetime.now().isoformat(timespec="milliseconds")))

    def list_requests(self, limit=200, source="", query=""):
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            where, params = [], []
            if source:
                where.append("source = ?"); params.append(source)
            if query:
                where.append("(model LIKE ? OR id LIKE ?)"); params.extend([f"%{query}%", f"%{query}%"])
            sql = "SELECT id, source, ts, method, path, model, stream, message_count, tool_count, status_code, finish_reasons, elapsed_ms, error FROM requests"
            if where: sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY ts DESC LIMIT ?"; params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["request_id"] = item.pop("id")
                item["finish_reasons"] = json.loads(item.get("finish_reasons") or "[]")
                item["stream"] = bool(item.get("stream"))
                result.append(item)
            return result

    def get_request(self, request_id):
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
            if not row: return None
            item = dict(row)
            item["request_id"] = item.pop("id")
            item["finish_reasons"] = json.loads(item.get("finish_reasons") or "[]")
            item["stream"] = bool(item.get("stream"))
            item["messages"] = json.loads(item.get("messages") or "[]")
            item["tools"] = json.loads(item.get("tools") or "[]")
            item["request_body"] = safe_json_loads(item.get("request_body") or "{}")
            item["response_body"] = safe_json_loads(item.get("response_body") or "{}")
            item["message_count"] = len(item["messages"])
            item["tool_count"] = len(item["tools"])
            events = conn.execute("SELECT * FROM events WHERE request_id = ? ORDER BY ts", (request_id,)).fetchall()
            item["events"] = [json.loads(e["data"]) for e in events]
            return item

    def get_sources(self):
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute("SELECT DISTINCT source FROM requests WHERE source IS NOT NULL ORDER BY source").fetchall()
            return [r[0] for r in rows]


def create_app(settings: ProxySettings) -> FastAPI:
    app = FastAPI(title="LLM Debug Proxy")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        index_path = Path(__file__).parent.parent.parent / "viewer" / "dist" / "index.html"
        if index_path.exists():
            return index_path.read_text(encoding="utf-8")
        return LOG_VIEWER_HTML  # fallback

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "upstream_base": settings.upstream_base,
            "log_dir": str(settings.log_dir),
        }

    @app.get("/api/logs")
    async def api_logs(limit: int = 200, source: str = "", q: str = "") -> dict[str, Any]:
        sessions = settings.store.list_requests(limit=limit, source=source, query=q)
        sources_list = settings.store.get_sources()
        return {
            "log_dir": str(settings.db_path),
            "files": [],
            "sources": sources_list,
            "sessions": sessions,
        }

    @app.get("/api/logs/{request_id}")
    async def api_log_detail(request_id: str) -> dict[str, Any]:
        session = settings.store.get_request(request_id)
        return {"session": session}

    @app.get("/assets/{path:path}")
    async def assets(path: str):
        from fastapi.responses import FileResponse as FR
        asset_path = Path(__file__).parent.parent.parent / "viewer" / "dist" / "assets" / path
        if asset_path.exists():
            return FR(asset_path)
        return Response(status_code=404)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def proxy(path: str, request: Request):
        if path == "health":
            return await health()
        if path.startswith("api/"):
            return Response(status_code=404)

        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        body = await request.body()
        request_json = decode_json(body)
        source = request.headers.get(settings.source_header) or request.headers.get(
            "user-agent", "unknown"
        )

        ts = datetime.now().isoformat(timespec="milliseconds")
        await settings.store.write_request(
            request_id, source, ts, request.method, path,
            request_json.get("model") if isinstance(request_json, dict) else None,
            request_json.get("stream") if isinstance(request_json, dict) else None,
            request_json.get("messages") if isinstance(request_json, dict) else None,
            request_json.get("tools") if isinstance(request_json, dict) else None,
            request_json.get("max_tokens") if isinstance(request_json, dict) else None,
            request_json.get("temperature") if isinstance(request_json, dict) else None,
            request_json if isinstance(request_json, dict) else None,
        )

        upstream_url = build_upstream_url(settings.upstream_base, path, request.url.query)
        headers = forward_headers(request.headers, settings.api_key)
        client = httpx.AsyncClient(timeout=None)

        try:
            stream_cm = client.stream(
                request.method,
                upstream_url,
                content=body,
                headers=headers,
            )
            upstream = await stream_cm.__aenter__()
        except Exception as exc:
            await client.aclose()
            await settings.store.write_event(
                request_id, "proxy_error",
                {"error": repr(exc), "elapsed_ms": elapsed_ms(started)},
                datetime.now().isoformat(timespec="milliseconds"),
            )
            raise

        content_type = upstream.headers.get("content-type", "")
        response_headers = filter_response_headers(upstream.headers)
        if "text/event-stream" not in content_type:
            try:
                data = await upstream.aread()
                await log_non_stream_response(
                    settings, request_id, source, upstream.status_code, data, started
                )
                return Response(
                    content=data,
                    status_code=upstream.status_code,
                    headers=response_headers,
                    media_type=content_type or None,
                )
            finally:
                await upstream.aclose()
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()

        async def response_iter():
            parser = SSEFinishReasonParser()
            finish_reasons: list[str] = []
            try:
                async for chunk in upstream.aiter_bytes():
                    for reason in parser.feed(chunk):
                        finish_reasons.append(reason)
                        await settings.store.write_event(
                            request_id, "finish_reason",
                            {"finish_reason": reason, "source": source},
                            datetime.now().isoformat(timespec="milliseconds"),
                        )
                    yield chunk
                for reason in parser.close():
                    finish_reasons.append(reason)
                    await settings.store.write_event(
                        request_id, "finish_reason",
                        {"finish_reason": reason, "source": source},
                        datetime.now().isoformat(timespec="milliseconds"),
                    )
            finally:
                await settings.store.write_event(
                    request_id, "response_complete",
                    {"status_code": upstream.status_code, "finish_reasons": finish_reasons,
                     "elapsed_ms": elapsed_ms(started), "source": source},
                    datetime.now().isoformat(timespec="milliseconds"),
                )
                await upstream.aclose()
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()

        return StreamingResponse(
            response_iter(),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=content_type or "text/event-stream",
        )

    return app


class SSEFinishReasonParser:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[str]:
        self._buffer += chunk.decode("utf-8", errors="ignore")
        lines = self._buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._buffer = lines.pop()
        else:
            self._buffer = ""
        return extract_finish_reasons_from_lines(lines)

    def close(self) -> list[str]:
        if not self._buffer:
            return []
        lines = self._buffer.splitlines()
        self._buffer = ""
        return extract_finish_reasons_from_lines(lines)


def extract_finish_reasons_from_lines(lines: list[str]) -> list[str]:
    reasons: list[str] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        payload = decode_json(data.encode("utf-8"))
        if not isinstance(payload, dict):
            continue
        for choice in payload.get("choices") or []:
            if isinstance(choice, dict) and choice.get("finish_reason"):
                reasons.append(str(choice["finish_reason"]))
    return reasons


def build_upstream_url(upstream_base: str, path: str, query: str) -> str:
    base = upstream_base.rstrip("/")
    clean_path = path.lstrip("/")
    if base.endswith("/v1") and clean_path == "v1":
        clean_path = ""
    elif base.endswith("/v1") and clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    url = f"{base}/{clean_path}" if clean_path else base
    if query:
        url += f"?{query}"
    return url


def forward_headers(headers, api_key: str) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "host":
            continue
        if lower in SENSITIVE_HEADERS:
            continue
        forwarded[key] = value
    forwarded["Authorization"] = f"Bearer {api_key}"
    return forwarded


def filter_response_headers(headers) -> dict[str, str]:
    blocked = HOP_BY_HOP_HEADERS | {"content-encoding", "content-length"}
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def decode_json(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


async def log_non_stream_response(
    settings: ProxySettings,
    request_id: str,
    source: str,
    status_code: int,
    data: bytes,
    started: float,
) -> None:
    payload = decode_json(data)
    finish_reasons: list[str] = []
    if isinstance(payload, dict):
        for choice in payload.get("choices") or []:
            if isinstance(choice, dict) and choice.get("finish_reason"):
                finish_reasons.append(str(choice["finish_reason"]))
    await settings.store.write_response(
        request_id, status_code, finish_reasons, elapsed_ms(started),
        None,
        payload if isinstance(payload, dict) else None,
    )


def list_log_files(log_dir: Path) -> list[Path]:
    if not log_dir.exists():
        return []
    return sorted(
        log_dir.glob("llm-proxy-*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def read_log_events(log_dir: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    remaining = limit
    for path in list_log_files(log_dir):
        if remaining <= 0:
            break
        lines = read_tail_lines(path, remaining)
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        remaining = limit - len(events)
    events.sort(key=lambda item: str(item.get("ts", "")), reverse=True)
    return events[:limit]


def read_tail_lines(path: Path, limit: int) -> list[str]:
    if limit <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8") as fp:
            lines = fp.readlines()
    except OSError:
        return []
    return [line.rstrip("\n") for line in lines[-limit:]]


def summarize_requests(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in sorted(events, key=lambda item: str(item.get("ts", ""))):
        request_id = str(event.get("request_id") or "")
        if not request_id:
            continue
        if request_id not in grouped:
            grouped[request_id] = {
                "request_id": request_id,
                "source": event.get("source"),
                "events": [],
                "finish_reasons": [],
            }
            order.append(request_id)
        item = grouped[request_id]
        item["events"].append(event)
        item["source"] = item.get("source") or event.get("source")
        if event.get("type") == "request":
            item.update(
                {
                    "ts": event.get("ts"),
                    "method": event.get("method"),
                    "path": event.get("path"),
                    "model": event.get("model"),
                    "stream": event.get("stream"),
                    "messages": event.get("messages"),
                    "tools": event.get("tools"),
                    "tool_choice": event.get("tool_choice"),
                    "max_tokens": event.get("max_tokens"),
                    "temperature": event.get("temperature"),
                }
            )
        elif event.get("type") == "finish_reason":
            reason = event.get("finish_reason")
            if reason:
                item["finish_reasons"].append(reason)
        elif event.get("type") == "response_complete":
            item.update(
                {
                    "status_code": event.get("status_code"),
                    "elapsed_ms": event.get("elapsed_ms"),
                    "saw_stop": event.get("saw_stop"),
                    "response_json": event.get("response_json"),
                    "response_bytes": event.get("response_bytes"),
                }
            )
            for reason in event.get("finish_reasons") or []:
                item["finish_reasons"].append(reason)
        elif event.get("type") == "proxy_error":
            item["error"] = event.get("error")
            item["elapsed_ms"] = event.get("elapsed_ms")
    sessions = [grouped[request_id] for request_id in reversed(order)]
    for item in sessions:
        item["message_count"] = len(item.get("messages") or [])
        item["tool_count"] = len(item.get("tools") or [])
        item["finish_reasons"] = list(dict.fromkeys(item.get("finish_reasons") or []))
    return sessions


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def load_provider_from_ftre_config(config_path: Path, provider_api_base: str) -> tuple[str, str]:
    text = config_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        for provider in (data.get("providers") or {}).values():
            if (
                isinstance(provider, dict)
                and str(provider.get("api_base", "")).rstrip("/")
                == provider_api_base.rstrip("/")
            ):
                return str(provider["api_base"]), str(provider["api_key"])
    except json.JSONDecodeError:
        logger.warning("ftre config is not valid JSON; using targeted extraction")

    idx = text.find(f'"api_base": "{provider_api_base.rstrip("/")}"')
    if idx < 0:
        raise RuntimeError(f"provider api_base not found: {provider_api_base}")
    start = find_object_start(text, idx)
    end = find_object_end(text, start)
    provider_text = text[start:end]
    api_base = extract_json_string(provider_text, "api_base")
    api_key = extract_json_string(provider_text, "api_key")
    if not api_base or not api_key:
        raise RuntimeError("provider matched but api_base/api_key could not be extracted")
    return api_base, api_key


def find_object_start(text: str, idx: int) -> int:
    pos = idx
    while pos >= 0:
        if text[pos] == "{":
            return pos
        pos -= 1
    raise RuntimeError("could not find object start")


def find_object_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return pos + 1
    raise RuntimeError("could not find object end")


def extract_json_string(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if not match:
        return ""
    return bytes(match.group(1), "utf-8").decode("unicode_escape")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI-compatible LLM debug proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19570)
    parser.add_argument("--upstream-base", default=os.environ.get("LLM_PROXY_UPSTREAM_BASE", DEFAULT_UPSTREAM_BASE))
    parser.add_argument("--api-key", default=os.environ.get("LLM_PROXY_API_KEY", ""))
    parser.add_argument("--log-dir", type=Path, default=Path(os.environ.get("LLM_PROXY_LOG_DIR", "logs")))
    parser.add_argument("--source-header", default=os.environ.get("LLM_PROXY_SOURCE_HEADER", "X-LLM-Debug-Source"))
    parser.add_argument("--from-ftre-config", type=Path)
    parser.add_argument("--provider-api-base", default=DEFAULT_UPSTREAM_BASE)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)-8s - %(name)s - %(message)s",
    )
    args = parse_args()
    upstream_base = args.upstream_base
    api_key = args.api_key
    if args.from_ftre_config:
        upstream_base, api_key = load_provider_from_ftre_config(
            args.from_ftre_config,
            args.provider_api_base,
        )
    if not api_key:
        raise SystemExit("missing upstream API key; set LLM_PROXY_API_KEY or use --from-ftre-config")

    settings = ProxySettings(
        upstream_base=upstream_base,
        api_key=api_key,
        log_dir=args.log_dir,
        source_header=args.source_header.lower(),
    )
    logger.info("proxying %s via http://%s:%s/v1", settings.upstream_base, args.host, args.port)
    logger.info("writing logs to %s", settings.log_dir)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
