import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSessionStore } from '../../store/sessionStore'
import ChatMessage from './ChatMessage'
import EmptyState from './EmptyState'
import { useSession } from '../../hooks/useSession'

export default function ChatWindow() {
  const messages = useSessionStore(s => s.messages)
  const status   = useSessionStore(s => s.status)
  const { createSession } = useSession()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const isRunning = status === 'running'

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      {messages.length === 0 ? (
        <EmptyState onPrompt={createSession} />
      ) : (
        <div style={{ maxWidth: 850, margin: '0 auto' }}>
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                style={{ marginBottom: i === messages.length - 1 ? 0 : 20 }}
              >
                <ChatMessage message={msg} />
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Typing indicator */}
          {isRunning && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ marginTop: 20 }}
            >
              <TypingIndicator />
            </motion.div>
          )}

          <div ref={bottomRef} style={{ height: 1 }} />
        </div>
      )}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex items-center justify-center rounded-full flex-shrink-0"
        style={{
          width: 28, height: 28,
          background: 'linear-gradient(135deg, #6366F1, #8B5CF6)',
        }}
      >
        <span style={{ fontSize: 12, color: 'white', fontWeight: 700 }}>AI</span>
      </div>
      <div
        className="flex items-center gap-1.5 card"
        style={{ padding: '10px 14px', borderRadius: 12 }}
      >
        <span className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: 'var(--text-3)' }} />
        <span className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: 'var(--text-3)' }} />
        <span className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: 'var(--text-3)' }} />
      </div>
    </div>
  )
}
