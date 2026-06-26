import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldCheck, CheckCircle2, XCircle, Edit3, RotateCcw,
  Eye, Activity, Clock, FileText, ChevronDown, ChevronRight
} from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import { useSession } from '../../hooks/useSession'
import FileIcon from '../explorer/FileIcon'

export default function ReviewPanel() {
  const checkpoint   = useSessionStore(s => s.activeCheckpoint)
  const testResults  = useSessionStore(s => s.testResults)
  const metrics      = useSessionStore(s => s.metrics)
  const reviewIssues = useSessionStore(s => s.reviewIssues)
  const status       = useSessionStore(s => s.status)
  const fileContents = useSessionStore(s => s.fileContents)
  const selectFile   = useSessionStore(s => s.selectFile)

  const { sendAction }             = useSession()
  const [feedback, setFeedback]    = useState('')
  const [editMode, setEditMode]    = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const handleAction = useCallback(async (action: string) => {
    if (actionLoading) return
    setActionLoading(true)
    try {
      const fb = (action === 'reject' || action === 'edit') ? feedback : ''
      // Send via REST endpoint (the backend will resolve the checkpoint)
      await sendAction(action, fb)
      setFeedback('')
      setEditMode(false)
    } finally {
      // Reset loading after a short delay to prevent rapid re-clicks
      setTimeout(() => setActionLoading(false), 1000)
    }
  }, [actionLoading, feedback, sendAction])

  const fileList = Object.keys(fileContents)

  return (
    <div
      className="flex flex-col h-full overflow-y-auto"
      style={{ background: 'var(--bg-panel)' }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 flex-shrink-0"
        style={{
          padding: '14px 16px 10px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <ShieldCheck size={14} strokeWidth={2} style={{ color: 'var(--primary)' }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Review
        </span>
        {status === 'checkpoint' && (
          <span
            className="ml-auto"
            style={{
              fontSize: 11, fontWeight: 600,
              padding: '2px 8px', borderRadius: 99,
              background: 'var(--warning-dim)', color: 'var(--warning)',
            }}
          >
            Action needed
          </span>
        )}
      </div>

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'y-auto' }}>

        {/* ── Summary & Actions Card ── */}
        {status === 'complete' || status === 'error' || status === 'checkpoint' ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="card"
            style={{
              padding: 16,
              borderColor: status === 'error' ? 'rgba(239,68,68,0.35)' : status === 'checkpoint' ? 'rgba(234,179,8,0.35)' : 'rgba(34,197,94,0.35)',
              boxShadow: status === 'error' ? '0 0 24px rgba(239,68,68,0.12)' : status === 'checkpoint' ? '0 0 24px rgba(234,179,8,0.12)' : '0 0 24px rgba(34,197,94,0.12)',
            }}
          >
            <div className="flex items-center gap-2 mb-3">
              <span
                style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  padding: '3px 8px', borderRadius: 4,
                  background: status === 'error' ? 'var(--error-dim)' : status === 'checkpoint' ? 'var(--warning-dim)' : 'var(--success-dim)',
                  color: status === 'error' ? 'var(--error)' : status === 'checkpoint' ? 'var(--warning)' : 'var(--success)',
                }}
              >
                {status === 'complete' ? 'PIPELINE COMPLETE' : status === 'checkpoint' ? 'ACTION NEEDED' : 'PIPELINE FAILED'}
              </span>
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 12, lineHeight: 1.6 }}>
              {status === 'complete' 
                ? 'The AI has finished generating, testing, and reviewing your project. Please review the results below.'
                : status === 'checkpoint'
                  ? (checkpoint?.message || 'Please review the current progress before continuing.')
                  : 'The pipeline encountered a critical error or reached maximum retries.'}
            </p>

            {/* Test Failure Output rendering */}
            {status === 'checkpoint' && checkpoint?.checkpoint_type === 'test_review' && (
              <div style={{ marginBottom: 16 }}>
                {checkpoint.data?.rca_data?.rca && checkpoint.data.rca_data.rca.length > 0 && (
                  <>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Activity size={14} style={{ color: 'var(--error)' }} /> Root Cause Analysis
                    </div>
                    {checkpoint.data.rca_data.rca.map((r: any, idx: number) => (
                       <div key={idx} style={{ padding: 10, background: 'var(--bg-input)', borderRadius: 6, marginBottom: 8, border: '1px solid var(--border)' }}>
                         <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--error)' }}>{r.category}</div>
                         <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Impacted: {r.impacted_tests}</div>
                         <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{r.diagnosis}</div>
                       </div>
                    ))}
                  </>
                )}
                {checkpoint.data?.rca_data?.recommended_action && (
                  <div style={{ fontSize: 12, padding: 10, background: 'var(--primary-dim)', color: 'var(--primary)', borderRadius: 6, marginBottom: 12, border: '1px solid rgba(99,102,241,0.2)' }}>
                    <span style={{ fontWeight: 600 }}>Suggested Fix: </span>{checkpoint.data.rca_data.recommended_action}
                  </div>
                )}

                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8, marginTop: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <FileText size={14} style={{ color: 'var(--text-3)' }} /> Raw Terminal Output
                </div>
                <div style={{ 
                  background: '#0d1117', color: '#c9d1d9', padding: 12, borderRadius: 6, 
                  fontFamily: 'monospace', fontSize: 11, maxHeight: 350, overflowY: 'auto',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', border: '1px solid var(--border)',
                  boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.2)'
                }}>
                  {checkpoint.data?.output || 'No output available'}
                </div>
              </div>
            )}

            {/* Feedback textarea */}
            <AnimatePresence>
              {editMode && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  style={{ overflow: 'hidden', marginBottom: 12 }}
                >
                  <textarea
                    value={feedback}
                    onChange={e => setFeedback(e.target.value)}
                    placeholder="Describe changes or issues for the AI to fix in a new run…"
                    rows={3}
                    style={{
                      width: '100%',
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      padding: '10px 12px',
                      fontSize: 13,
                      color: 'var(--text-1)',
                      resize: 'vertical',
                      outline: 'none',
                      fontFamily: 'inherit',
                    }}
                    onFocus={e => (e.currentTarget.style.borderColor = 'var(--primary)')}
                    onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                  />
                </motion.div>
              )}
            </AnimatePresence>

            {/* Action buttons */}
            {(status === 'complete' || status === 'checkpoint') && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <ActionBtn
                  icon={CheckCircle2} label="Approve" color="success"
                  onClick={() => handleAction('approve')}
                  fullWidth
                />
                <ActionBtn
                  icon={XCircle} label="Reject" color="error"
                  onClick={() => { setEditMode(true); if (feedback) handleAction('reject') }}
                  fullWidth
                />
                <ActionBtn
                  icon={Edit3} label="Edit" color="primary"
                  onClick={() => setEditMode(e => !e)}
                  fullWidth
                />
                <ActionBtn
                  icon={RotateCcw} label="Regenerate" color="muted"
                  onClick={() => handleAction('reject')}
                  fullWidth
                />
              </div>
            )}
          </motion.div>
        ) : (
          <div
            className="card flex flex-col items-center justify-center text-center"
            style={{ padding: 20, gap: 8 }}
          >
            <div
              style={{
                width: 40, height: 40, borderRadius: 10,
                background: 'var(--bg-base)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {status === 'running'
                ? <ShieldCheck size={20} style={{ color: 'var(--primary)' }} className="pulse-ring" />
                : <ShieldCheck size={20} style={{ color: 'var(--text-3)' }} />}
            </div>
            <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-2)' }}>
              {status === 'running'  ? 'Pipeline running…' : 'Awaiting pipeline start'}
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-3)' }}>
              {status === 'running' ? 'Summary will appear once validation finishes' : 'Enter a prompt to get started'}
            </p>
          </div>
        )}

        {/* ── Generated Files ── */}
        {fileList.length > 0 && (
          <Section title="Generated Files" icon={FileText} count={fileList.length}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {fileList.map(f => {
                const name = f.split('/').pop() || f
                const lines = fileContents[f]?.split('\n').length || 0
                return (
                  <button
                    key={f}
                    onClick={() => selectFile(f)}
                    className="flex items-center gap-2 rounded-md w-full text-left"
                    style={{
                      padding: '8px 10px',
                      background: 'var(--bg-base)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      cursor: 'pointer',
                      transition: 'all 150ms',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--primary)')}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                  >
                    <FileIcon filename={name} size={14} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {name}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{lines} lines</div>
                    </div>
                    <Eye size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                  </button>
                )
              })}
            </div>
          </Section>
        )}

        {/* ── Test Results ── */}
        {testResults && (
          <Section
            title="Test Results"
            icon={Activity}
            badge={testResults.passed ? 'Passed' : 'Failed'}
            badgeColor={testResults.passed ? 'success' : 'error'}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <MetricRow label="Status" value={testResults.passed ? 'All Passed' : 'Failed'} color={testResults.passed ? 'success' : 'error'} />
              <MetricRow label="Coverage" value={`${testResults.coverage_line.toFixed(1)}%`} />
              <MetricRow label="Duration" value={`${testResults.duration.toFixed(2)}s`} />
            </div>
          </Section>
        )}

        {/* ── Metrics ── */}
        {metrics && (
          <Section title="Metrics" icon={Clock}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <MetricRow label="Total Time"   value={`${metrics.total_time}s`} />
              <MetricRow label="Attempts"     value={String(metrics.attempts)} />
              <MetricRow label="Files"        value={String(metrics.files_count)} />
              <MetricRow label="Coverage"     value={`${Number(metrics.coverage).toFixed(1)}%`} />
              {metrics.pylint_score !== undefined && (
                <MetricRow label="Pylint Score" value={`${Number(metrics.pylint_score).toFixed(1)}/10`} />
              )}
            </div>
          </Section>
        )}

        {/* ── Review Issues ── */}
        {reviewIssues.length > 0 && (
          <Section title={`Issues (${reviewIssues.length})`} icon={ShieldCheck}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {reviewIssues.slice(0, 6).map((issue, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6,
                    borderLeft: '2px solid var(--border)',
                    paddingLeft: 10,
                  }}
                >
                  {typeof issue === 'string' ? issue : JSON.stringify(issue)}
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────

function Section({
  title, icon: Icon, count, badge, badgeColor, children
}: {
  title: string; icon: React.ElementType
  count?: number; badge?: string; badgeColor?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
        style={{
          padding: '12px 14px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          borderBottom: open ? '1px solid var(--border)' : 'none',
        }}
      >
        <Icon size={14} strokeWidth={2} style={{ color: 'var(--primary)', flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', flex: 1 }}>{title}</span>
        {count !== undefined && (
          <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: 'var(--primary-dim)', color: 'var(--primary)' }}>
            {count}
          </span>
        )}
        {badge && (
          <span style={{
            fontSize: 11, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
            background: badgeColor === 'success' ? 'var(--success-dim)' : 'var(--error-dim)',
            color: badgeColor === 'success' ? 'var(--success)' : 'var(--error)',
          }}>
            {badge}
          </span>
        )}
        {open ? <ChevronDown size={13} style={{ color: 'var(--text-3)' }} /> : <ChevronRight size={13} style={{ color: 'var(--text-3)' }} />}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: 14 }}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{label}</span>
      <span style={{
        fontSize: 12, fontWeight: 600,
        color: color === 'success' ? 'var(--success)' : color === 'error' ? 'var(--error)' : 'var(--text-1)',
      }}>
        {value}
      </span>
    </div>
  )
}

function ActionBtn({
  icon: Icon, label, color, onClick, fullWidth
}: {
  icon: React.ElementType; label: string; color: string
  onClick: () => void; fullWidth?: boolean
}) {
  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    success: { bg: 'var(--success-dim)', text: 'var(--success)', border: 'rgba(34,197,94,0.3)' },
    error:   { bg: 'var(--error-dim)',   text: 'var(--error)',   border: 'rgba(239,68,68,0.3)' },
    primary: { bg: 'var(--primary-dim)', text: 'var(--primary)', border: 'rgba(99,102,241,0.3)' },
    muted:   { bg: 'var(--bg-base)',     text: 'var(--text-2)',  border: 'var(--border)' },
  }
  const c = colorMap[color] ?? colorMap.muted
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 rounded-lg transition-all duration-150"
      style={{
        padding: '8px 12px',
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.text,
        fontSize: 13, fontWeight: 500,
        cursor: 'pointer',
        width: fullWidth ? '100%' : 'auto',
      }}
      onMouseEnter={e => (e.currentTarget.style.opacity = '0.8')}
      onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
    >
      <Icon size={13} strokeWidth={2} />
      {label}
    </button>
  )
}
