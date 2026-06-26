import {
  MessageSquare, Code2, MonitorPlay
} from 'lucide-react'

interface Props {
  centerTab: 'chat' | 'code' | 'preview'
  onTabChange: (t: 'chat' | 'code' | 'preview') => void
}

const TABS = [
  { id: 'chat'    as const, label: 'Chat',    icon: MessageSquare },
  { id: 'code'    as const, label: 'Code',    icon: Code2 },
  { id: 'preview' as const, label: 'Preview', icon: MonitorPlay },
]

export default function TopNav({ centerTab, onTabChange }: Props) {
  return (
    <header
      className="flex items-center justify-between border-b select-none"
      style={{
        height: 'var(--topnav-h)',
        padding: '0 20px',
        background: 'var(--bg-panel)',
        borderColor: 'var(--border)',
        flexShrink: 0,
        zIndex: 50,
        gap: 12,
      }}
    >
      {/* Left section: Logo + Brand */}
      <div className="flex items-center gap-2.5 flex-1 min-w-0">
        <div className="flex flex-col leading-none">
          <span
            className="font-semibold text-xs"
            style={{ color: 'var(--text-1)', letterSpacing: '0.01em' }}
          >
            AI Dev Platform
          </span>
          <span className="text-[10px]" style={{ color: 'var(--text-3)' }}>
            Development Environment
          </span>
        </div>
      </div>

      {/* Center tabs */}
      <div
        className="flex items-center justify-center flex-shrink-0 rounded-lg"
        style={{
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          gap: 4,
          padding: 4,
        }}
      >
        {TABS.map(({ id, label, icon: Icon }) => {
          const isActive = centerTab === id;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className="flex items-center transition-all duration-200"
              style={{
                gap: 6,
                padding: '6px 14px',
                borderRadius: 6,
                fontSize: 13,
                fontFamily: 'Inter, sans-serif',
                fontWeight: 500,
                color: isActive ? 'white' : 'var(--text-3)',
                background: isActive ? 'linear-gradient(135deg, var(--primary), #4F46E5)' : 'transparent',
                boxShadow: isActive ? '0 4px 12px rgba(99,102,241,0.2)' : 'none',
                lineHeight: 1,
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.color = 'var(--text-1)';
                  (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)';
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.color = 'var(--text-3)';
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                }
              }}
            >
              <Icon size={14} strokeWidth={2} style={{ flexShrink: 0 }} />
              <span>{label}</span>
            </button>
          )
        })}
      </div>

      {/* Right section (Empty, for centering) */}
      <div className="flex-1 min-w-0" />
    </header>
  )
}
