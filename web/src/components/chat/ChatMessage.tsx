import type { ChatMessage as ChatMessageType } from '../../types'
import { Bot } from 'lucide-react'

interface Props { message: ChatMessageType }

export default function ChatMessage({ message }: Props) {
  const { role, content } = message

  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          style={{
            maxWidth: '72%',
            padding: '12px 16px',
            borderRadius: 14,
            borderBottomRightRadius: 4,
            background: 'var(--primary)',
            color: 'white',
            fontSize: 14,
            lineHeight: 1.6,
            boxShadow: '0 2px 12px rgba(99,102,241,0.3)',
          }}
        >
          {content}
        </div>
      </div>
    )
  }

  if (role === 'system') {
    return (
      <div className="flex justify-center">
        <div
          style={{
            padding: '4px 12px',
            borderRadius: 99,
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            fontSize: 12,
            color: 'var(--text-3)',
          }}
        >
          {content}
        </div>
      </div>
    )
  }

  // Assistant
  return (
    <div className="flex items-start gap-3">
      <div
        className="flex-shrink-0 flex items-center justify-center rounded-full"
        style={{
          width: 28, height: 28, marginTop: 2,
          background: 'linear-gradient(135deg, #6366F1, #8B5CF6)',
        }}
      >
        <Bot size={13} strokeWidth={2} color="white" />
      </div>
      <div
        style={{
          maxWidth: '72%',
          padding: '12px 16px',
          borderRadius: 14,
          borderTopLeftRadius: 4,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          fontSize: 14,
          color: 'var(--text-1)',
          lineHeight: 1.7,
        }}
      >
        <InlineContent content={content} />
      </div>
    </div>
  )
}

function InlineContent({ content }: { content: string }) {
  // Render inline backtick code
  const parts = content.split(/(`[^`]+`)/)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('`') && part.endsWith('`') ? (
          <code
            key={i}
            className="mono"
            style={{
              padding: '1px 5px',
              borderRadius: 4,
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              color: 'var(--primary)',
              fontSize: 13,
            }}
          >
            {part.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}
