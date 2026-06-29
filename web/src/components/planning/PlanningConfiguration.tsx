import { useState, useRef } from 'react'
import {
  Settings, Check, FolderTree, Lightbulb, ListChecks, Building2, Boxes,
  Package, Workflow, FileText, Globe, Database, Shield, TestTube, Code, AlertTriangle,
  Map, Send, ChevronDown, ChevronRight, Info, Layers, Sparkles, FolderKanban,
  Paperclip, Mic, XCircle,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSessionStore } from '../../store/sessionStore'
import type { PlanningModuleMeta } from '../../types'

const CATEGORIES = [
  {
    title: 'Project Foundation',
    modules: [
      { id: 'project_understanding', label: 'Project Understanding', description: 'Identify project type, complexity, assumptions, and ambiguous requirements.', icon: 'Lightbulb' },
      { id: 'functional_requirements', label: 'Functional Requirements', description: 'Core, secondary, optional, and future features.', icon: 'ListChecks' },
      { id: 'folder_structure', label: 'Folder Structure', description: 'Complete directory tree the Coder must respect.', icon: 'FolderTree' },
    ]
  },
  {
    title: 'Design & Architecture',
    modules: [
      { id: 'architecture_design', label: 'Architecture Design', description: 'Architecture pattern (MVC, Clean, Hexagonal, etc.) with rationale.', icon: 'Building2' },
      { id: 'component_breakdown', label: 'Component Breakdown', description: 'Modules, classes, services, interfaces, and their purposes.', icon: 'Boxes' },
      { id: 'data_flow', label: 'Data Flow', description: 'High-level execution flow from input to output.', icon: 'Workflow' },
    ]
  },
  {
    title: 'Implementation Details',
    modules: [
      { id: 'file_responsibilities', label: 'File Responsibilities', description: 'Responsibility of every planned file.', icon: 'FileText' },
      { id: 'dependency_planning', label: 'Dependency Planning', description: 'Python packages, frameworks, and runtime requirements with reasoning.', icon: 'Package' },
      { id: 'code_standards', label: 'Code Standards', description: 'Naming, organization, type hints, docstrings.', icon: 'Code' },
    ]
  },
  {
    title: 'Integrations',
    modules: [
      { id: 'api_planning', label: 'API Planning', description: 'Endpoints, HTTP methods, request/response models, auth.', icon: 'Globe' },
      { id: 'database_planning', label: 'Database Planning', description: 'DB choice, tables, entities, relationships, indexes.', icon: 'Database' },
    ]
  },
  {
    title: 'Quality & Reliability',
    modules: [
      { id: 'security_considerations', label: 'Security Considerations', description: 'Input validation, auth, secret management.', icon: 'Shield' },
      { id: 'testing_strategy', label: 'Testing Strategy', description: 'Unit, integration, e2e, edge cases, mocking.', icon: 'TestTube' },
      { id: 'risks_challenges', label: 'Risks & Challenges', description: 'Technical risks, scalability, mitigations.', icon: 'AlertTriangle' },
    ]
  },
  {
    title: 'Execution',
    modules: [
      { id: 'execution_roadmap', label: 'Execution Roadmap', description: 'Step-by-step implementation order.', icon: 'Map' },
    ]
  }
]

// Flatten modules for easy mapping
const MODULE_METADATA = CATEGORIES.flatMap(c => c.modules) as PlanningModuleMeta[]

const iconMap: Record<string, React.ElementType> = {
  Lightbulb, ListChecks, FolderTree, Building2, Boxes, Package, Workflow, FileText, Globe, Database, Shield, TestTube, Code, AlertTriangle, Map
}

interface Props {
  onSubmit: (promptText: string, projectTitle?: string) => void
}

export default function PlanningConfiguration({ onSubmit }: Props) {
  const planningConfig = useSessionStore((s: any) => s.planningConfig)
  const togglePlanningModule = useSessionStore((s: any) => s.togglePlanningModule)
  const selectAllPlanningModules = useSessionStore((s: any) => s.selectAllPlanningModules)

  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>(
    CATEGORIES.reduce((acc, cat) => ({ ...acc, [cat.title]: true }), {})
  )
  const [projectTitle, setProjectTitle] = useState('')
  const [promptText, setPromptText]   = useState('')
  const titleRef = useRef<HTMLInputElement>(null)
  const descRef  = useRef<HTMLTextAreaElement>(null)

  const selectedCount = Object.values(planningConfig.modules).filter(Boolean).length
  const totalCount = MODULE_METADATA.length
  const anySelected = selectedCount > 0
  const canSubmit = anySelected && projectTitle.trim().length > 0 && promptText.trim().length > 0

  const toggleCategory = (title: string) => {
    setExpandedCategories(prev => ({ ...prev, [title]: !prev[title] }))
  }

  const handleGenerate = () => {
    if (canSubmit) {
      // Combine title + description into the requirements prompt
      const composed = `Project Title: ${projectTitle.trim()}\n\n${promptText.trim()}`
      onSubmit(composed, projectTitle.trim())
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.99 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col h-full w-full overflow-hidden"
      style={{ background: 'transparent' }}
    >
      {/* Scrollable content area */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: '20px 24px 16px' }}
      >
        <div className="flex flex-col gap-5 max-w-[1400px] mx-auto">

          {/* Header */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Title row */}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: 24,
                flexWrap: 'wrap',
              }}
            >
              {/* Title block */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: 'rgba(99,102,241,0.14)',
                    border: '1px solid rgba(99,102,241,0.28)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    boxShadow: '0 4px 14px rgba(99,102,241,0.15)',
                  }}
                >
                  <Settings size={22} strokeWidth={1.75} style={{ color: '#A5B4FC' }} />
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <h2
                    style={{
                      fontSize: 21,
                      fontWeight: 600,
                      margin: 0,
                      color: 'white',
                      letterSpacing: '-0.01em',
                      lineHeight: 1.2,
                    }}
                  >
                    Planning Configuration
                  </h2>
                  <p
                    style={{
                      fontSize: 13,
                      margin: '6px 0 0',
                      color: 'var(--text-3)',
                      lineHeight: 1.55,
                      maxWidth: 560,
                    }}
                  >
                    Select the planning components and artifacts the agent should generate before writing code.
                  </p>
                </div>
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                <button
                  onClick={() => selectAllPlanningModules(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '9px 16px',
                    borderRadius: 8,
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    color: 'var(--text-2)',
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 150ms',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--bg-input)'
                    e.currentTarget.style.borderColor = 'rgba(99,102,241,0.45)'
                    e.currentTarget.style.color = 'white'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.color = 'var(--text-2)'
                  }}
                >
                  <ListChecks size={14} strokeWidth={2} />
                  Select All
                </button>
                <button
                  onClick={() => selectAllPlanningModules(false)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '9px 16px',
                    borderRadius: 8,
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    color: 'var(--text-2)',
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 150ms',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--bg-input)'
                    e.currentTarget.style.borderColor = 'rgba(239,68,68,0.45)'
                    e.currentTarget.style.color = 'white'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.color = 'var(--text-2)'
                  }}
                >
                  <XCircle size={14} strokeWidth={2} />
                  Clear All
                </button>
              </div>
            </div>

            {/* Info Box */}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 14,
                padding: '16px 20px',
                borderRadius: 12,
                background: 'rgba(99,102,241,0.08)',
                border: '1px solid rgba(99,102,241,0.20)',
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: 'rgba(99,102,241,0.16)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: 1,
                }}
              >
                <Info size={16} strokeWidth={2} style={{ color: '#A5B4FC' }} />
              </div>
              <p
                style={{
                  fontSize: 13,
                  margin: 0,
                  color: 'var(--text-2)',
                  lineHeight: 1.6,
                  paddingTop: 6,
                  wordBreak: 'break-word',
                }}
              >
                Select only the components you want the Planning Agent to generate. You can review and approve the plan before
                code generation begins.
              </p>
            </div>
          </div>

          {/* Main Content Area: Left Sidebar (Tree) and Right Area (Grid) */}
          <div className="flex flex-1 gap-5 min-h-0" style={{ minHeight: 480 }}>

            {/* Left Sidebar - Tree View */}
            <div
              style={{
                width: 340,
                borderRadius: 14,
                display: 'flex',
                flexDirection: 'column',
                flexShrink: 0,
                overflow: 'hidden',
                boxShadow: '0 4px 14px rgba(0,0,0,0.20)',
                background: 'var(--bg-panel)',
                border: '1px solid var(--border)',
              }}
            >
              {/* Sidebar header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '18px 20px',
                  borderBottom: '1px solid var(--border)',
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                <div
                  style={{
                    width: 32, height: 32, borderRadius: 8,
                    background: 'rgba(99,102,241,0.12)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Layers size={16} strokeWidth={1.75} style={{ color: '#A5B4FC' }} />
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <h3 style={{ fontSize: 13.5, fontWeight: 600, margin: 0, color: 'white', letterSpacing: '0.01em' }}>
                    Planning Components
                  </h3>
                  <p style={{ fontSize: 11, margin: '2px 0 0', color: 'var(--text-3)' }}>
                    Pick modules to generate
                  </p>
                </div>
              </div>

              {/* Tree */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '12px 14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                {CATEGORIES.map((category) => {
                  const catModules = category.modules
                  const selectedInCat = catModules.filter(m => planningConfig.modules[m.id]).length
                  const isExpanded = expandedCategories[category.title]

                  return (
                    <div key={category.title} style={{ display: 'flex', flexDirection: 'column' }}>
                      {/* Category row */}
                      <button
                        onClick={() => toggleCategory(category.title)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 10,
                          padding: '11px 12px',
                          borderRadius: 8,
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          width: '100%',
                          textAlign: 'left',
                          transition: 'background 120ms',
                          minWidth: 0,
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0, flex: 1 }}>
                          {isExpanded
                            ? <ChevronDown size={14} strokeWidth={2} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                            : <ChevronRight size={14} strokeWidth={2} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
                          <span style={{
                            fontSize: 13, fontWeight: 600,
                            color: 'var(--text-1)',
                            letterSpacing: '0.01em',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}>
                            {category.title}
                          </span>
                        </div>
                        <span style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '3px 9px',
                          borderRadius: 99,
                          background: selectedInCat > 0 ? 'rgba(99,102,241,0.18)' : 'var(--bg-input)',
                          color: selectedInCat > 0 ? '#A5B4FC' : 'var(--text-3)',
                          border: `1px solid ${selectedInCat > 0 ? 'rgba(99,102,241,0.30)' : 'var(--border)'}`,
                          flexShrink: 0,
                          minWidth: 22,
                          textAlign: 'center',
                          letterSpacing: '0.02em',
                        }}>
                          {selectedInCat}
                        </span>
                      </button>

                      {/* Modules (expanded) */}
                      <AnimatePresence initial={false}>
                        {isExpanded && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.18, ease: 'easeInOut' }}
                            style={{ overflow: 'hidden' }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                gap: 3,
                                padding: '6px 0 6px 14px',
                                marginLeft: 12,
                                marginTop: 4,
                                marginBottom: 6,
                                borderLeft: '2px solid var(--border)',
                              }}
                            >
                              {catModules.map(mod => {
                                const isSelected = !!planningConfig.modules[mod.id]
                                const Icon = iconMap[mod.icon] || FileText
                                return (
                                  <button
                                    key={mod.id}
                                    onClick={() => togglePlanningModule(mod.id, !isSelected)}
                                    title={mod.label}
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'space-between',
                                      gap: 10,
                                      padding: '10px 12px',
                                      borderRadius: 8,
                                      background: isSelected ? 'rgba(99,102,241,0.10)' : 'transparent',
                                      border: `1px solid ${isSelected ? 'rgba(99,102,241,0.28)' : 'transparent'}`,
                                      cursor: 'pointer',
                                      width: '100%',
                                      textAlign: 'left',
                                      transition: 'background 120ms, border-color 120ms',
                                      minWidth: 0,
                                      maxWidth: '100%',
                                      boxSizing: 'border-box',
                                    }}
                                    onMouseEnter={e => {
                                      if (!isSelected) e.currentTarget.style.background = 'var(--bg-input)'
                                    }}
                                    onMouseLeave={e => {
                                      e.currentTarget.style.background = isSelected ? 'rgba(99,102,241,0.10)' : 'transparent'
                                    }}
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                                      <Icon
                                        size={14}
                                        strokeWidth={1.75}
                                        style={{
                                          color: isSelected ? 'var(--primary)' : 'var(--text-3)',
                                          flexShrink: 0,
                                        }}
                                      />
                                      <span style={{
                                        fontSize: 12.5,
                                        fontWeight: isSelected ? 600 : 500,
                                        color: isSelected ? 'var(--text-1)' : 'var(--text-2)',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                        minWidth: 0,
                                      }}>
                                        {mod.label}
                                      </span>
                                    </div>
                                    {/* Checkbox */}
                                    <div
                                      aria-hidden
                                      style={{
                                        width: 18,
                                        height: 18,
                                        borderRadius: 5,
                                        flexShrink: 0,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        background: isSelected ? 'var(--primary)' : 'transparent',
                                        border: isSelected ? 'none' : '1.5px solid var(--text-3)',
                                        transition: 'background 120ms, border-color 120ms',
                                      }}
                                    >
                                      {isSelected && <Check size={12} strokeWidth={3.5} color="white" />}
                                    </div>
                                  </button>
                                )
                              })}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                })}
              </div>

              {/* Footer */}
              <div
                style={{
                  padding: '14px 16px',
                  borderTop: '1px solid var(--border)',
                  background: 'rgba(255,255,255,0.02)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                }}
              >
                <span style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: '5px 11px',
                  borderRadius: 6,
                  background: selectedCount > 0 ? 'rgba(99,102,241,0.18)' : 'var(--bg-input)',
                  color: selectedCount > 0 ? '#A5B4FC' : 'var(--text-3)',
                  border: `1px solid ${selectedCount > 0 ? 'rgba(99,102,241,0.30)' : 'var(--border)'}`,
                  letterSpacing: '0.01em',
                }}>
                  {selectedCount} / {totalCount} selected
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
                  {CATEGORIES.length} categories
                </span>
              </div>
            </div>

            {/* Right Area - Grid of Selected Components */}
            <div className="flex-1 flex flex-col bg-transparent relative min-w-0">
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 20,
                  padding: '14px 18px',
                  borderRadius: 10,
                  background: 'var(--bg-panel)',
                  border: '1px solid var(--border)',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                  <div
                    style={{
                      width: 28, height: 28, borderRadius: 7,
                      background: 'rgba(99,102,241,0.14)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Sparkles size={14} strokeWidth={2} style={{ color: '#A5B4FC' }} />
                  </div>
                  <h3 style={{ fontSize: 14, fontWeight: 600, color: 'white', margin: 0, letterSpacing: '0.01em' }}>
                    Selected Components
                  </h3>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    padding: '4px 10px', borderRadius: 99,
                    background: selectedCount > 0 ? 'rgba(34,197,94,0.14)' : 'var(--bg-input)',
                    color: selectedCount > 0 ? '#22c55e' : 'var(--text-3)',
                    border: `1px solid ${selectedCount > 0 ? 'rgba(34,197,94,0.30)' : 'var(--border)'}`,
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    whiteSpace: 'nowrap',
                    letterSpacing: '0.02em',
                  }}>
                    <Check size={11} strokeWidth={3} />
                    {selectedCount} selected
                  </span>
                </div>
                <span style={{
                  fontSize: 11.5, fontWeight: 600,
                  color: 'var(--text-3)',
                  whiteSpace: 'nowrap',
                  letterSpacing: '0.02em',
                }}>
                  {selectedCount} / {totalCount}
                </span>
              </div>

              <div className="flex-1 overflow-y-auto pr-1">
                {selectedCount === 0 ? (
                  <div
                    className="w-full h-full flex flex-col items-center justify-center rounded-2xl"
                    style={{
                      border: '2px dashed var(--border)',
                      background: 'var(--bg-panel)',
                      minHeight: 420,
                      padding: '48px 32px',
                      gap: 14,
                    }}
                  >
                    <div
                      style={{
                        width: 64, height: 64, borderRadius: 16,
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <Layers size={28} strokeWidth={1.5} style={{ color: 'var(--text-3)' }} />
                    </div>
                    <div className="text-center" style={{ maxWidth: 320 }}>
                      <h4 className="text-[15px] font-semibold text-white m-0 mb-2">
                        Select planning components
                      </h4>
                      <p className="text-[12px] leading-relaxed m-0" style={{ color: 'var(--text-3)' }}>
                        Pick modules from the tree on the left to add them to your planning configuration.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                      gap: 16,
                      paddingBottom: 8,
                    }}
                  >
                    <AnimatePresence>
                      {MODULE_METADATA.filter(m => planningConfig.modules[m.id]).map(mod => {
                        const Icon = iconMap[mod.icon] || FileText
                        return (
                          <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ duration: 0.18 }}
                            key={mod.id}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 14,
                              padding: '20px',
                              borderRadius: 14,
                              background: 'var(--bg-panel)',
                              border: '1px solid rgba(99,102,241,0.28)',
                              boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
                              position: 'relative',
                              minWidth: 0,
                              maxWidth: '100%',
                              boxSizing: 'border-box',
                              overflow: 'hidden',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                              <div
                                style={{
                                  width: 40, height: 40, borderRadius: 10,
                                  background: 'rgba(99,102,241,0.12)',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  flexShrink: 0,
                                }}
                              >
                                <Icon size={20} strokeWidth={1.5} style={{ color: '#A5B4FC' }} />
                              </div>
                              <button
                                onClick={() => togglePlanningModule(mod.id, false)}
                                title="Remove from selection"
                                aria-label={`Remove ${mod.label}`}
                                style={{
                                  width: 24, height: 24, borderRadius: 6,
                                  background: 'var(--primary)',
                                  border: 'none',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  cursor: 'pointer',
                                  flexShrink: 0,
                                  transition: 'background 120ms',
                                }}
                                onMouseEnter={e => (e.currentTarget.style.background = '#4338ca')}
                                onMouseLeave={e => (e.currentTarget.style.background = 'var(--primary)')}
                              >
                                <Check size={13} strokeWidth={3} color="white" />
                              </button>
                            </div>
                            <div style={{ minWidth: 0 }}>
                              <h4
                                style={{
                                  fontSize: 14, fontWeight: 600, color: 'white',
                                  margin: 0, marginBottom: 6,
                                  lineHeight: 1.35,
                                  wordBreak: 'break-word',
                                  overflowWrap: 'break-word',
                                }}
                              >
                                {mod.label}
                              </h4>
                              <p
                                style={{
                                  fontSize: 12.5, lineHeight: 1.55,
                                  margin: 0,
                                  color: 'var(--text-3)',
                                  wordBreak: 'break-word',
                                  overflowWrap: 'break-word',
                                }}
                              >
                                {mod.description}
                              </p>
                            </div>
                          </motion.div>
                        )
                      })}
                    </AnimatePresence>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ───────── Bottom prompt bar — mirrors the Coding phase's PromptInput ───────── */}
      <div
        className="flex-shrink-0 border-t"
        style={{
          background: 'var(--bg-panel)',
          borderColor: 'var(--border)',
          padding: '14px 24px 16px',
        }}
      >
        <div className="max-w-[1400px] mx-auto flex flex-col gap-3">
          {/* Project title + description combined bar */}
          <div
            className="flex flex-col gap-0 rounded-xl overflow-hidden"
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              transition: 'border-color 150ms',
            }}
            onFocusCapture={() => { /* keeps focus ring logic minimal */ }}
          >
            {/* Project Title row */}
            <div
              className="flex items-center gap-3"
              style={{
                padding: '0 14px',
                height: 46,
                borderBottom: projectTitle || (document.activeElement === titleRef.current)
                  ? '1px solid var(--border)'
                  : '1px solid transparent',
              }}
            >
              <FolderKanban size={16} strokeWidth={1.75} style={{ color: 'var(--primary)', flexShrink: 0 }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', flexShrink: 0 }}>
                Project Title
              </span>
              <input
                ref={titleRef}
                type="text"
                value={projectTitle}
                onChange={e => setProjectTitle(e.target.value)}
                placeholder="e.g. Calculator App, REST API for Tasks, E-commerce Website…"
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  fontSize: 13,
                  color: 'var(--text-1)',
                  fontFamily: 'inherit',
                  minWidth: 0,
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    descRef.current?.focus()
                  }
                }}
              />
              {projectTitle.trim() && (
                <span style={{ fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>
                  {projectTitle.trim().length} chars
                </span>
              )}
            </div>

            {/* Description row */}
            <div
              className="flex items-start gap-3"
              style={{
                padding: '10px 14px',
                minHeight: 70,
              }}
            >
              <Paperclip size={16} strokeWidth={1.75} style={{ color: 'var(--text-3)', flexShrink: 0, marginTop: 4 }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', flexShrink: 0, marginTop: 4 }}>
                Description
              </span>
              <textarea
                ref={descRef}
                value={promptText}
                onChange={e => {
                  setPromptText(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
                }}
                placeholder="Describe your project, the architecture you prefer, and specific requirements to guide the Planning Agent… (Enter for newline, click Send to submit)"
                rows={2}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  fontSize: 13,
                  color: 'var(--text-1)',
                  resize: 'none',
                  fontFamily: 'inherit',
                  lineHeight: 1.55,
                  minHeight: 44,
                  maxHeight: 140,
                  minWidth: 0,
                  padding: 0,
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault()
                    handleGenerate()
                  }
                }}
              />
            </div>

            {/* Action row */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 16,
                padding: '10px 14px',
                borderTop: '1px solid var(--border)',
                background: 'rgba(0,0,0,0.18)',
                minHeight: 60,
                flexWrap: 'nowrap',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                <Sparkles size={14} strokeWidth={2} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-1)', letterSpacing: '0.02em', lineHeight: 1.3 }}>
                    {canSubmit
                      ? `Ready to plan with ${selectedCount} component${selectedCount === 1 ? '' : 's'}`
                      : !anySelected
                        ? 'Select at least one planning component'
                        : !projectTitle.trim()
                          ? 'Enter a project title'
                          : 'Describe your project'}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4, marginTop: 2 }}>
                    The Planning Agent will generate the selected components before code generation.
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, alignSelf: 'center' }}>
                <button
                  type="button"
                  aria-label="Voice input"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    background: 'transparent',
                    color: 'var(--text-3)',
                    flexShrink: 0,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 150ms',
                    border: '1px solid var(--border)',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.color = 'var(--text-1)'
                    e.currentTarget.style.borderColor = 'rgba(99,102,241,0.45)'
                    e.currentTarget.style.background = 'var(--bg-input)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.color = 'var(--text-3)'
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <Mic size={15} strokeWidth={1.75} />
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={!canSubmit}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    height: 36,
                    minWidth: 150,
                    padding: '0 18px',
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    letterSpacing: '0.01em',
                    background: canSubmit ? 'var(--primary)' : 'var(--bg-card)',
                    color: canSubmit ? 'white' : 'var(--text-3)',
                    cursor: canSubmit ? 'pointer' : 'not-allowed',
                    border: 'none',
                    boxShadow: canSubmit ? '0 4px 14px rgba(99,102,241,0.32)' : 'none',
                    opacity: canSubmit ? 1 : 0.6,
                    flexShrink: 0,
                    alignSelf: 'center',
                    whiteSpace: 'nowrap',
                    transition: 'all 150ms',
                  }}
                  onMouseEnter={e => {
                    if (canSubmit) e.currentTarget.style.background = '#4f46e5'
                  }}
                  onMouseLeave={e => {
                    if (canSubmit) e.currentTarget.style.background = 'var(--primary)'
                  }}
                >
                  <Send size={14} strokeWidth={2} />
                  Generate Plan
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px]" style={{ color: 'var(--text-3)' }}>
            <span>Tip: press <kbd style={{ padding: '1px 6px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4, fontFamily: 'monospace' }}>Ctrl</kbd> + <kbd style={{ padding: '1px 6px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4, fontFamily: 'monospace' }}>Enter</kbd> to submit.</span>
            <span>{selectedCount} / {totalCount} planning components selected</span>
          </div>
        </div>
      </div>
    </motion.div>
  )
}