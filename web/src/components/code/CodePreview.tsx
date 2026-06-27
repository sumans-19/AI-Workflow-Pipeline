import { useState, useEffect } from 'react'
import { Copy, Check, Code2, Edit3, Save, X } from 'lucide-react'
import { Highlight, themes } from 'prism-react-renderer'
import { useSessionStore } from '../../store/sessionStore'
import FileIcon from '../explorer/FileIcon'

export default function CodePreview() {
  const selectedFile = useSessionStore(s => s.selectedFile)
  const fileContents = useSessionStore(s => s.fileContents)
  const selectFile   = useSessionStore(s => s.selectFile)

  const openFiles = Object.keys(fileContents)
  const code      = selectedFile ? fileContents[selectedFile] ?? '' : ''

  const getLanguage = (path: string): string => {
    const ext = path.split('.').pop() || ''
    const map: Record<string, string> = {
      py: 'python', ts: 'typescript', tsx: 'tsx',
      js: 'javascript', jsx: 'jsx', json: 'json',
      css: 'css', html: 'markup', md: 'markdown',
      toml: 'toml', yaml: 'yaml', yml: 'yaml',
    }
    return map[ext] || 'text'
  }

  if (openFiles.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center h-full"
        style={{ color: 'var(--text-3)' }}
      >
        <Code2 size={40} strokeWidth={1.25} style={{ marginBottom: 12, opacity: 0.3 }} />
        <p style={{ fontSize: 14, color: 'var(--text-2)' }}>No files generated yet</p>
        <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
          Generated code will appear here
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>
      {/* File tabs */}
      <div
        className="flex items-center border-b overflow-x-auto"
        style={{
          borderColor: 'var(--border)',
          background: 'var(--bg-panel)',
          flexShrink: 0,
          height: 40,
        }}
      >
        {openFiles.map(f => {
          const name = f.split('/').pop() || f
          const active = f === selectedFile
          return (
            <button
              key={f}
              onClick={() => selectFile(f)}
              className="flex items-center gap-2 h-full border-b-2 flex-shrink-0 transition-all duration-150"
              style={{
                padding: '0 16px',
                borderColor: active ? 'var(--primary)' : 'transparent',
                background: active ? 'var(--bg-active)' : 'transparent',
                color: active ? 'var(--text-1)' : 'var(--text-3)',
                fontSize: 13,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              <FileIcon filename={name} size={13} />
              {name}
            </button>
          )
        })}
      </div>

      {/* Code area */}
      <div className="flex-1 overflow-auto" style={{ position: 'relative' }}>
        {!selectedFile || !code ? (
          <div
            className="flex items-center justify-center h-full"
            style={{ color: 'var(--text-3)', fontSize: 13 }}
          >
            Select a file from the tabs above
          </div>
        ) : (
          <CodeBlock
            code={code}
            language={getLanguage(selectedFile)}
            filename={selectedFile}
          />
        )}
      </div>
    </div>
  )
}

function CodeBlock({ code: initialCode, language, filename }: { code: string; language: string; filename: string }) {
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [code, setCode] = useState(initialCode)
  const [isSaving, setIsSaving] = useState(false)
  
  const sessionId = useSessionStore(s => s.sessionId)

  useEffect(() => {
    if (!isEditing) setCode(initialCode)
  }, [initialCode, isEditing])

  const copy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleSave = async () => {
    if (!sessionId) return
    setIsSaving(true)
    try {
      await fetch(`http://127.0.0.1:8000/api/sessions/${sessionId}/files/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filename, content: code })
      })
      setIsEditing(false)
    } catch (e) {
      console.error("Failed to save file", e)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div style={{ height: '100%', position: 'relative', display: 'flex', flexDirection: 'column' }}>
      {/* Sticky header */}
      <div
        className="flex items-center justify-between"
        style={{
          padding: '0 20px',
          height: 36,
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0
        }}
      >
        <span className="mono" style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {filename}
        </span>
        <div className="flex items-center gap-3">
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            {code.split('\n').length} lines
          </span>
          {isEditing ? (
            <>
              <button
                onClick={() => { setIsEditing(false); setCode(initialCode) }}
                className="flex items-center gap-1.5 transition-all duration-150 hover:bg-[var(--bg-card)]"
                style={{ fontSize: 12, color: 'var(--text-3)', padding: '3px 8px', borderRadius: 6 }}
              >
                <X size={12} /> Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || code === initialCode}
                className="flex items-center gap-1.5 transition-all duration-150"
                style={{
                  fontSize: 12, color: 'var(--primary)',
                  padding: '3px 8px', borderRadius: 6,
                  background: 'var(--primary-dim)',
                  border: '1px solid rgba(99,102,241,0.3)',
                  opacity: (isSaving || code === initialCode) ? 0.5 : 1
                }}
              >
                <Save size={12} /> {isSaving ? 'Saving...' : 'Save'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setIsEditing(true)}
                className="flex items-center gap-1.5 transition-all duration-150 hover:bg-[var(--bg-card)]"
                style={{ fontSize: 12, color: 'var(--text-3)', padding: '3px 8px', borderRadius: 6 }}
              >
                <Edit3 size={12} /> Edit
              </button>
              <button
                onClick={copy}
                className="flex items-center gap-1.5 transition-all duration-150"
                style={{
                  fontSize: 12, color: copied ? 'var(--success)' : 'var(--text-3)',
                  padding: '3px 8px', borderRadius: 6,
                  background: copied ? 'var(--success-dim)' : 'var(--bg-card)',
                  border: '1px solid var(--border)',
                }}
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Code Editor / Viewer */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {isEditing ? (
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="mono"
            style={{
              width: '100%',
              height: '100%',
              padding: '16px',
              background: '#0d1117',
              color: '#c9d1d9',
              fontSize: 13,
              lineHeight: 1.7,
              border: 'none',
              outline: 'none',
              resize: 'none',
            }}
          />
        ) : (
          <div style={{ height: '100%', overflow: 'auto' }}>
            <Highlight code={code.trimEnd()} language={language} theme={themes.vsDark}>
              {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={`${className} mono`}
            style={{
              ...style,
              background: 'transparent',
              margin: 0,
              padding: '16px 0',
              fontSize: 13,
              lineHeight: 1.7,
              overflowX: 'auto',
            }}
          >
            {tokens.map((line, i) => (
              <div
                key={i}
                {...getLineProps({ line })}
                style={{ display: 'flex', paddingLeft: 0 }}
              >
                <span
                  className="select-none text-right"
                  style={{
                    minWidth: 44, paddingRight: 20,
                    paddingLeft: 20,
                    color: 'var(--text-4)',
                    fontSize: 12, lineHeight: '23.1px',
                    borderRight: '1px solid var(--border)',
                    marginRight: 20,
                    userSelect: 'none',
                  }}
                >
                  {i + 1}
                </span>
                <span>
                  {line.map((token, key) => (
                    <span key={key} {...getTokenProps({ token })} />
                  ))}
                </span>
              </div>
            ))}
          </pre>
        )}
      </Highlight>
          </div>
        )}
      </div>
    </div>
  )
}
