import {
  MessageSquare, Code2, MonitorPlay, Box, AlertCircle
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { useSessionStore } from '../../store/sessionStore'

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
  const [dockerStatus, setDockerStatus] = useState<'checking' | 'available' | 'unavailable'>('checking')
  const [showDockerGuide, setShowDockerGuide] = useState(false)
  const testExecutionMode = useSessionStore(s => s.testExecutionMode)
  const setTestExecutionMode = useSessionStore(s => s.setTestExecutionMode)

  useEffect(() => {
    const checkDocker = () => {
      fetch('http://127.0.0.1:8000/api/docker/status')
        .then(res => res.json())
        .then(data => {
          setDockerStatus(data.status)
          if (data.status === 'unavailable') {
            setTestExecutionMode('local')
          }
        })
        .catch(() => {
          setDockerStatus('unavailable')
          setTestExecutionMode('local')
        })
    }

    checkDocker()
    const interval = setInterval(checkDocker, 5000)
    return () => clearInterval(interval)
  }, [setTestExecutionMode])

  return (
    <header
      className="flex items-center justify-between border-b select-none relative"
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

      {/* Right section */}
      <div className="flex items-center justify-end flex-1 min-w-0 gap-4">
        {/* Docker/Local Toggle Indicator */}
        <div 
          className="relative flex items-center transition-colors"
          style={{ 
            gap: 6,
            padding: '4px 6px',
            borderRadius: 24,
            whiteSpace: 'nowrap',
            background: 'var(--bg-input)',
            border: '1px solid var(--border)',
            userSelect: 'none'
          }}
          onMouseEnter={() => setShowDockerGuide(true)}
          onMouseLeave={() => setShowDockerGuide(false)}
        >
          {/* Local Button */}
          <button
            onClick={() => setTestExecutionMode('local')}
            className="flex items-center gap-1.5 transition-all duration-200"
            style={{
              padding: '4px 10px',
              borderRadius: 20,
              fontSize: 11,
              fontWeight: 600,
              color: testExecutionMode === 'local' ? '#f97316' : 'var(--text-3)',
              background: testExecutionMode === 'local' ? 'rgba(249, 115, 22, 0.1)' : 'transparent',
            }}
          >
            <AlertCircle size={13} />
            Local
          </button>

          {/* Docker Button */}
          <button
            onClick={() => {
              if (dockerStatus === 'available') {
                setTestExecutionMode('docker')
              }
            }}
            className={`flex items-center gap-1.5 transition-all duration-200 ${dockerStatus !== 'available' ? 'cursor-not-allowed opacity-50' : ''}`}
            style={{
              padding: '4px 10px',
              borderRadius: 20,
              fontSize: 11,
              fontWeight: 600,
              color: testExecutionMode === 'docker' ? '#22c55e' : 'var(--text-3)',
              background: testExecutionMode === 'docker' ? 'rgba(34, 197, 94, 0.1)' : 'transparent',
            }}
          >
            <Box size={13} />
            Docker
          </button>

          {/* Setup Guide Tooltip */}
          {showDockerGuide && dockerStatus === 'unavailable' && (
            <div className="absolute right-0 top-full mt-2 w-72 p-4 rounded-lg shadow-xl z-50 text-left"
                 style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8 }}>
                Docker Setup Guide
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 12, lineHeight: 1.5 }}>
                Docker is unavailable. Toggle is locked to local mode.
              </p>
              <ul style={{ fontSize: 12, color: 'var(--text-2)', paddingLeft: 16, listStyleType: 'disc', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <li>Install Docker Desktop</li>
                <li>Enable WSL2 backend (Windows)</li>
                <li>Start Docker Desktop</li>
                <li>Verify using: <code style={{ background: 'var(--bg-input)', padding: '2px 4px', borderRadius: 4, color: 'var(--primary)' }}>docker info</code></li>
              </ul>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
