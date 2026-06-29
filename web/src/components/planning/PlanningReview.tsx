import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, Edit3, RotateCcw, ClipboardList, Ban } from 'lucide-react'
import { useSessionStore } from '../../store/sessionStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import type { PlanningDocument } from '../../types'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Props {
  plan: PlanningDocument
  planMarkdown: string
}

export default function PlanningReview({ planMarkdown }: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState(planMarkdown)
  const { sendCheckpointResponse } = useWebSocket()
  const modulesGenerated = useSessionStore((s: any) => s.planningModulesGenerated)

  const handleApprove = () => {
    sendCheckpointResponse('approve')
  }

  const handleReject = () => {
    sendCheckpointResponse('reject')
  }

  const handleRegenerate = () => {
    sendCheckpointResponse('regenerate_plan')
  }

  const handleEditSubmit = () => {
    sendCheckpointResponse('edit_plan', editValue)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="card flex flex-col w-full max-w-[900px] shadow-2xl"
      style={{ border: '1px solid var(--border)', maxHeight: '90vh' }}
    >
      <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: 'var(--primary-dim)', color: 'var(--primary)' }}>
            <ClipboardList size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold m-0" style={{ color: 'var(--text-1)' }}>Implementation Plan</h2>
            <p className="text-xs m-0 mt-1" style={{ color: 'var(--text-3)' }}>
              {modulesGenerated.length} modules generated. Review before generating code.
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6" style={{ background: 'var(--bg-base)' }}>
        {isEditing ? (
          <div className="h-full flex flex-col gap-3">
            <p className="text-sm m-0" style={{ color: 'var(--text-2)' }}>
              Edit the plan markdown below. The Coder agent will use this updated plan.
            </p>
            <textarea
              className="w-full flex-1 p-4 rounded-lg outline-none font-mono text-sm"
              style={{
                background: 'var(--bg-input)',
                color: 'var(--text-1)',
                border: '1px solid var(--border)',
                resize: 'none'
              }}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
            />
          </div>
        ) : (
          <div className="markdown-body text-sm" style={{ color: 'var(--text-2)' }}>
            <Markdown remarkPlugins={[remarkGfm]}>
              {planMarkdown}
            </Markdown>
          </div>
        )}
      </div>

      <div className="p-4 border-t flex justify-between items-center bg-black/20" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={handleReject}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-red-500/10 hover:text-red-500 cursor-pointer"
          style={{ color: 'var(--text-3)' }}
        >
          <Ban size={15} /> Reject
        </button>
        
        <div className="flex items-center gap-3">
          {isEditing ? (
            <>
              <button
                onClick={() => setIsEditing(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer"
                style={{ color: 'var(--text-2)' }}
              >
                Cancel
              </button>
              <button
                onClick={handleEditSubmit}
                className="flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-semibold transition-all cursor-pointer"
                style={{ background: 'var(--primary)', color: '#fff' }}
              >
                <Check size={15} /> Save & Continue
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setIsEditing(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer"
                style={{ border: '1px solid var(--border)', color: 'var(--text-2)' }}
              >
                <Edit3 size={15} /> Edit
              </button>
              <button
                onClick={handleRegenerate}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer"
                style={{ border: '1px solid var(--border)', color: 'var(--text-2)' }}
              >
                <RotateCcw size={15} /> Regenerate
              </button>
              <button
                onClick={handleApprove}
                className="flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-semibold transition-all shadow-lg cursor-pointer"
                style={{ background: 'var(--success)', color: '#fff' }}
              >
                <Check size={15} /> Approve Plan
              </button>
            </>
          )}
        </div>
      </div>
    </motion.div>
  )
}
