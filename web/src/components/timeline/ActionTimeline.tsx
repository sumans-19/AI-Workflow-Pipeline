import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2, XCircle, Code2, FlaskConical, SearchCheck, ShieldCheck, Clock3
} from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import type { PipelineStage, StageStatus, TimelineStep } from '../../types'

const STAGES: { stage: PipelineStage; label: string; icon: React.ElementType }[] = [
  { stage: 'CODING', label: 'Code Generation', icon: Code2 },
  { stage: 'TESTING', label: 'Testing', icon: FlaskConical },
  { stage: 'REVIEWING', label: 'Code Review', icon: SearchCheck },
  { stage: 'VALIDATING', label: 'Validation', icon: ShieldCheck },
]

// S-pattern flow: 0->1 (TL to TR), 1->2 (TR to BL), 2->3 (BL to BR)
const PATHS = [
  "M 25 25 L 75 25",
  "M 75 25 C 75 50, 25 50, 25 75",
  "M 25 75 L 75 75"
]

export default function ActionTimeline() {
  const timeline = useSessionStore(s => s.timeline)
  const status = useSessionStore(s => s.status)

  const getStep = (stage: PipelineStage): TimelineStep | undefined =>
    timeline.findLast(s => s.stage === stage)

  return (
    <div style={{ background: '#0F172A', padding: '14px', display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      {/* Header */}
      <div
        className="flex items-center gap-2"
        style={{
          paddingBottom: '10px',
          flexShrink: 0,
        }}
      >
        <Clock3 size={13} strokeWidth={2.5} style={{ color: '#E6EAF2' }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: '#E6EAF2', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Pipeline
        </span>
        {status === 'running' && (
          <div
            className="ml-auto flex items-center gap-2"
            style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 99,
              background: 'rgba(91,124,255,0.1)', color: '#5B7CFF',
              border: '1px solid rgba(91,124,255,0.2)'
            }}
          >
            <motion.div
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ repeat: Infinity, duration: 1.5, ease: "easeInOut" }}
              style={{ width: 5, height: 5, borderRadius: '50%', background: '#5B7CFF' }}
            />
            <span className="font-semibold tracking-wide uppercase">Running</span>
          </div>
        )}
      </div>

      <div className="relative w-full mx-auto" style={{ flex: 1 }}>
        {/* SVG Connectors */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <svg className="w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
            {PATHS.map((d, i) => {
              const stageStatus = getStep(STAGES[i].stage)?.status ?? 'pending'
              const isPulse = stageStatus === 'in_progress'
              const isSolid = stageStatus === 'complete'

              return (
                <g key={i}>
                  {/* Base Track */}
                  <path
                    d={d}
                    stroke="rgba(255,255,255,0.06)"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                    fill="none"
                    strokeLinecap="round"
                  />
                  {/* Solid Green Completed */}
                  <motion.path
                    d={d}
                    stroke="#22C55E"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                    fill="none"
                    strokeLinecap="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: isSolid ? 1 : 0 }}
                    transition={{ duration: 0.6, ease: "easeInOut" }}
                  />
                  {/* Glowing Pulse */}
                  <AnimatePresence>
                    {isPulse && (
                      <motion.path
                        d={d}
                        stroke="#5B7CFF"
                        strokeWidth="2"
                        vectorEffect="non-scaling-stroke"
                        fill="none"
                        strokeLinecap="round"
                        style={{ filter: 'drop-shadow(0 0 4px rgba(91,124,255,0.6))' }}
                        initial={{ pathLength: 0, pathOffset: 0, opacity: 0 }}
                        animate={{ pathLength: 0.25, pathOffset: 1, opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{
                          pathOffset: { repeat: Infinity, duration: 1.5, ease: "linear" },
                          opacity: { duration: 0.3 }
                        }}
                      />
                    )}
                  </AnimatePresence>
                </g>
              )
            })}
          </svg>
        </div>

        {/* 2x2 Grid Layout */}
        <div className="grid grid-cols-2 grid-rows-2 gap-2.5 relative z-10 w-full h-[180px]">
          {STAGES.map(({ stage, label, icon: Icon }) => {
            const step = getStep(stage)
            const s: StageStatus = step?.status ?? 'pending'

            const isWaiting = s === 'pending';
            const isRunning = s === 'in_progress';
            const isComplete = s === 'complete';
            const isError = s === 'error';

            let CurrentIcon = Icon;
            if (isComplete) CurrentIcon = CheckCircle2;
            if (isError) CurrentIcon = XCircle;

            const iconColor = isRunning ? '#5B7CFF' :
              isComplete ? '#22C55E' :
                isError ? '#EF4444' :
                  '#94A3B8';

            return (
              <motion.div
                key={stage}
                initial={false}
                animate={{
                  scale: isRunning ? 1.02 : 1,
                  boxShadow: isRunning ? '0 8px 24px -4px rgba(91,124,255,0.12), 0 0 0 1px rgba(91,124,255,0.3)' :
                    isComplete ? '0 4px 12px -2px rgba(0,0,0,0.2), 0 0 0 1px rgba(255,255,255,0.12)' :
                      isError ? '0 4px 12px rgba(239,68,68,0.2), 0 0 0 1px #EF4444' :
                        '0 2px 8px rgba(0,0,0,0.1), 0 0 0 1px rgba(255,255,255,0.06)',
                  x: isError ? [0, -4, 4, -4, 4, 0] : 0,
                  backgroundColor: '#172033'
                }}
                transition={{
                  scale: { duration: 0.3, ease: "easeOut" },
                  boxShadow: isRunning ? { repeat: Infinity, duration: 2.5, ease: "easeInOut", repeatType: "mirror" } : { duration: 0.3 },
                  x: { duration: 0.4 }
                }}
                whileHover={{ y: -2 }}
                className="flex flex-col justify-center items-start relative overflow-hidden"
                style={{
                  padding: '10px 12px',
                  borderRadius: '10px',
                  gap: '6px',
                  cursor: 'default'
                }}
              >
                {/* Subtle Gradient Tint for Running */}
                <AnimatePresence>
                  {isRunning && (
                    <motion.div
                      className="absolute inset-0 pointer-events-none"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: [0.15, 0.35, 0.15] }}
                      exit={{ opacity: 0 }}
                      transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
                      style={{
                        background: 'radial-gradient(circle at top left, rgba(91,124,255,0.15), transparent 70%)'
                      }}
                    />
                  )}
                </AnimatePresence>

                <div className="flex items-center justify-center relative z-10">
                  <motion.div
                    initial={false}
                    animate={
                      isRunning ? { opacity: [0.7, 1, 0.7], scale: [0.95, 1.05, 0.95] } :
                        isComplete ? { scale: [0.8, 1.2, 1] } :
                          isError ? { scale: [0.8, 1.2, 1] } : {}
                    }
                    transition={
                      isRunning ? { repeat: Infinity, duration: 2, ease: "easeInOut" } :
                        isComplete || isError ? { duration: 0.4, ease: "easeOut" } : {}
                    }
                    style={{ color: iconColor }}
                  >
                    <CurrentIcon size={16} strokeWidth={isRunning ? 2 : 1.75} />
                  </motion.div>
                </div>

                <div className="relative z-10 w-full">
                  <div style={{ color: isWaiting ? '#94A3B8' : '#E6EAF2', fontSize: '11.5px', fontWeight: 500, letterSpacing: '0.01em', transition: 'color 0.3s' }}>
                    {label}
                  </div>
                  <div style={{ color: '#94A3B8', fontSize: '10px', marginTop: '2px', height: '14px', display: 'flex', alignItems: 'center' }}>
                    <AnimatePresence mode="wait">
                      <motion.span
                        key={s}
                        initial={{ opacity: 0, y: 2 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -2 }}
                        transition={{ duration: 0.2 }}
                      >
                        {isRunning ? 'Running...' : isComplete ? 'Completed' : isError ? 'Failed' : 'Waiting'}
                      </motion.span>
                    </AnimatePresence>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
