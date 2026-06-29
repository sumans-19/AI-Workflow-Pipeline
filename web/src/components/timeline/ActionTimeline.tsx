import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2, XCircle, Code2, FlaskConical, SearchCheck, ShieldCheck, Clock3,
  ClipboardList, Loader2,
} from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import type { PipelineStage, StageStatus, TimelineStep } from '../../types'

const STAGES: { stage: PipelineStage; label: string; icon: React.ElementType; description: string }[] = [
  { stage: 'PLANNING',    label: 'Planning',        icon: ClipboardList, description: 'Design the implementation plan' },
  { stage: 'CODING',      label: 'Code Generation', icon: Code2,         description: 'Generate the project files'    },
  { stage: 'TESTING',     label: 'Testing',         icon: FlaskConical,  description: 'Run the test suite'            },
  { stage: 'REVIEWING',   label: 'Code Review',     icon: SearchCheck,   description: 'Review generated code'         },
  { stage: 'VALIDATING',  label: 'Validation',      icon: ShieldCheck,   description: 'Final validation & polish'     },
]

const STATUS_LABELS: Record<StageStatus, string> = {
  pending:    'Waiting',
  in_progress:'Running',
  complete:   'Completed',
  error:      'Failed',
  bypassed:   'Bypassed',
}

// Spring transitions used everywhere for a polished, 60 FPS feel
const spring = { type: 'spring' as const, stiffness: 320, damping: 28, mass: 0.7 }
const softSpring = { type: 'spring' as const, stiffness: 180, damping: 24, mass: 0.8 }

export default function ActionTimeline() {
  const timeline = useSessionStore(s => s.timeline)
  const status   = useSessionStore(s => s.status)

  const getStep = (stage: PipelineStage): TimelineStep | undefined =>
    timeline.findLast(s => s.stage === stage)

  return (
    <div
      style={{
        background: 'var(--bg-panel)',
        padding: '16px 14px 18px',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          paddingBottom: 14,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 26, height: 26, borderRadius: 7,
            background: 'rgba(99,102,241,0.14)',
            border: '1px solid rgba(99,102,241,0.28)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Clock3 size={13} strokeWidth={2} style={{ color: '#A5B4FC' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Pipeline
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 1 }}>
            5 stages · {STAGES.filter(s => getStep(s.stage)?.status === 'complete' || getStep(s.stage)?.status === 'bypassed').length} done
          </span>
        </div>

        {status === 'running' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={spring}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 9px',
              borderRadius: 99,
              background: 'rgba(91,124,255,0.12)',
              color: 'var(--primary)',
              border: '1px solid rgba(91,124,255,0.28)',
              flexShrink: 0,
            }}
          >
            <motion.span
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
              style={{
                width: 6, height: 6, borderRadius: '50%',
                background: 'var(--primary)',
                boxShadow: '0 0 8px rgba(99,102,241,0.7)',
              }}
            />
            <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Live
            </span>
          </motion.div>
        )}
      </div>

      {/* Vertical workflow */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          position: 'relative',
        }}
      >
        {STAGES.map((s, i) => {
          const step = getStep(s.stage)
          const status: StageStatus = step?.status ?? 'pending'
          const isLast = i === STAGES.length - 1
          const nextStep = !isLast ? getStep(STAGES[i + 1].stage) : undefined
          const nextStatus: StageStatus = nextStep?.status ?? 'pending'
          const connectorActive =
            status === 'complete' || status === 'bypassed' ||
            (status === 'in_progress' && (nextStatus === 'in_progress' || nextStatus === 'complete' || nextStatus === 'bypassed'))

          return (
            <div key={s.stage} style={{ position: 'relative' }}>
              <StageCard
                index={i}
                stage={s.stage}
                label={s.label}
                description={s.description}
                icon={s.icon}
                status={status}
                stepMessage={step?.message}
              />
              {!isLast && (
                <Connector
                  isActive={connectorActive}
                  isFlowing={status === 'in_progress'}
                  isSuccess={(status === 'complete' || status === 'bypassed') &&
                              (nextStatus === 'pending' || nextStatus === 'in_progress' || nextStatus === 'complete' || nextStatus === 'bypassed')}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Stage Card
// ─────────────────────────────────────────────────────────────
function StageCard({ index, label, description, icon: Icon, status, stepMessage }: {
  index: number
  stage: PipelineStage
  label: string
  description: string
  icon: React.ElementType
  status: StageStatus
  stepMessage?: string
}) {
  const isWaiting = status === 'pending'
  const isRunning = status === 'in_progress'
  const isComplete = status === 'complete' || status === 'bypassed'
  const isError = status === 'error'

  const labelText = STATUS_LABELS[status]
  let badgeBg = 'var(--bg-input)'
  let badgeFg = 'var(--text-3)'
  let badgeBorder = 'var(--border)'
  if (isRunning) {
    badgeBg = 'rgba(99,102,241,0.16)'; badgeFg = '#A5B4FC'; badgeBorder = 'rgba(99,102,241,0.32)'
  } else if (isComplete) {
    badgeBg = 'rgba(34,197,94,0.14)'; badgeFg = '#22c55e'; badgeBorder = 'rgba(34,197,94,0.30)'
  } else if (isError) {
    badgeBg = 'rgba(239,68,68,0.14)'; badgeFg = '#F87171'; badgeBorder = 'rgba(239,68,68,0.30)'
  }

  // Border + shadow state
  const borderColor = isRunning  ? 'rgba(99,102,241,0.55)'
    : isComplete ? 'rgba(34,197,94,0.35)'
    : isError    ? 'rgba(239,68,68,0.45)'
    : 'var(--border)'
  const boxShadow = isRunning  ? '0 0 0 1px rgba(99,102,241,0.18), 0 6px 18px -8px rgba(99,102,241,0.45)'
    : isComplete ? '0 0 0 1px rgba(34,197,94,0.10), 0 4px 14px -8px rgba(34,197,94,0.45)'
    : isError    ? '0 0 0 1px rgba(239,68,68,0.10), 0 4px 14px -8px rgba(239,68,68,0.45)'
    : '0 1px 3px rgba(0,0,0,0.20)'

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{
        opacity: 1,
        y: 0,
        boxShadow,
        borderColor,
      }}
      transition={{ ...softSpring, delay: index * 0.04 }}
      whileHover={{ y: -2, borderColor: isWaiting ? 'rgba(99,102,241,0.40)' : borderColor }}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 14px',
        borderRadius: 14,
        background: 'var(--bg-card)',
        border: `1px solid ${borderColor}`,
        boxShadow,
        cursor: 'default',
        overflow: 'hidden',
        minHeight: 64,
      }}
    >
      {/* Background sweep for running stage */}
      <AnimatePresence>
        {isRunning && (
          <motion.div
            key="sweep"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              background:
                'linear-gradient(110deg, transparent 30%, rgba(99,102,241,0.10) 50%, transparent 70%)',
              backgroundSize: '200% 100%',
            }}
          >
            <motion.div
              animate={{ backgroundPosition: ['200% 0%', '-200% 0%'] }}
              transition={{ repeat: Infinity, duration: 2.6, ease: 'linear' }}
              style={{
                position: 'absolute',
                inset: 0,
                background:
                  'linear-gradient(110deg, transparent 30%, rgba(99,102,241,0.16) 50%, transparent 70%)',
                backgroundSize: '200% 100%',
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Subtle radial glow for running stage */}
      <AnimatePresence>
        {isRunning && (
          <motion.div
            key="glow"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.18, 0.32, 0.18] }}
            exit={{ opacity: 0 }}
            transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              background:
                'radial-gradient(circle at top right, rgba(99,102,241,0.18), transparent 70%)',
            }}
          />
        )}
      </AnimatePresence>

      {/* Icon tile */}
      <IconTile
        Icon={Icon}
        isWaiting={isWaiting}
        isRunning={isRunning}
        isComplete={isComplete}
        isError={isError}
      />

      {/* Text */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span
            style={{
              fontSize: 12.5,
              fontWeight: 600,
              color: isWaiting ? 'var(--text-2)' : 'var(--text-1)',
              letterSpacing: '0.01em',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </span>
          <span
            style={{
              fontSize: 9.5,
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              padding: '2px 7px',
              borderRadius: 4,
              background: badgeBg,
              color: badgeFg,
              border: `1px solid ${badgeBorder}`,
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {labelText}
          </span>
        </div>
        <span
          style={{
            fontSize: 10.5,
            color: 'var(--text-3)',
            lineHeight: 1.35,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={stepMessage || description}
        >
          {stepMessage || description}
        </span>
      </div>

      {/* Right-side completion check or running spinner */}
      <div
        style={{
          flexShrink: 0,
          position: 'relative',
          zIndex: 1,
          width: 18,
          height: 18,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <AnimatePresence mode="wait">
          {isRunning && (
            <motion.div
              key="spin"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1, rotate: 360 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={{
                opacity: { duration: 0.2 },
                scale: { duration: 0.2 },
                rotate: { repeat: Infinity, duration: 1.4, ease: 'linear' },
              }}
            >
              <Loader2 size={16} strokeWidth={2.25} style={{ color: 'var(--primary)' }} />
            </motion.div>
          )}
          {isComplete && (
            <motion.div
              key="ok"
              initial={{ scale: 0, rotate: -45 }}
              animate={{ scale: 1, rotate: 0 }}
              exit={{ scale: 0 }}
              transition={spring}
            >
              <CheckCircle2 size={16} strokeWidth={2.25} style={{ color: '#22c55e' }} />
            </motion.div>
          )}
          {isError && (
            <motion.div
              key="err"
              initial={{ scale: 0 }}
              animate={{ scale: [1, 1.15, 1] }}
              transition={{ duration: 0.5 }}
            >
              <XCircle size={16} strokeWidth={2.25} style={{ color: 'var(--error)' }} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}

// ─────────────────────────────────────────────────────────────
// Icon tile — pulsing ring when active, success check when done
// ─────────────────────────────────────────────────────────────
function IconTile({ Icon, isWaiting, isRunning, isComplete, isError }: {
  Icon: React.ElementType
  isWaiting: boolean
  isRunning: boolean
  isComplete: boolean
  isError: boolean
}) {
  const bg = isRunning  ? 'rgba(99,102,241,0.18)'
    : isComplete ? 'rgba(34,197,94,0.16)'
    : isError    ? 'rgba(239,68,68,0.16)'
    : 'var(--bg-input)'
  const border = isRunning  ? 'rgba(99,102,241,0.45)'
    : isComplete ? 'rgba(34,197,94,0.40)'
    : isError    ? 'rgba(239,68,68,0.40)'
    : 'var(--border)'
  const iconColor = isRunning  ? 'var(--primary)'
    : isComplete ? '#22c55e'
    : isError    ? 'var(--error)'
    : 'var(--text-3)'

  return (
    <div
      style={{
        position: 'relative',
        width: 36,
        height: 36,
        flexShrink: 0,
        zIndex: 1,
      }}
    >
      {/* Pulsing ring for running */}
      <AnimatePresence>
        {isRunning && (
          <>
            <motion.div
              key="ring1"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: [0.4, 0], scale: [1, 1.5] }}
              exit={{ opacity: 0 }}
              transition={{ repeat: Infinity, duration: 1.8, ease: 'easeOut' }}
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: 10,
                border: '1.5px solid rgba(99,102,241,0.55)',
              }}
            />
            <motion.div
              key="ring2"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: [0.5, 0], scale: [1, 1.8] }}
              exit={{ opacity: 0 }}
              transition={{ repeat: Infinity, duration: 1.8, ease: 'easeOut', delay: 0.6 }}
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: 10,
                border: '1.5px solid rgba(99,102,241,0.35)',
              }}
            />
          </>
        )}
      </AnimatePresence>

      <motion.div
        animate={{ backgroundColor: bg, borderColor: border, scale: isRunning ? [1, 1.04, 1] : 1 }}
        transition={{
          backgroundColor: { duration: 0.3 },
          borderColor:    { duration: 0.3 },
          scale:          isRunning ? { repeat: Infinity, duration: 2, ease: 'easeInOut' } : { duration: 0.2 },
        }}
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 10,
          border: `1px solid ${border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: isRunning ? '0 0 12px rgba(99,102,241,0.30)' : 'none',
        }}
      >
        <AnimatePresence mode="wait">
          {isComplete ? (
            <motion.div
              key="check"
              initial={{ scale: 0, rotate: -90 }}
              animate={{ scale: 1, rotate: 0 }}
              exit={{ scale: 0 }}
              transition={spring}
            >
              <CheckCircle2 size={16} strokeWidth={2.25} style={{ color: '#22c55e' }} />
            </motion.div>
          ) : isError ? (
            <motion.div key="x" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={spring}>
              <XCircle size={16} strokeWidth={2.25} style={{ color: 'var(--error)' }} />
            </motion.div>
          ) : (
            <motion.div
              key="icon"
              animate={isRunning ? { rotate: [0, 4, -4, 0] } : { rotate: 0 }}
              transition={isRunning ? { repeat: Infinity, duration: 2, ease: 'easeInOut' } : { duration: 0.2 }}
            >
              <Icon
                size={15}
                strokeWidth={isWaiting ? 1.5 : 2}
                style={{ color: iconColor, opacity: isWaiting ? 0.85 : 1 }}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Vertical connector with flowing pulse when active
// ─────────────────────────────────────────────────────────────
function Connector({ isActive, isFlowing, isSuccess }: {
  isActive: boolean
  isFlowing: boolean
  isSuccess: boolean
}) {
  return (
    <div
      style={{
        position: 'relative',
        height: 14,
        width: 36,
        marginLeft: 17, // centers under the 36×36 icon tile (17 = 18 - 1)
        display: 'flex',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {/* Base rail */}
      <div
        style={{
          position: 'absolute',
          top: 0, bottom: 0,
          width: 2,
          background: isActive ? 'rgba(34,197,94,0.35)' : 'var(--border)',
          transition: 'background 300ms',
          borderRadius: 1,
        }}
      />

      {/* Flowing pulse (only when previous stage is running) */}
      <AnimatePresence>
        {isFlowing && (
          <motion.div
            key="pulse"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: [0, 1, 0], y: [0, 14, 14] }}
            exit={{ opacity: 0 }}
            transition={{
              opacity: { duration: 1.0, times: [0, 0.3, 1], repeat: Infinity, ease: 'easeInOut' },
              y:       { duration: 1.0, repeat: Infinity, ease: 'easeInOut' },
            }}
            style={{
              position: 'absolute',
              top: 0,
              left: '50%',
              transform: 'translateX(-50%)',
              width: 2,
              height: 14,
              background: 'linear-gradient(to bottom, transparent, rgba(99,102,241,0.95), transparent)',
              borderRadius: 2,
              boxShadow: '0 0 8px rgba(99,102,241,0.7)',
            }}
          />
        )}
      </AnimatePresence>

      {/* Tiny dot at the midpoint to break the line visually */}
      <motion.div
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.25 }}
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: isActive ? 5 : 4,
          height: isActive ? 5 : 4,
          borderRadius: '50%',
          background: isSuccess ? '#22c55e' : 'var(--text-3)',
          boxShadow: isSuccess ? '0 0 6px rgba(34,197,94,0.55)' : 'none',
          transition: 'all 300ms',
        }}
      />
    </div>
  )
}