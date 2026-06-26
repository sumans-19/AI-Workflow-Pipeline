import { useState } from 'react'
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-react'
import type { FileNode } from '../../types'
import FileIcon from './FileIcon'
import { motion, AnimatePresence } from 'framer-motion'
import { useSessionStore } from '../../store/sessionStore'

interface Props {
  node: FileNode
  depth?: number
  selectedFile: string | null
  onSelect: (path: string) => void
}

export default function FileTreeNode({ node, depth = 0, selectedFile, onSelect }: Props) {
  const [expanded, setExpanded] = useState(depth < 2)
  const isSelected = selectedFile === node.path
  const indent = depth * 16
  const recentlyAdded = useSessionStore(s => s.recentlyAdded)
  const isNew = !node.isDirectory && recentlyAdded.has(node.path)

  if (node.isDirectory) {
    return (
      <div>
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full flex items-center gap-2 rounded-md text-left group"
          style={{
            paddingLeft: 12 + indent,
            paddingRight: 8,
            height: 28,
            color: 'var(--text-2)',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            transition: 'all 150ms',
            fontSize: 13,
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          <span style={{ color: 'var(--text-3)', width: 14, flexShrink: 0 }}>
            {expanded
              ? <ChevronDown size={13} strokeWidth={2} />
              : <ChevronRight size={13} strokeWidth={2} />}
          </span>
          {expanded
            ? <FolderOpen size={14} strokeWidth={1.75} style={{ color: 'var(--warning)', flexShrink: 0 }} />
            : <Folder size={14} strokeWidth={1.75} style={{ color: 'var(--warning)', flexShrink: 0 }} />}
          <span style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{node.name}</span>
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ overflow: 'hidden' }}
            >
              {node.children.map(child => (
                <FileTreeNode
                  key={child.path}
                  node={child}
                  depth={depth + 1}
                  selectedFile={selectedFile}
                  onSelect={onSelect}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    )
  }

  return (
    <motion.button
      initial={isNew ? { opacity: 0, x: -8, backgroundColor: 'rgba(99,102,241,0.15)' } : false}
      animate={{ opacity: 1, x: 0, backgroundColor: isSelected ? 'var(--bg-active)' : 'transparent' }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      onClick={() => onSelect(node.path)}
      className="w-full flex items-center gap-2 rounded-md text-left"
      style={{
        paddingLeft: 12 + indent,
        paddingRight: 8,
        height: 28,
        border: `1px solid ${isSelected ? 'rgba(99,102,241,0.2)' : 'transparent'}`,
        color: isSelected ? 'var(--primary)' : 'var(--text-2)',
        cursor: 'pointer',
        fontSize: 13,
      }}
      onMouseEnter={e => {
        if (!isSelected) (e.currentTarget.style.background = 'var(--bg-hover)')
      }}
      onMouseLeave={e => {
        if (!isSelected) (e.currentTarget.style.background = 'transparent')
      }}
    >
      <FileIcon filename={node.name} size={14} />
      <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {node.name}
      </span>
      {/* New file indicator dot */}
      {isNew && (
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="ml-auto flex-shrink-0"
          style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--success)',
          }}
        />
      )}
    </motion.button>
  )
}
