// src/components/ChatPanel.jsx
import { useState, useRef, useEffect } from 'react'
import { useApiData } from '../hooks/useApi'
import { Send, Bot, User, AlertCircle, Loader, Sparkles } from 'lucide-react'
import { marked } from 'marked'

const SUGGESTED_QUERIES = [
  "What is our biggest supply chain risk this week?",
  "Which suppliers are exposed to the Middle East situation?",
  "Generate a Monday morning procurement briefing",
  "If Zhejiang Huahai shuts down, what are our options?",
  "What indirect risks has the system detected?",
  "Show me all HIGH and CRITICAL events",
]

function Message({ msg }) {
  const isUser  = msg.role === 'user'
  const isError = msg.role === 'error'

  // Parse markdown to HTML for agent responses
  const renderContent = () => {
    if (msg.role === 'thinking') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Loader size={12} color="#a78bfa" style={{ animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 12, color: '#a78bfa', fontStyle: 'italic' }}>
            Analysing data…
          </span>
        </div>
      )
    }

    // Parse markdown for non-user messages
    if (!isUser && !isError) {
      const html = marked(msg.content, {
        breaks: true,
        gfm: true,
      })
      return (
        <div 
          style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-2)' }}
          dangerouslySetInnerHTML={{ __html: html }}
          className="markdown-content"
        />
      )
    }

    // Plain text for user and error messages
    return (
      <div style={{ fontSize: 13, lineHeight: 1.65, color: isUser ? 'var(--text-1)' : 'var(--text-2)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {msg.content}
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      gap: 10,
      marginBottom: 16,
      alignItems: 'flex-start',
    }}>
      {/* Avatar */}
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: isUser ? '#f59e0b22' : isError ? '#ef444422' : '#a78bfa22',
        border: `1px solid ${isUser ? '#f59e0b44' : isError ? '#ef444444' : '#a78bfa44'}`,
      }}>
        {isUser
          ? <User size={13} color="#f59e0b" />
          : isError
            ? <AlertCircle size={13} color="#ef4444" />
            : <Bot size={13} color="#a78bfa" />
        }
      </div>

      {/* Bubble */}
      <div style={{
        maxWidth: '82%',
        padding: '10px 14px',
        borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
        background: isUser
          ? '#f59e0b18'
          : isError
            ? '#ef444418'
            : 'var(--surface-2)',
        border: `1px solid ${isUser ? '#f59e0b30' : isError ? '#ef444430' : 'var(--surface-3)'}`,
      }}>
        {renderContent()}

        {msg.method && msg.method !== 'error' && (
          <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 6, fontFamily: 'DM Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {msg.method === 'agent' ? '⚡ ReAct agent' : '⚙ direct tool'}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel() {
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const messagesEndRef             = useRef(null)
  const inputRef                   = useRef(null)
  const wsRef                      = useRef(null)
  const [wsConnected, setWsConnected] = useState(false)

  const { data: agentStatus } = useApiData('/agent/status', {}, 0)

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // WebSocket connection
  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket('ws://localhost:8000/api/agent/ws')

        ws.onopen = () => {
          setWsConnected(true)
          wsRef.current = ws
        }

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data)

          if (data.type === 'thinking') {
            // Replace or add thinking message
            setMessages(prev => {
              const filtered = prev.filter(m => m.role !== 'thinking')
              return [...filtered, { role: 'thinking', content: '' }]
            })
          } else if (data.type === 'answer') {
            setMessages(prev => {
              const filtered = prev.filter(m => m.role !== 'thinking')
              return [...filtered, {
                role: 'agent',
                content: data.text,
                method: data.method,
              }]
            })
            setLoading(false)
          } else if (data.type === 'error') {
            setMessages(prev => {
              const filtered = prev.filter(m => m.role !== 'thinking')
              return [...filtered, { role: 'error', content: data.text }]
            })
            setLoading(false)
          }
        }

        ws.onclose = () => {
          setWsConnected(false)
          wsRef.current = null
          // Reconnect after 3s
          setTimeout(connect, 3000)
        }

        ws.onerror = () => {
          ws.close()
        }
      } catch (e) {
        setTimeout(connect, 3000)
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  const sendMessage = async (question) => {
    if (!question.trim() || loading) return

    const userMsg = { role: 'user', content: question }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // Try WebSocket first, fall back to REST
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ question }))
    } else {
      // REST fallback
      try {
        const resp = await fetch('/api/agent/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
        })
        const data = await resp.json()
        setMessages(prev => [...prev, {
          role: 'agent',
          content: data.answer,
          method: data.method,
        }])
      } catch (e) {
        setMessages(prev => [...prev, {
          role: 'error',
          content: `Connection error: ${e.message}`,
        }])
      }
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
      }}>
        <Sparkles size={12} style={{ color: 'var(--amber)' }} />
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 500, color: 'var(--amber)' }}>
          AI AGENT
        </span>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5, marginLeft: 8,
        }}>
          <div style={{
            width: 5, height: 5, borderRadius: '50%',
            background: wsConnected ? '#22c55e' : '#6b7280',
            boxShadow: wsConnected ? '0 0 4px #22c55e88' : 'none',
          }} />
          <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
            {wsConnected ? 'live' : 'connecting…'}
          </span>
        </div>
        {agentStatus && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
            {agentStatus.mode === 'langchain_react' ? '⚡ ReAct' : '⚙ fallback'}
          </span>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
        {messages.length === 0 && (
          <div style={{ paddingTop: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Bot size={16} color="#a78bfa" />
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
                I have access to live supply chain risk data. What would you like to know?
              </span>
            </div>

            <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
              Suggested queries
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {SUGGESTED_QUERIES.map(q => (
                <button key={q} onClick={() => sendMessage(q)}
                  style={{
                    padding: '8px 12px', borderRadius: 6, textAlign: 'left',
                    fontSize: 12, color: 'var(--text-2)', cursor: 'pointer',
                    background: 'var(--surface-2)', border: '1px solid var(--surface-3)',
                    transition: 'all 0.15s', fontFamily: 'IBM Plex Sans, sans-serif',
                  }}
                  onMouseEnter={e => { e.target.style.borderColor = '#f59e0b44'; e.target.style.color = 'var(--text-1)' }}
                  onMouseLeave={e => { e.target.style.borderColor = 'var(--surface-3)'; e.target.style.color = 'var(--text-2)' }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 16px', borderTop: '1px solid var(--surface-3)',
        display: 'flex', gap: 8, flexShrink: 0,
      }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about risks, suppliers, alternates, or request a briefing…"
          rows={1}
          style={{
            flex: 1, background: 'var(--surface-2)', border: '1px solid var(--surface-3)',
            borderRadius: 6, padding: '8px 12px', fontSize: 13, color: 'var(--text-1)',
            fontFamily: 'IBM Plex Sans, sans-serif', outline: 'none', resize: 'none',
            lineHeight: 1.5,
          }}
          onInput={e => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
          }}
          onFocus={e => e.target.style.borderColor = '#f59e0b44'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-3)'}
          disabled={loading}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          style={{
            width: 36, height: 36, borderRadius: 6, border: 'none',
            background: loading || !input.trim() ? 'var(--surface-3)' : '#f59e0b22',
            cursor: loading || !input.trim() ? 'default' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0, transition: 'all 0.15s',
            border: `1px solid ${loading || !input.trim() ? 'var(--surface-3)' : '#f59e0b44'}`,
          }}
        >
          {loading
            ? <Loader size={14} color="#6b7280" />
            : <Send size={14} color={input.trim() ? '#f59e0b' : '#6b7280'} />
          }
        </button>
      </div>

      {/* Spin animation */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
