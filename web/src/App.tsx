import { useState, useRef, useCallback } from 'react'
import { useWebSocket } from './hooks/useWebSocket'

import TopNav      from './components/layout/TopNav'
import FileTree    from './components/explorer/FileTree'
import ChatWindow  from './components/chat/ChatWindow'
import PromptInput from './components/chat/PromptInput'
import CodePreview from './components/code/CodePreview'
import ReviewPanel from './components/review/ReviewPanel'

type CenterTab = 'chat' | 'code' | 'preview'

const MIN_EXPLORER = 200
const MAX_EXPLORER = 420
const MIN_REVIEW   = 260
const MAX_REVIEW   = 480

export default function App() {
  useWebSocket()

  const [centerTab,      setCenterTab]      = useState<CenterTab>('chat')
  const [activeSection,  setActiveSection]  = useState('explorer')
  const [explorerWidth,  setExplorerWidth]  = useState(280)
  const [reviewWidth,    setReviewWidth]    = useState(340)
  const [explorerOpen,   setExplorerOpen]   = useState(true)
  const [reviewOpen]    = useState(true)

  // Drag state
  const dragging    = useRef<'explorer' | 'review' | null>(null)
  const startX      = useRef(0)
  const startWidth  = useRef(0)

  const onMouseDown = useCallback((side: 'explorer' | 'review') => (e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = side
    startX.current   = e.clientX
    startWidth.current = side === 'explorer' ? explorerWidth : reviewWidth

    const onMove = (me: MouseEvent) => {
      const delta = me.clientX - startX.current
      if (dragging.current === 'explorer') {
        setExplorerWidth(() => Math.min(MAX_EXPLORER, Math.max(MIN_EXPLORER, startWidth.current + delta)))
      } else {
        setReviewWidth(() => Math.min(MAX_REVIEW, Math.max(MIN_REVIEW, startWidth.current - delta)))
      }
    }
    const onUp = () => {
      dragging.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [explorerWidth, reviewWidth])

  const handleSectionSelect = (section: string) => {
    if (section === activeSection && explorerOpen) {
      setExplorerOpen(false)
    } else {
      setActiveSection(section)
      setExplorerOpen(true)
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: 'var(--bg-base)',
        overflow: 'hidden',
        userSelect: dragging.current ? 'none' : 'auto',
      }}
    >
      {/* Top Navigation */}
      <TopNav centerTab={centerTab} onTabChange={setCenterTab} />

      {/* Main content */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>


        {/* Explorer sidebar */}
        {explorerOpen && (
          <>
            <div
              style={{
                width: explorerWidth,
                flexShrink: 0,
                borderRight: '1px solid var(--border)',
                overflow: 'hidden',
              }}
            >
              <FileTree />
            </div>

            {/* Resize handle */}
            <div
              className="resize-handle"
              onMouseDown={onMouseDown('explorer')}
              style={{ cursor: 'col-resize' }}
            />
          </>
        )}

        {/* Center workspace */}
        <main
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minWidth: 0,
            background: 'var(--bg-base)',
          }}
        >
          {/* Content area */}
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {centerTab === 'chat' ? (
              <>
                <ChatWindow />
                <PromptInput />
              </>
            ) : centerTab === 'code' ? (
              <CodePreview />
            ) : (
              <PreviewPlaceholder />
            )}
          </div>
        </main>

        {/* Resize handle */}
        {reviewOpen && (
          <div
            className="resize-handle"
            onMouseDown={onMouseDown('review')}
            style={{ cursor: 'col-resize' }}
          />
        )}

        {/* Review sidebar */}
        {reviewOpen && (
          <div
            style={{
              width: reviewWidth,
              flexShrink: 0,
              borderLeft: '1px solid var(--border)',
              overflow: 'hidden',
            }}
          >
            <ReviewPanel />
          </div>
        )}
      </div>

    </div>
  )
}

function PreviewPlaceholder() {
  return (
    <div
      style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        color: 'var(--text-3)',
      }}
    >
      <div style={{ fontSize: 14 }}>Preview not available yet</div>
      <div style={{ fontSize: 12, marginTop: 4 }}>Switch to Code tab to view generated files</div>
    </div>
  )
}
