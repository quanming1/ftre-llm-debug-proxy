import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'

interface SessionSummary {
  request_id: string
  source: string
  ts: string
  model: string
  path: string
  status_code: number
  finish_reasons: string[]
  elapsed_ms: number
  error: string | null
  message_count: number
  tool_count: number
}

interface LogsResponse {
  log_dir: string
  files: string[]
  sources: string[]
  sessions: SessionSummary[]
}

interface DetailResponse {
  session: SessionDetail | null
}

interface SessionDetail {
  request_id: string
  messages: any[]
  tools: any[]
  events: any[]
  request_body: any
  response_body: any
  [key: string]: any
}

const PAGE_SIZE = 50

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c))
}

export default function App() {
  const [data, setData] = useState<LogsResponse | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [source, setSource] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [status, setStatus] = useState('加载中...')

  const selectedRef = useRef(selected)
  selectedRef.current = selected

  const fetchLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '800', source, q: query })
      const res = await fetch(`/api/logs?${params}`)
      const d: LogsResponse = await res.json()
      setData(d)
      setStatus(`${d.sessions.length} requests · ${d.log_dir}`)
      if (!selectedRef.current || !d.sessions.some(s => s.request_id === selectedRef.current)) {
        setSelected(d.sessions[0]?.request_id || null)
      }
    } catch (e) {
      setStatus('加载失败')
    }
  }, [source, query])

  const fetchDetail = useCallback(async (requestId: string) => {
    try {
      const res = await fetch(`/api/logs/${requestId}`)
      const d: DetailResponse = await res.json()
      setDetail(d.session)
    } catch {
      setDetail(null)
    }
  }, [])

  useEffect(() => {
    fetchLogs()
    const interval = setInterval(fetchLogs, 10000)
    return () => clearInterval(interval)
  }, [fetchLogs])

  useEffect(() => {
    if (selected) {
      fetchDetail(selected)
      setPage(0)
    }
  }, [selected, fetchDetail])

  const sessions = data?.sessions || []
  const totalPages = Math.ceil(sessions.length / PAGE_SIZE)
  const pageStart = page * PAGE_SIZE
  const pageItems = sessions.slice(pageStart, pageStart + PAGE_SIZE)
  const activeDetail = detail || null

  return (
    <div className="app">
      <header className="topbar">
        <h1>LLM Debug Proxy</h1>
        <div className="toolbar">
          <input
            placeholder="搜索 model / request_id / message"
            value={query}
            onChange={e => { setQuery(e.target.value); setPage(0) }}
          />
          <select value={source} onChange={e => { setSource(e.target.value); setPage(0) }}>
            <option value="">全部来源</option>
            {(data?.sources || []).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={fetchLogs}>刷新</button>
          <span className="status">{status}</span>
        </div>
      </header>

      <main className="main">
        <div className="list-panel">
          <div className="list">
            {pageItems.length === 0 ? (
              <div className="empty">暂无日志</div>
            ) : (
              pageItems.map(item => (
                <button
                  key={item.request_id}
                  className={`row ${item.request_id === selected ? 'active' : ''}`}
                  onClick={() => setSelected(item.request_id)}
                >
                  <div className="row-main">
                    <div className="row-title">
                      <span className="model">{item.model || '(no model)'}</span>
                      {item.error && <span className="pill err">error</span>}
                    </div>
                    <div className="source">{item.source || 'unknown'}</div>
                    <div className="meta">
                      <span>{item.ts}</span>
                      <span>{item.path}</span>
                      <span>{item.message_count} msgs</span>
                      <span>{item.tool_count} tools</span>
                    </div>
                  </div>
                  <div className="tags">
                    {item.status_code && (
                      <span className={`pill ${item.status_code >= 400 ? 'err' : 'stop'}`}>{item.status_code}</span>
                    )}
                    {(item.finish_reasons || []).map(r => (
                      <span key={r} className={`pill ${r === 'stop' ? 'stop' : 'warn'}`}>{r}</span>
                    ))}
                  </div>
                </button>
              ))
            )}
          </div>
          {totalPages > 1 && (
            <div className="pagination">
              <button disabled={page <= 0} onClick={() => setPage(p => p - 1)}>← 上一页</button>
              <span>{pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, sessions.length)} / {sessions.length}</span>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>下一页 →</button>
            </div>
          )}
        </div>

        <div className="detail-panel">
          {activeDetail ? (
            <DetailView item={activeDetail} />
          ) : (
            <div className="empty">选择一条请求查看详情</div>
          )}
        </div>
      </main>
    </div>
  )
}

function DetailView({ item }: { item: SessionDetail }) {
  const [tab, setTab] = useState<'summary' | 'messages' | 'events' | 'request'>('summary')
  const [msgPage, setMsgPage] = useState(1)
  const MSG_PAGE_SIZE = 20

  const messages = item.messages || []
  const totalMsgPages = Math.ceil(messages.length / MSG_PAGE_SIZE)
  const visibleMessages = messages.slice(0, msgPage * MSG_PAGE_SIZE)
  const hasMore = msgPage < totalMsgPages

  // Reset msg page when switching requests
  useEffect(() => { setMsgPage(1) }, [item.request_id])

  return (
    <div className="detail">
      <div className="detail-tabs">
        {(['summary', 'messages', 'events', 'request'] as const).map(t => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t === 'summary' ? '摘要' : t === 'messages' ? `Messages (${messages.length})` : t === 'events' ? `事件 (${(item.events || []).length})` : '请求体'}
          </button>
        ))}
      </div>

      <div className="detail-body">
        {tab === 'summary' && (
          <div className="kv-grid">
            <KV label="Request ID" value={item.request_id} />
            <KV label="Source" value={item.source} />
            <KV label="Time" value={item.ts} />
            <KV label="Model" value={item.model} />
            <KV label="Path" value={item.path} />
            <KV label="Status" value={item.status_code} />
            <KV label="Finish" value={(item.finish_reasons || []).join(', ')} />
            <KV label="Elapsed" value={item.elapsed_ms != null ? `${item.elapsed_ms}ms` : ''} />
            <KV label="Messages" value={item.message_count} />
            <KV label="Tools" value={item.tool_count} />
            {item.error && <KV label="Error" value={item.error} />}
          </div>
        )}

        {tab === 'messages' && (
          <div className="messages">
            {visibleMessages.map((msg: any, i: number) => (
              <MessageBlock key={i} msg={msg} index={i} />
            ))}
            {hasMore && (
              <button className="load-more" onClick={() => setMsgPage(p => p + 1)}>
                加载更多 ({msgPage * MSG_PAGE_SIZE}/{messages.length})
              </button>
            )}
          </div>
        )}

        {tab === 'events' && (
          <div>
            <div className="msg-header">
              <span>原始事件 ({(item.events || []).length})</span>
              <button className="copy-btn" onClick={() => navigator.clipboard.writeText(JSON.stringify(item.events || [], null, 2))}>复制全部</button>
            </div>
            <pre className="raw-json">{JSON.stringify(item.events || [], null, 2)}</pre>
          </div>
        )}

        {tab === 'request' && (
          <div>
            <div className="msg-header">
              <span>请求体</span>
              <button className="copy-btn" onClick={() => navigator.clipboard.writeText(JSON.stringify(item.request_body || {}, null, 2))}>复制</button>
            </div>
            <pre className="raw-json">{JSON.stringify(item.request_body || {}, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  )
}

function MessageBlock({ msg, index }: { msg: any; index: number }) {
  const [collapsed, setCollapsed] = useState(true)
  const role = msg.role || 'unknown'
  const preview = JSON.stringify(msg).substring(0, 120)

  return (
    <div className="msg-block">
      <div className="msg-header" onClick={() => setCollapsed(!collapsed)} style={{ cursor: 'pointer' }}>
        <span>
          <span className={`role role-${role}`}>{role}</span>
          <span className="msg-index">#{index + 1}</span>
        </span>
        <span className="msg-preview">{collapsed ? preview : ''}</span>
        <button className="copy-btn" onClick={e => { e.stopPropagation(); navigator.clipboard.writeText(JSON.stringify(msg, null, 2)) }}>
          {collapsed ? '展开' : '复制'}
        </button>
      </div>
      {!collapsed && (
        <pre className="msg-body">{JSON.stringify(msg, null, 2)}</pre>
      )}
    </div>
  )
}

function KV({ label, value }: { label: string; value: any }) {
  return (
    <div className="kv">
      <div className="k">{label}</div>
      <div className="v">{escapeHtml(String(value ?? ''))}</div>
    </div>
  )
}