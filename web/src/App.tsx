import { useState, useRef, useCallback } from 'react'
import { PanelRightOpen, PanelLeftOpen } from 'lucide-react'
import { useWebSocket } from './hooks/useWebSocket'
import { useSessionStore } from './store/sessionStore'
import { useSession } from './hooks/useSession'

import TopNav      from './components/layout/TopNav'
import FileTree    from './components/explorer/FileTree'
import ChatWindow  from './components/chat/ChatWindow'
import PromptInput from './components/chat/PromptInput'
import CodePreview from './components/code/CodePreview'
import ReviewPanel from './components/review/ReviewPanel'
import PlanningConfiguration from './components/planning/PlanningConfiguration'
import PlanningReview from './components/planning/PlanningReview'

type CenterTab = 'chat' | 'code' | 'preview'

const MIN_EXPLORER = 200
const MAX_EXPLORER = 420
const MIN_REVIEW   = 260
const MAX_REVIEW   = 520

export default function App() {
  useWebSocket()

  const [centerTab,      setCenterTab]      = useState<CenterTab>('chat')
  const [explorerWidth,  setExplorerWidth]  = useState(280)
  const [reviewWidth,    setReviewWidth]    = useState(380)
  const explorerOpen   = useSessionStore(s => s.explorerOpen)
  const reviewOpen     = useSessionStore(s => s.reviewOpen)
  const toggleReview   = useSessionStore(s => s.toggleReview)
  const toggleExplorer = useSessionStore(s => s.toggleExplorer)
  const status         = useSessionStore(s => s.status)
  const planningMode   = useSessionStore(s => s.planningMode)
  const planningDoc    = useSessionStore(s => s.planningDocument)

  // We bring in createSession so we can start the pipeline from the PlanningConfiguration screen
  const { createSession } = useSession()

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
              onDoubleClick={toggleExplorer}
              title="Drag to resize · Double-click to toggle"
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
            {/* Planning configuration overlay — shown while user is choosing modules */}
            {planningMode === 'config' && status === 'pending' && (
              <div style={{
                flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column',
                background: 'var(--bg-base)',
              }}>
                <PlanningConfiguration onSubmit={(composedPrompt: string, projectTitle?: string) => {
                  createSession(composedPrompt, projectTitle)
                }} />
              </div>
            )}

            {/* Planning review overlay — shown when the planner produces a plan */}
            {planningMode === 'review' && planningDoc && (
              <div style={{
                flex: 1, overflow: 'auto', display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                padding: '24px 16px',
              }}>
                <PlanningReview
                  plan={planningDoc}
                  planMarkdown={(useSessionStore.getState().activeCheckpoint?.data as any)?.plan_markdown ?? ''}
                />
              </div>
            )}

            {planningMode !== 'config' && planningMode !== 'review' && (
              centerTab === 'chat' ? (
                <>
                  <ChatWindow />
                  <PromptInput />
                </>
              ) : centerTab === 'code' ? (
                <CodePreview />
              ) : (
                <PreviewPlaceholder />
              )
            )}
          </div>
        </main>

        {/* Resize handle */}
        <div
          className="resize-handle"
          onMouseDown={onMouseDown('review')}
          onDoubleClick={toggleReview}
          title="Drag to resize · Double-click to hide"
          style={{ cursor: 'col-resize' }}
        />

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

      {/* Floating toggle buttons — appear when their panel is hidden */}
      {!explorerOpen && (
        <button
          onClick={toggleExplorer}
          title="Show explorer"
          aria-label="Show explorer"
          style={{
            position: 'fixed', left: 8, top: '50%',
            transform: 'translateY(-50%)',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '6px 8px',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center',
            color: 'var(--text-2)',
            zIndex: 20,
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        >
          <PanelLeftOpen size={14} />
        </button>
      )}
      {!reviewOpen && (
        <button
          onClick={toggleReview}
          title="Show review panel"
          aria-label="Show review panel"
          style={{
            position: 'fixed', right: 8, top: '50%',
            transform: 'translateY(-50%)',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '6px 8px',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center',
            color: 'var(--text-2)',
            zIndex: 20,
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        >
          <PanelRightOpen size={14} />
        </button>
      )}

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
