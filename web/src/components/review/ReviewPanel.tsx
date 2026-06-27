import { useState, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldCheck, CheckCircle2, XCircle, Edit3, RotateCcw,
  Eye, Activity, Clock, FileText, ChevronDown, ChevronRight,
  SkipForward, MonitorPlay, Wand2, Ban, PanelRightClose, PanelRightOpen,
  Copy, Check, AlertTriangle, Sparkles,
} from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import { useSession } from '../../hooks/useSession'
import FileIcon from '../explorer/FileIcon'

// ─────────────────────────────────────────────────────────────
// Threshold for switching test-review button sets.
// ─────────────────────────────────────────────────────────────
const PASS_RATE_THRESHOLD = 0.70

// ─────────────────────────────────────────────────────────────
// Issue parsing — turn raw strings/JSON into structured cards.
// ─────────────────────────────────────────────────────────────
type ParsedIssue = {
  severity?: string
  category?: string
  location?: string
  file?: string
  line?: number | string
  title?: string
  description?: string
  raw: string
}

function stripMarkdownFences(text: string): string {
  const fencePattern = /```(?:json|JSON|python|PYTHON)?\s*\n?([\s\S]*?)\n?```/
  const match = text.match(fencePattern)
  return match ? match[1].trim() : text.trim()
}

function parseIssue(raw: unknown): ParsedIssue | ParsedIssue[] {
  if (typeof raw !== 'string') return { raw: String(raw ?? '') }
  // Strip markdown fences first
  const cleaned = stripMarkdownFences(raw)
  // Try JSON parse
  let obj: any = null
  try {
    obj = JSON.parse(cleaned)
  } catch {
    // Try to extract a JSON object/array from the text
    const objMatch = cleaned.match(/\{[\s\S]*\}/)
    const arrMatch = cleaned.match(/\[[\s\S]*\]/)
    const candidate = objMatch?.[0] || arrMatch?.[0]
    if (candidate) {
      try { obj = JSON.parse(candidate) } catch { /* not JSON */ }
    }
  }
  if (obj && typeof obj === 'object') {
    // Unwrap {"issues": [...]} into multiple ParsedIssues
    if (Array.isArray(obj.issues)) {
      return obj.issues
        .filter((i: any) => i && typeof i === 'object')
        .map((i: any) => ({
          severity: i.severity || i.priority,
          category: i.category || i.type,
          location: i.location || i.symbol,
          file: i.file || i.filename || i.path,
          line: i.line || i.lineno,
          title: i.title || i.problem || i.name,
          description: i.description || i.message || i.detail || i.problem,
          raw,
        }))
    }
    // If the object itself looks like an issue (has severity/problem/location)
    if (obj.severity || obj.problem || obj.title) {
      return {
        severity: obj.severity || obj.priority,
        category: obj.category || obj.type,
        location: obj.location || obj.symbol,
        file: obj.file || obj.filename || obj.path,
        line: obj.line || obj.lineno,
        title: obj.title || obj.problem || obj.name,
        description: obj.description || obj.message || obj.detail || obj.problem,
        raw,
      }
    }
    // If it's an array at the root, map each element
    if (Array.isArray(obj)) {
      return obj
        .filter((i: any) => i && typeof i === 'object')
        .map((i: any) => ({
          severity: i.severity || i.priority,
          category: i.category || i.type,
          location: i.location || i.symbol,
          file: i.file || i.filename || i.path,
          line: i.line || i.lineno,
          title: i.title || i.problem || i.name,
          description: i.description || i.message || i.detail || i.problem,
          raw,
        }))
    }
  }
  // Plain text — wrap as description
  return { description: cleaned || raw, raw }
}

function severityStyle(sev?: string): { bg: string; fg: string; label: string } {
  switch ((sev || '').toLowerCase()) {
    case 'critical': return { bg: 'rgba(239,68,68,0.16)', fg: 'var(--error)',   label: 'CRITICAL' }
    case 'high':
    case 'major':   return { bg: 'rgba(249,115,22,0.16)', fg: '#f97316',      label: 'HIGH' }
    case 'medium':
    case 'minor':   return { bg: 'rgba(234,179,8,0.16)',  fg: 'var(--warning)',label: 'MEDIUM' }
    case 'low':
    case 'suggestion':
    case 'info':    return { bg: 'rgba(99,102,241,0.16)', fg: 'var(--primary)',label: sev?.toUpperCase() || 'LOW' }
    default:        return { bg: 'var(--bg-input)',       fg: 'var(--text-3)', label: (sev || 'INFO').toUpperCase() }
  }
}

// ─────────────────────────────────────────────────────────────
// Design tokens (kept in one place for consistency)
// ─────────────────────────────────────────────────────────────
const CARD_PADDING = 16
const CARD_GAP     = 16
const CARD_RADIUS  = 12

const cardBase = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: CARD_RADIUS,
  padding: CARD_PADDING,
} as const

const sectionTitleStyle = {
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase' as const,
  color: 'var(--text-2)',
} as const

// ─────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────
export default function ReviewPanel() {
  const checkpoint   = useSessionStore(s => s.activeCheckpoint)
  const reviewOpen   = useSessionStore(s => s.reviewOpen)
  const toggleReview = useSessionStore(s => s.toggleReview)
  const testResults  = useSessionStore(s => s.testResults)
  const metrics      = useSessionStore(s => s.metrics)
  const reviewIssues = useSessionStore(s => s.reviewIssues)
  const status       = useSessionStore(s => s.status)
  const sessionId    = useSessionStore(s => s.sessionId)
  const fileContents = useSessionStore(s => s.fileContents)
  const selectFile   = useSessionStore(s => s.selectFile)

  const { sendAction }             = useSession()
  const [feedback, setFeedback]    = useState('')
  const [editMode, setEditMode]    = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [confirmBypass, setConfirmBypass] = useState(false)

  const checkpointType = (checkpoint?.checkpoint_type || '').toLowerCase()
  const isTestReview   = checkpointType === 'test_review'

  // ── Pass-rate info ──
  const passRateInfo = useMemo(() => {
    const reportData = testResults?.report_data || (checkpoint?.data?.report_data as Record<string, any>) || {}
    const summary    = (reportData as any)?.summary || {}
    const collected  = Number((summary as any).collected || 0)
    const passed     = Number((summary as any).passed || 0)
    const failed     = Number((summary as any).failed || 0)
    const total      = Number((summary as any).total || (collected || passed + failed))
    const rate       = total > 0 ? passed / total : 0
    return {
      collected, passed, failed, total, rate,
      passRatePct: (rate * 100).toFixed(1),
    }
  }, [testResults, checkpoint])

  const parsedIssues = useMemo<ParsedIssue[]>(() => {
    const out: ParsedIssue[] = []
    for (const raw of reviewIssues || []) {
      const parsed = parseIssue(raw)
      if (Array.isArray(parsed)) {
        out.push(...parsed)
      } else {
        out.push(parsed)
      }
    }
    return out.filter(i => i.description || i.title)
  }, [reviewIssues])

  const handleAction = useCallback(async (action: string) => {
    if (action === 'bypass' && !confirmBypass) {
      setConfirmBypass(true)
      return
    }
    if (actionLoading) return
    setActionLoading(true)
    try {
      const fb = (action === 'reject' || action === 'edit' || action === 'retry' || action === 'auto_fix') ? feedback : ''
      await sendAction(action, fb)
      setFeedback('')
      setEditMode(false)
      setConfirmBypass(false)
    } finally {
      setTimeout(() => setActionLoading(false), 1000)
    }
  }, [actionLoading, feedback, sendAction, confirmBypass])

  const fileList = Object.keys(fileContents)

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: 'var(--bg-panel)', overflow: 'hidden', minHeight: 0 }}
    >
      {/* ─────────────── Header ─────────────── */}
      <div
        className="flex items-center gap-2 flex-shrink-0"
        style={{
          padding: '16px 20px 14px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <ShieldCheck size={15} strokeWidth={2} style={{ color: 'var(--primary)' }} />
        <span style={{ ...sectionTitleStyle, color: 'var(--text-1)' }}>Review</span>

        {status === 'checkpoint' && (
          <span
            className="ml-auto"
            style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
              textTransform: 'uppercase',
              padding: '3px 8px', borderRadius: 99,
              background: 'var(--warning-dim)', color: 'var(--warning)',
            }}
          >
            Action needed
          </span>
        )}

        {toggleReview && (
          <button
            onClick={toggleReview}
            title={reviewOpen ? 'Hide review panel' : 'Show review panel'}
            aria-label="Toggle review panel"
            style={{
              marginLeft: status === 'checkpoint' ? 6 : 'auto',
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '5px 7px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              color: 'var(--text-2)',
              transition: 'all 150ms',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--primary)'
              e.currentTarget.style.color = 'var(--primary)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-2)'
            }}
          >
            {reviewOpen ? <PanelRightClose size={13} /> : <PanelRightOpen size={13} />}
          </button>
        )}
      </div>

      {/* ─────────────── Scrollable Content ─────────────── */}
      <div
        className="review-scroll"
        style={{
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: CARD_GAP,
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          minHeight: 0,
        }}
      >
        {/* ── Empty state when truly no session exists ── */}
        {!sessionId && (
          <EmptyState />
        )}

        {/* ── Running state (pipeline active but no checkpoint yet) ── */}
        {sessionId && status === 'running' && !checkpoint && !testResults && !metrics && (
          <RunningState />
        )}

        {/* ═══════════ 1. Action Required Card ═══════════ */}
        {(status === 'checkpoint' || status === 'complete' || status === 'error') && (
          <ActionRequiredCard
            status={status}
            message={
              status === 'complete'
                ? 'The AI has finished generating, testing, and reviewing your project. Review the final results below.'
                : status === 'checkpoint'
                  ? (checkpoint?.message || 'Please review the current progress before continuing.')
                  : 'The pipeline encountered a critical error or reached maximum retries.'
            }
          />
        )}

        {/* ═══════════ 2. Testing Summary (test_review only) ═══════════ */}
        {status === 'checkpoint' && isTestReview && (
          <TestingSummaryCard
            summary={(testResults?.report_data as any)?.summary || (checkpoint?.data?.report_data as any)?.summary || {}}
            passRate={passRateInfo.rate}
            passRatePct={passRateInfo.passRatePct}
            coverage={testResults?.coverage_line ?? 0}
            duration={testResults?.duration ?? 0}
            isMajority={!!(testResults?.majority_passed || testResults?.passed)}
          />
        )}

        {/* ═══════════ 3. Action Buttons (checkpoint only) ═══════════ */}
        {(status === 'checkpoint' || status === 'complete') && (
          <ActionButtonsCard
            status={status}
            isTestReview={isTestReview}
            confirmBypass={confirmBypass}
            passRate={passRateInfo.rate}
            editMode={editMode}
            feedback={feedback}
            onAction={handleAction}
            onToggleEdit={() => setEditMode(e => !e)}
            onCancelBypass={() => setConfirmBypass(false)}
          />
        )}

        {/* ── Edit feedback textarea (when toggled) ── */}
        <AnimatePresence>
          {editMode && (status === 'checkpoint' || status === 'complete') && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={cardBase}>
                <SectionTitle icon={Edit3} title="Feedback for the AI" />
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
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══════════ 4. Failed Tests (expandable) ═══════════ */}
        {status === 'checkpoint' && isTestReview && (() => {
          const failures = (testResults?.report_data as any)?.failures
            || (checkpoint?.data?.report_data as any)?.failures
            || []
          return failures.length > 0 ? <FailedTestsCard failures={failures} /> : null
        })()}

        {/* ═══════════ 6. Root Cause Analysis ═══════════ */}
        {(() => {
          const rcaList = (checkpoint?.data?.rca_data as any)?.rca
            || (testResults?.rca_data as any)?.rca
            || []
          return rcaList.length > 0 ? <RcaCard items={rcaList} /> : null
        })()}

        {/* ═══════════ 7. Issues (parsed) ═══════════ */}
        {parsedIssues.length > 0 && <IssuesCard issues={parsedIssues} />}

        {/* ═══════════ 8. Metrics ═══════════ */}
        {metrics && <MetricsCard metrics={metrics} testResults={testResults} />}

        {/* ═══════════ 9. Terminal Output (collapsible) ═══════════ */}
        {(() => {
          const termOut = testResults?.output
            || (checkpoint?.data?.output as string)
            || ''
          const execMode = testResults?.execution_mode
            || (checkpoint?.data?.execution_mode as string)
            || 'unknown'
          return termOut ? <TerminalOutputCard output={termOut} executionMode={execMode} /> : null
        })()}

        {/* ═══════════ 10. Generated Files ═══════════ */}
        {fileList.length > 0 && <GeneratedFilesCard files={fileList} contents={fileContents} onSelect={selectFile} />}

        {/* ═══════════ 11. Final Status ═══════════ */}
        {status === 'complete' && <FinalStatusCard />}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════

function Card({ children, accent }: { children: React.ReactNode; accent?: 'success' | 'warning' | 'error' }) {
  const accentColor = accent === 'success' ? 'rgba(34,197,94,0.25)'
    : accent === 'warning' ? 'rgba(234,179,8,0.25)'
    : accent === 'error' ? 'rgba(239,68,68,0.25)'
    : 'var(--border)'
  const shadow = accent === 'success' ? '0 0 0 1px rgba(34,197,94,0.08)'
    : accent === 'warning' ? '0 0 0 1px rgba(234,179,8,0.08)'
    : accent === 'error' ? '0 0 0 1px rgba(239,68,68,0.08)'
    : 'none'
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        ...cardBase,
        borderColor: accentColor,
        boxShadow: shadow,
      }}
    >
      {children}
    </motion.div>
  )
}

function SectionTitle({ icon: Icon, title, count, badge }: {
  icon: React.ElementType
  title: string
  count?: number
  badge?: { label: string; color: string; bg: string }
}) {
  return (
    <div
      className="flex items-center gap-2"
      style={{ marginBottom: 14, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}
    >
      <Icon size={14} strokeWidth={2} style={{ color: 'var(--primary)', flexShrink: 0 }} />
      <span style={{ ...sectionTitleStyle, flex: 1 }}>{title}</span>
      {count !== undefined && (
        <span style={{
          fontSize: 11, fontWeight: 600,
          padding: '2px 7px', borderRadius: 4,
          background: 'var(--primary-dim)', color: 'var(--primary)',
        }}>
          {count}
        </span>
      )}
      {badge && (
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
          textTransform: 'uppercase',
          padding: '2px 7px', borderRadius: 4,
          background: badge.bg, color: badge.color,
        }}>
          {badge.label}
        </span>
      )}
    </div>
  )
}

function Metric({ label, value, valueColor }: { label: string; value: string | number; valueColor?: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      padding: '10px 12px',
      background: 'var(--bg-input)',
      borderRadius: 8,
      border: '1px solid var(--border)',
    }}>
      <span style={{
        fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: 'var(--text-3)',
      }}>
        {label}
      </span>
      <span style={{
        fontSize: 15, fontWeight: 600,
        color: valueColor || 'var(--text-1)',
        fontVariantNumeric: 'tabular-nums',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {value}
      </span>
    </div>
  )
}

function EmptyState() {
  return (
    <Card>
      <div style={{
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', gap: 10, padding: '12px 8px',
      }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: 'var(--bg-base)',
          border: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <ShieldCheck size={22} style={{ color: 'var(--text-3)' }} />
        </div>
        <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-2)' }}>
          Awaiting pipeline start
        </p>
        <p style={{ fontSize: 12, color: 'var(--text-3)' }}>
          Enter a prompt to get started
        </p>
      </div>
    </Card>
  )
}

function RunningState() {
  return (
    <Card>
      <div style={{
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', gap: 10, padding: '12px 8px',
      }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: 'var(--bg-base)',
          border: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <ShieldCheck size={22} style={{ color: 'var(--primary)' }} className="pulse-ring" />
        </div>
        <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-2)' }}>
          Pipeline running…
        </p>
        <p style={{ fontSize: 12, color: 'var(--text-3)' }}>
          Summary will appear once validation finishes
        </p>
      </div>
    </Card>
  )
}

function ActionRequiredCard({ status, message }: { status: string; message: string }) {
  const accent = status === 'complete' ? 'success' : status === 'checkpoint' ? 'warning' : 'error'
  const badge = status === 'complete' ? 'PIPELINE COMPLETE'
    : status === 'checkpoint' ? 'ACTION NEEDED'
    : 'PIPELINE FAILED'
  return (
    <Card accent={accent as any}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 10px', borderRadius: 99,
        background: accent === 'success' ? 'var(--success-dim)' : accent === 'warning' ? 'var(--warning-dim)' : 'var(--error-dim)',
        color: accent === 'success' ? 'var(--success)' : accent === 'warning' ? 'var(--warning)' : 'var(--error)',
        fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase',
        marginBottom: 12,
      }}>
        {accent === 'success' && <CheckCircle2 size={12} />}
        {accent === 'warning' && <AlertTriangle size={12} />}
        {accent === 'error' && <XCircle size={12} />}
        {badge}
      </div>
      <p style={{
        fontSize: 13, color: 'var(--text-2)',
        lineHeight: 1.6, margin: 0,
      }}>
        {message}
      </p>
    </Card>
  )
}

function TestingSummaryCard({ summary, passRate, passRatePct, coverage, duration, isMajority }: {
  summary: any
  passRate: number
  passRatePct: string
  coverage: number
  duration: number
  isMajority: boolean
}) {
  return (
    <Card>
      <SectionTitle
        icon={isMajority ? CheckCircle2 : XCircle}
        title="Testing Summary"
        badge={{
          label: isMajority ? 'PASSED' : 'FAILED',
          color: isMajority ? 'var(--success)' : 'var(--error)',
          bg: isMajority ? 'var(--success-dim)' : 'var(--error-dim)',
        }}
      />
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 10,
      }}>
        <Metric label="Tests Collected" value={summary.collected || 0} />
        <Metric label="Passed" value={summary.passed || 0} valueColor="var(--success)" />
        <Metric label="Failed" value={summary.failed || 0} valueColor="var(--error)" />
        <Metric label="Skipped" value={summary.skipped || 0} />
        <Metric label="Coverage" value={`${coverage.toFixed(1)}%`} />
        <Metric label="Execution Time" value={`${duration.toFixed(2)}s`} />
      </div>
      <div style={{
        marginTop: 12,
        padding: '12px 14px',
        borderRadius: 8,
        background: passRate >= PASS_RATE_THRESHOLD ? 'var(--success-dim)' : 'var(--warning-dim)',
        border: `1px solid ${passRate >= PASS_RATE_THRESHOLD ? 'rgba(34,197,94,0.3)' : 'rgba(234,179,8,0.3)'}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{
          fontSize: 11, fontWeight: 600,
          color: passRate >= PASS_RATE_THRESHOLD ? 'var(--success)' : 'var(--warning)',
          textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          Success Rate
        </span>
        <span style={{
          fontSize: 18, fontWeight: 700,
          color: passRate >= PASS_RATE_THRESHOLD ? 'var(--success)' : 'var(--warning)',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {passRatePct}%
        </span>
      </div>
    </Card>
  )
}

function ActionButtonsCard({ isTestReview, confirmBypass, passRate, onAction, onToggleEdit, onCancelBypass }: {
  status: string
  isTestReview: boolean
  confirmBypass: boolean
  passRate: number
  editMode: boolean
  feedback: string
  onAction: (a: string) => void
  onToggleEdit: () => void
  onCancelBypass: () => void
}) {
  return (
    <Card>
      <SectionTitle icon={Sparkles} title="Actions" />
      {isTestReview && confirmBypass ? (
        <>
          <div style={{
            fontSize: 13,
            color: 'var(--warning)',
            background: 'var(--warning-dim)',
            padding: '12px 14px',
            borderRadius: 8,
            marginBottom: 12,
            border: '1px solid rgba(234,179,8,0.3)',
          }}>
            Continue to Code Review despite failed tests?
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <ActionButton icon={SkipForward} label="Proceed" subtitle="Continue" color="primary" onClick={() => onAction('bypass')} />
            <ActionButton icon={XCircle}    label="Cancel"  subtitle="Stay here"  color="muted"   onClick={onCancelBypass} />
          </div>
        </>
      ) : isTestReview ? (
        <>
          <div style={{
            fontSize: 12,
            padding: '8px 12px',
            borderRadius: 8,
            marginBottom: 12,
            background: passRate >= PASS_RATE_THRESHOLD ? 'var(--success-dim)' : 'var(--warning-dim)',
            color: passRate >= PASS_RATE_THRESHOLD ? 'var(--success)' : 'var(--warning)',
            border: `1px solid ${passRate >= PASS_RATE_THRESHOLD ? 'rgba(34,197,94,0.3)' : 'rgba(234,179,8,0.3)'}`,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {passRate >= PASS_RATE_THRESHOLD ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
            <span style={{ fontWeight: 600 }}>
              {passRate === 0
                ? 'No tests were collected.'
                : passRate >= PASS_RATE_THRESHOLD
                  ? `${(passRate * 100).toFixed(1)}% passed — testing mostly succeeded`
                  : `${(passRate * 100).toFixed(1)}% passed — significant failures`}
            </span>
          </div>
          {passRate >= PASS_RATE_THRESHOLD ? (
            // ≥ 70%: Approve / Auto-Fix / Bypass / Reject
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <ActionButton icon={CheckCircle2} label="Approve"  subtitle="→ Review"  color="success" onClick={() => onAction('approve')} />
              <ActionButton icon={Wand2}        label="Auto Fix" subtitle="→ Coding"  color="primary" onClick={() => onAction('auto_fix')} />
              <ActionButton icon={SkipForward}  label="Bypass"   subtitle="→ Review"  color="muted"   onClick={() => onAction('bypass')} />
              <ActionButton icon={XCircle}      label="Reject"   subtitle="Stop"      color="error"  onClick={() => onAction('reject')} />
            </div>
          ) : (
            // < 70%: Auto-Fix / Revoke / Edit / Reject
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <ActionButton icon={Wand2}  label="Auto Fix"   subtitle="→ Coding" color="primary" onClick={() => onAction('auto_fix')} />
              <ActionButton icon={Ban}    label="Revoke"     subtitle="Retry"   color="muted"   onClick={() => onAction('retry')} />
              <ActionButton icon={Edit3}  label="Edit Code"  subtitle="Manual"  color="primary" onClick={onToggleEdit} />
              <ActionButton icon={XCircle} label="Reject"    subtitle="Stop"    color="error"  onClick={() => onAction('reject')} />
            </div>
          )}
        </>
      ) : (
        // final_review or other checkpoints
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <ActionButton icon={CheckCircle2} label="Approve"    color="success" onClick={() => onAction('approve')} />
          <ActionButton icon={XCircle}      label="Reject"     color="error"   onClick={() => onAction('reject')} />
          <ActionButton icon={Edit3}        label="Edit"       color="primary" onClick={onToggleEdit} />
          <ActionButton icon={RotateCcw}    label="Regenerate" color="muted"   onClick={() => onAction('reject')} />
        </div>
      )}
    </Card>
  )
}

function ActionButton({ icon: Icon, label, subtitle, color, onClick }: {
  icon: React.ElementType
  label: string
  subtitle?: string
  color: 'success' | 'error' | 'primary' | 'muted'
  onClick: () => void
}) {
  const colorMap = {
    success: { bg: 'rgba(34,197,94,0.10)',  text: 'var(--success)', border: 'rgba(34,197,94,0.30)', hover: 'rgba(34,197,94,0.18)' },
    error:   { bg: 'rgba(239,68,68,0.10)',  text: 'var(--error)',   border: 'rgba(239,68,68,0.30)', hover: 'rgba(239,68,68,0.18)' },
    primary: { bg: 'rgba(99,102,241,0.10)', text: 'var(--primary)', border: 'rgba(99,102,241,0.30)',hover: 'rgba(99,102,241,0.18)' },
    muted:   { bg: 'var(--bg-input)',       text: 'var(--text-2)',  border: 'var(--border)',        hover: 'var(--bg-base)' },
  }
  const c = colorMap[color]
  return (
    <button
      onClick={onClick}
      className="transition-all duration-150"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        padding: '12px 14px',
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: 10,
        color: c.text,
        cursor: 'pointer',
        minHeight: 64,
        textAlign: 'center',
        fontFamily: 'inherit',
        width: '100%',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = c.hover }}
      onMouseLeave={e => { e.currentTarget.style.background = c.bg }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Icon size={14} strokeWidth={2} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
      </div>
      {subtitle && (
        <span style={{ fontSize: 10, opacity: 0.75, fontWeight: 500, letterSpacing: '0.02em' }}>
          {subtitle}
        </span>
      )}
    </button>
  )
}

function FailedTestsCard({ failures }: { failures: any[] }) {
  return (
    <Card accent="error">
      <SectionTitle
        icon={XCircle}
        title="Failed Tests"
        count={failures.length}
        badge={{
          label: `${failures.length} FAILED`,
          color: 'var(--error)',
          bg: 'var(--error-dim)',
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {failures.map((f: any, idx: number) => (
          <ExpandableFailure key={idx} failure={f} />
        ))}
      </div>
    </Card>
  )
}

function ExpandableFailure({ failure }: { failure: any }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center w-full text-left transition-colors duration-100"
        style={{
          padding: '10px 12px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          gap: 8,
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-input)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
      >
        {open
          ? <ChevronDown size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
          : <ChevronRight size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
        <XCircle size={12} style={{ color: 'var(--error)', flexShrink: 0 }} />
        <span style={{
          fontSize: 12, fontWeight: 500, color: 'var(--text-1)',
          flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {failure.test_name || failure.nodeid || 'Test'}
        </span>
        <span style={{
          fontSize: 10, fontWeight: 600,
          padding: '2px 6px', borderRadius: 4,
          background: 'var(--error-dim)', color: 'var(--error)',
          flexShrink: 0,
        }}>
          {failure.error_type || 'FAIL'}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden', borderTop: '1px solid var(--border)' }}
          >
            <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {failure.file && (
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  <span style={{ fontWeight: 600 }}>File:</span>{' '}
                  <span style={{ fontFamily: 'monospace', color: 'var(--text-2)' }}>
                    {failure.file}{failure.lineno ? `:${failure.lineno}` : ''}
                  </span>
                </div>
              )}
              {failure.exception && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase' }}>
                    Exception
                  </div>
                  <div style={{
                    fontSize: 11, fontFamily: 'monospace',
                    color: 'var(--error)',
                    background: 'var(--bg-input)',
                    padding: '8px 10px',
                    borderRadius: 6,
                    wordBreak: 'break-word',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {failure.exception}
                  </div>
                </div>
              )}
              {failure.assertion && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase' }}>
                    Assertion
                  </div>
                  <div style={{
                    fontSize: 11, fontFamily: 'monospace',
                    color: 'var(--text-2)',
                    background: 'var(--bg-input)',
                    padding: '8px 10px',
                    borderRadius: 6,
                  }}>
                    {failure.assertion}
                  </div>
                </div>
              )}
              {failure.expected_actual && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase' }}>
                    Expected vs Actual
                  </div>
                  <div style={{
                    fontSize: 11, fontFamily: 'monospace',
                    color: 'var(--text-2)',
                    background: 'var(--bg-input)',
                    padding: '8px 10px',
                    borderRadius: 6,
                    whiteSpace: 'pre-wrap',
                  }}>
                    {failure.expected_actual}
                  </div>
                </div>
              )}
              {failure.traceback && (
                <details>
                  <summary style={{
                    fontSize: 11, fontWeight: 600, color: 'var(--text-3)',
                    cursor: 'pointer', marginBottom: 6,
                  }}>
                    Show traceback
                  </summary>
                  <pre style={{
                    fontSize: 10, fontFamily: 'monospace',
                    color: 'var(--text-3)',
                    background: 'var(--bg-input)',
                    padding: '10px 12px',
                    borderRadius: 6,
                    overflow: 'auto',
                    maxHeight: 240,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    margin: 0,
                  }}>
                    {failure.traceback}
                  </pre>
                </details>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function RcaCard({ items }: { items: any[] }) {
  return (
    <Card accent="warning">
      <SectionTitle
        icon={Activity}
        title="Root Cause Analysis"
        count={items.length}
        badge={{
          label: 'AI ANALYSIS',
          color: 'var(--warning)',
          bg: 'var(--warning-dim)',
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((rca: any, idx: number) => (
          <ExpandableRca key={idx} rca={rca} />
        ))}
      </div>
    </Card>
  )
}

function ExpandableRca({ rca }: { rca: any }) {
  const [open, setOpen] = useState(true)
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center w-full text-left"
        style={{
          padding: '12px 14px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          gap: 10,
        }}
      >
        {open
          ? <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />
          : <ChevronRight size={14} style={{ color: 'var(--text-3)' }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>
            {rca.category || 'Root Cause'}
          </div>
          {rca.caused_by_file && (
            <div style={{
              fontSize: 11, fontFamily: 'monospace',
              color: 'var(--text-3)',
              marginTop: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {rca.caused_by_file}
            </div>
          )}
        </div>
        {rca.confidence_score !== undefined && (
          <span style={{
            fontSize: 10, fontWeight: 700,
            padding: '3px 7px', borderRadius: 4,
            background: 'var(--primary-dim)', color: 'var(--primary)',
            flexShrink: 0,
          }}>
            {rca.confidence_score}%
          </span>
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden', borderTop: '1px solid var(--border)' }}
          >
            <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {rca.caused_by_function && (
                <Field label="Impacted Function" value={rca.caused_by_function} mono />
              )}
              {rca.why_it_happened && (
                <Field label="Explanation" value={rca.why_it_happened} />
              )}
              {rca.suggested_fix && (
                <div>
                  <div style={{
                    fontSize: 10, fontWeight: 600, color: 'var(--primary)',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                    marginBottom: 6,
                  }}>
                    Suggested Fix
                  </div>
                  <div style={{
                    fontSize: 12, color: 'var(--text-1)',
                    background: 'rgba(99,102,241,0.08)',
                    border: '1px dashed rgba(99,102,241,0.3)',
                    padding: '10px 12px',
                    borderRadius: 6,
                    lineHeight: 1.5,
                  }}>
                    {rca.suggested_fix}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{
        fontSize: 10, fontWeight: 600, color: 'var(--text-3)',
        textTransform: 'uppercase', letterSpacing: '0.06em',
        marginBottom: 4,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 12, color: 'var(--text-1)',
        fontFamily: mono ? 'monospace' : 'inherit',
        background: 'var(--bg-input)',
        padding: '8px 10px',
        borderRadius: 6,
        wordBreak: 'break-word',
        lineHeight: 1.5,
      }}>
        {value}
      </div>
    </div>
  )
}

function IssuesCard({ issues }: { issues: ParsedIssue[] }) {
  return (
    <Card>
      <SectionTitle
        icon={ShieldCheck}
        title="Review Issues"
        count={issues.length}
        badge={{
          label: `${issues.length} TOTAL`,
          color: 'var(--primary)',
          bg: 'var(--primary-dim)',
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {issues.slice(0, 8).map((issue, idx) => (
          <IssueCard key={idx} issue={issue} />
        ))}
        {issues.length > 8 && (
          <div style={{
            fontSize: 11, color: 'var(--text-3)',
            textAlign: 'center', padding: '8px 0',
            fontStyle: 'italic',
          }}>
            + {issues.length - 8} more issues (truncated)
          </div>
        )}
      </div>
    </Card>
  )
}

function IssueCard({ issue }: { issue: ParsedIssue }) {
  const sev = severityStyle(issue.severity)
  const locationStr = issue.location || issue.file
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '12px 14px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 8, flexWrap: 'wrap',
      }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
          padding: '3px 8px', borderRadius: 4,
          background: sev.bg, color: sev.fg,
        }}>
          {sev.label}
        </span>
        {issue.category && (
          <span style={{
            fontSize: 10, fontWeight: 600,
            padding: '3px 7px', borderRadius: 4,
            background: 'var(--bg-input)', color: 'var(--text-2)',
            textTransform: 'uppercase',
          }}>
            {issue.category}
          </span>
        )}
        {locationStr && (
          <span style={{
            fontSize: 11, fontFamily: 'monospace',
            color: 'var(--text-3)',
            marginLeft: 'auto',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            maxWidth: '60%',
          }}>
            {locationStr}{issue.line ? `:${issue.line}` : ''}
          </span>
        )}
      </div>
      {(issue.title || issue.description) && (
        <div style={{
          fontSize: 12, color: 'var(--text-1)',
          lineHeight: 1.55,
          wordBreak: 'break-word',
        }}>
          {issue.title && (
            <div style={{ fontWeight: 600, marginBottom: issue.description ? 4 : 0 }}>
              {issue.title}
            </div>
          )}
          {issue.description && (
            <div style={{ color: 'var(--text-2)' }}>{issue.description}</div>
          )}
        </div>
      )}
    </div>
  )
}

function MetricsCard({ metrics, testResults }: { metrics: any; testResults: any }) {
  const items: { label: string; value: string; color?: string }[] = []
  items.push({ label: 'Total Time', value: `${metrics.total_time || 0}s` })
  items.push({ label: 'Attempts', value: String(metrics.attempts || 1) })
  items.push({ label: 'Files', value: String(metrics.files_count || 0) })
  if (testResults) {
    items.push({ label: 'Tests', value: String((testResults.report_data as any)?.summary?.collected || 0) })
    items.push({ label: 'Passed', value: String((testResults.report_data as any)?.summary?.passed || 0), color: 'var(--success)' })
    items.push({ label: 'Failed', value: String((testResults.report_data as any)?.summary?.failed || 0), color: 'var(--error)' })
  }
  items.push({ label: 'Coverage', value: `${Number(metrics.coverage || 0).toFixed(1)}%` })
  if (metrics.pylint_score !== undefined) {
    items.push({ label: 'Pylint Score', value: `${Number(metrics.pylint_score).toFixed(1)}/10` })
  }
  return (
    <Card>
      <SectionTitle icon={Clock} title="Metrics" />
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 10,
      }}>
        {items.map((it, idx) => (
          <Metric key={idx} label={it.label} value={it.value} valueColor={it.color} />
        ))}
      </div>
    </Card>
  )
}

function TerminalOutputCard({ output, executionMode }: { output: string; executionMode: string }) {
  const [open, setOpen] = useState(true)
  const [copied, setCopied] = useState(false)
  const isDocker = executionMode === 'docker_container'
  const handleCopy = useCallback(() => {
    navigator.clipboard?.writeText(output).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => { /* clipboard unavailable */ })
  }, [output])

  return (
    <Card>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center w-full text-left"
        style={{
          background: 'transparent', border: 'none',
          cursor: 'pointer', padding: 0, marginBottom: open ? 12 : 0,
          width: '100%',
        }}
      >
        <SectionTitle
          icon={MonitorPlay}
          title="Terminal Output"
          badge={{
            label: isDocker ? 'DOCKER' : 'LOCAL',
            color: isDocker ? '#22c55e' : '#f97316',
            bg: isDocker ? 'rgba(34,197,94,0.15)' : 'rgba(249,115,22,0.15)',
          }}
        />
        <span style={{ marginLeft: 8, color: 'var(--text-3)' }}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              background: '#0d1117',
              borderRadius: 8,
              border: '1px solid var(--border)',
              overflow: 'hidden',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px',
                borderBottom: '1px solid rgba(255,255,255,0.05)',
                background: 'rgba(255,255,255,0.02)',
              }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: '#7d8590', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {executionMode}
                </span>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1"
                  style={{
                    background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
                    color: copied ? '#22c55e' : '#7d8590',
                    fontSize: 10, fontWeight: 600,
                    padding: '3px 8px', borderRadius: 4,
                    cursor: 'pointer', textTransform: 'uppercase',
                  }}
                  onMouseEnter={e => { if (!copied) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.3)' }}
                  onMouseLeave={e => { if (!copied) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)' }}
                >
                  {copied ? <Check size={10} /> : <Copy size={10} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <pre style={{
                margin: 0,
                padding: '12px 14px',
                background: '#0d1117',
                color: '#c9d1d9',
                fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
                fontSize: 11,
                lineHeight: 1.55,
                maxHeight: 320,
                overflowY: 'auto',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {output}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}

function GeneratedFilesCard({ files, contents, onSelect }: {
  files: string[]
  contents: Record<string, string>
  onSelect: (path: string) => void
}) {
  return (
    <Card>
      <SectionTitle icon={FileText} title="Generated Files" count={files.length} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {files.slice(0, 12).map(f => {
          const name = f.split('/').pop() || f
          const lines = contents[f]?.split('\n').length || 0
          return (
            <button
              key={f}
              onClick={() => onSelect(f)}
              className="flex items-center gap-2 rounded-md w-full text-left transition-colors duration-100"
              style={{
                padding: '8px 10px',
                background: 'var(--bg-input)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
            >
              <FileIcon filename={name} size={13} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 12, fontWeight: 500, color: 'var(--text-1)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{lines} lines</div>
              </div>
              <Eye size={12} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
            </button>
          )
        })}
        {files.length > 12 && (
          <div style={{
            fontSize: 11, color: 'var(--text-3)',
            textAlign: 'center', padding: '4px 0',
            fontStyle: 'italic',
          }}>
            + {files.length - 12} more files
          </div>
        )}
      </div>
    </Card>
  )
}

function FinalStatusCard() {
  return (
    <Card accent="success">
      <div style={{
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', textAlign: 'center',
        gap: 10, padding: '4px 0',
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: 14,
          background: 'var(--success-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <CheckCircle2 size={26} style={{ color: 'var(--success)' }} />
        </div>
        <div>
          <div style={{
            fontSize: 14, fontWeight: 600, color: 'var(--success)',
            marginBottom: 4,
          }}>
            Pipeline Complete
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
            All artifacts saved to the workspace.
          </div>
        </div>
      </div>
    </Card>
  )
}
