import { useState } from 'react'
import { Copy, Check, Code2 } from 'lucide-react'
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

function CodeBlock({ code, language, filename }: { code: string; language: string; filename: string }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      {/* Sticky header */}
      <div
        className="sticky top-0 z-10 flex items-center justify-between"
        style={{
          padding: '0 20px',
          height: 36,
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <span className="mono" style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {filename}
        </span>
        <div className="flex items-center gap-3">
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            {code.split('\n').length} lines
          </span>
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
        </div>
      </div>

      {/* Highlighted code */}
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
  )
}
