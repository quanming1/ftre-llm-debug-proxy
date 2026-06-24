"""Migrate JSONL logs to SQLite."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")
DB_PATH = Path("logs/proxy.db")


def migrate():
    if DB_PATH.exists():
        print(f"DB already exists at {DB_PATH}, skipping migration")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            source TEXT,
            ts TEXT,
            method TEXT,
            path TEXT,
            model TEXT,
            stream INTEGER,
            messages TEXT,
            tools TEXT,
            max_tokens INTEGER,
            temperature REAL,
            status_code INTEGER,
            finish_reasons TEXT,
            elapsed_ms REAL,
            error TEXT,
            request_body TEXT,
            response_body TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            type TEXT,
            data TEXT,
            ts TEXT,
            FOREIGN KEY (request_id) REFERENCES requests(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_request ON events(request_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts DESC)")

    events = []
    for path in sorted(LOG_DIR.glob("llm-proxy-*.jsonl")):
        print(f"Reading {path.name}...")
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    grouped: dict[str, dict] = {}
    for ev in events:
        rid = ev.get("request_id", "")
        if not rid:
            continue
        if rid not in grouped:
            grouped[rid] = {"request": None, "response": None, "events": []}
        if ev.get("type") == "request":
            grouped[rid]["request"] = ev
        elif ev.get("type") == "response_complete":
            grouped[rid]["response"] = ev
        grouped[rid]["events"].append(ev)

    count = 0
    for rid, g in grouped.items():
        req = g["request"] or {}
        resp = g["response"] or {}
        try:
            conn.execute(
                """INSERT INTO requests
                   (id, source, ts, method, path, model, stream, messages, tools,
                    max_tokens, temperature, status_code, finish_reasons,
                    elapsed_ms, error, request_body, response_body)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    req.get("source") or resp.get("source"),
                    req.get("ts") or resp.get("ts"),
                    req.get("method"),
                    req.get("path"),
                    req.get("model"),
                    1 if req.get("stream") else 0,
                    json.dumps(req.get("messages"), ensure_ascii=False) if req.get("messages") else None,
                    json.dumps(req.get("tools"), ensure_ascii=False) if req.get("tools") else None,
                    req.get("max_tokens"),
                    req.get("temperature"),
                    resp.get("status_code"),
                    json.dumps(resp.get("finish_reasons") or []),
                    resp.get("elapsed_ms"),
                    resp.get("error"),
                    json.dumps(req, ensure_ascii=False, default=str),
                    json.dumps(resp, ensure_ascii=False, default=str) if resp else None,
                ),
            )
            for ev in g["events"]:
                conn.execute(
                    "INSERT INTO events (request_id, type, data, ts) VALUES (?,?,?,?)",
                    (rid, ev.get("type"), json.dumps(ev, ensure_ascii=False, default=str),
                     ev.get("ts", datetime.now().isoformat())),
                )
            count += 1
        except Exception as e:
            print(f"  Error on {rid}: {e}")

    conn.commit()
    conn.close()
    print(f"Migrated {count} requests, {len(events)} events to {DB_PATH}")


if __name__ == "__main__":
    migrate()