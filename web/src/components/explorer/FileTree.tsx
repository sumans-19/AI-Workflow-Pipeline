import { useState } from 'react'
import { Search, FolderOpen, Plus, RefreshCw } from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import FileTreeNode from './FileTreeNode'
import ActionTimeline from '../timeline/ActionTimeline'
import type { FileNode } from '../../types'

export default function SidebarPanel() {
  const files        = useSessionStore(s => s.files)
  const selectedFile = useSessionStore(s => s.selectedFile)
  const selectFile   = useSessionStore(s => s.selectFile)
  const [search, setSearch] = useState('')

  const filterTree = (nodes: FileNode[], q: string): FileNode[] => {
    if (!q) return nodes
    return nodes.flatMap(node => {
      if (node.isDirectory) {
        const filtered = filterTree(node.children, q)
        return filtered.length ? [{ ...node, children: filtered }] : []
      }
      return node.name.toLowerCase().includes(q.toLowerCase()) ? [node] : []
    })
  }

  const visible = filterTree(files, search)
  const fileCount = countFiles(files)

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: 'var(--bg-panel)', overflow: 'hidden' }}
    >
      {/* ── EXPLORER section ── */}
      <div
        className="flex items-center gap-2"
        style={{
          padding: '12px 16px 8px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <FolderOpen size={14} strokeWidth={2} style={{ color: 'var(--primary)' }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Explorer
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 11, fontWeight: 500,
            padding: '2px 6px', borderRadius: 4,
            background: 'var(--primary-dim)', color: 'var(--primary)',
          }}
        >
          {fileCount} files
        </span>
        <button
          data-tooltip="Refresh"
          style={{ color: 'var(--text-3)', marginLeft: 4, transition: 'color 150ms' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
        >
          <RefreshCw size={13} strokeWidth={2} />
        </button>
        <button
          data-tooltip="New file"
          style={{ color: 'var(--text-3)', transition: 'color 150ms' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
        >
          <Plus size={14} strokeWidth={2} />
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: '8px 12px', flexShrink: 0 }}>
        <div
          className="flex items-center gap-2"
          style={{
            height: 38, padding: '0 10px',
            background: 'var(--bg-input)',
            border: '1px solid var(--border)',
            borderRadius: 8,
          }}
        >
          <Search size={13} strokeWidth={2} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
          <input
            type="text"
            placeholder="Search files…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: 13,
              color: 'var(--text-1)',
              width: '100%',
            }}
          />
        </div>
      </div>

      {/* Tree */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: '4px 6px', minHeight: 0 }}
      >
        {visible.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center h-full"
            style={{ padding: 24, color: 'var(--text-3)', textAlign: 'center' }}
          >
            <FolderOpen size={28} strokeWidth={1.5} style={{ marginBottom: 8, opacity: 0.4 }} />
            <p style={{ fontSize: 12 }}>
              {files.length === 0 ? 'No files generated yet' : 'No results'}
            </p>
          </div>
        ) : (
          visible.map(node => (
            <FileTreeNode
              key={node.path}
              node={node}
              selectedFile={selectedFile}
              onSelect={selectFile}
            />
          ))
        )}
      </div>

      {/* ── PIPELINE section ── */}
      <div
        style={{
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <ActionTimeline />
      </div>
    </div>
  )
}

function countFiles(nodes: FileNode[]): number {
  return nodes.reduce((acc, n) => acc + (n.isDirectory ? countFiles(n.children) : 1), 0)
}
