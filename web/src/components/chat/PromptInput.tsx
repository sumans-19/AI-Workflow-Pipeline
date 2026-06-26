import { useState, useRef } from 'react'
import { Paperclip, Mic, Send, ChevronUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSession } from '../../hooks/useSession'
import { useSessionStore } from '../../store/sessionStore'

const SUGGESTIONS = [
  'Add error handling',
  'Write unit tests',
  'Add TypeScript types',
  'Optimize performance',
  'Add API documentation',
]

export default function PromptInput() {
  const [value, setValue] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [charCount, setCharCount] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { createSession } = useSession()
  const status = useSessionStore(s => s.status)
  const isDisabled = status === 'running' || status === 'checkpoint'

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    setCharCount(e.target.value.length)
    // Auto-resize
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  const handleSubmit = async () => {
    if (!value.trim() || isDisabled) return
    const prompt = value.trim()
    setValue('')
    setCharCount(0)
    if (textareaRef.current) {
      textareaRef.current.style.height = '40px'
    }
    await createSession(prompt)
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div
      className="border-t"
      style={{
        height: 'var(--promptbar-h)',
        minHeight: 'var(--promptbar-h)',
        background: 'var(--bg-panel)',
        borderColor: 'var(--border)',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        flexShrink: 0,
        position: 'relative',
      }}
    >
      {/* Suggested prompts */}
      <AnimatePresence>
        {showSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full left-6 right-6 mb-2 card p-3"
            style={{ zIndex: 60 }}
          >
            <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
              Suggestions
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => { setValue(s); setShowSuggestions(false) }}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 6,
                    background: 'var(--bg-base)',
                    border: '1px solid var(--border)',
                    fontSize: 12,
                    color: 'var(--text-2)',
                    cursor: 'pointer',
                    transition: 'all 150ms',
                  }}
                  onMouseEnter={e => {
                    ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--primary)'
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--primary)'
                  }}
                  onMouseLeave={e => {
                    ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--text-2)'
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input container */}
      <div
        className="flex items-center gap-3 w-full"
        style={{
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-xl)',
          padding: '0 16px',
          height: 48,
          transition: 'border-color 150ms',
        }}
        onFocus={() => {}}
      >
        {/* Left actions */}
        <button
          data-tooltip="Attach file"
          onClick={() => setShowSuggestions(s => !s)}
          style={{ color: 'var(--text-3)', flexShrink: 0, transition: 'color 150ms' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
        >
          {showSuggestions
            ? <ChevronUp size={18} strokeWidth={1.75} />
            : <Paperclip size={18} strokeWidth={1.75} />}
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKey}
          disabled={isDisabled}
          placeholder={
            isDisabled
              ? status === 'checkpoint' ? 'Use the Review panel to respond…' : 'Pipeline is running…'
              : 'Describe what you want to build… (Enter to send, Shift+Enter for newline)'
          }
          rows={1}
          className="flex-1 resize-none bg-transparent outline-none"
          style={{
            fontSize: 14,
            color: 'var(--text-1)',
            lineHeight: 1.5,
            height: 40,
            paddingTop: 10,
            caretColor: 'var(--primary)',
          }}
        />

        {/* Right actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {charCount > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{charCount}</span>
          )}
          <button
            style={{ color: 'var(--text-3)', flexShrink: 0, transition: 'color 150ms' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-1)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
            data-tooltip="Voice input"
          >
            <Mic size={18} strokeWidth={1.75} />
          </button>
          <button
            onClick={handleSubmit}
            disabled={!value.trim() || isDisabled}
            className="flex items-center justify-center rounded-lg transition-all duration-150"
            style={{
              width: 32, height: 32,
              background: value.trim() && !isDisabled ? 'var(--primary)' : 'var(--bg-card)',
              color: value.trim() && !isDisabled ? 'white' : 'var(--text-3)',
              border: 'none',
              cursor: value.trim() && !isDisabled ? 'pointer' : 'not-allowed',
              boxShadow: value.trim() && !isDisabled ? '0 2px 8px rgba(99,102,241,0.4)' : 'none',
            }}
          >
            <Send size={15} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  )
}
