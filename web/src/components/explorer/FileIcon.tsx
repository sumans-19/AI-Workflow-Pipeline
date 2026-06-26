import {
  FileText, FileCode, FileJson, FileType, File,
  FileImage, FileTerminal
} from 'lucide-react'

interface Props { filename: string; size?: number }

const EXT_MAP: Record<string, { icon: React.ElementType; color: string }> = {
  py:   { icon: FileCode,     color: '#3B82F6' },
  ts:   { icon: FileCode,     color: '#6366F1' },
  tsx:  { icon: FileCode,     color: '#8B5CF6' },
  js:   { icon: FileCode,     color: '#F59E0B' },
  jsx:  { icon: FileCode,     color: '#F59E0B' },
  json: { icon: FileJson,     color: '#10B981' },
  md:   { icon: FileText,     color: '#94A3B8' },
  toml: { icon: FileType,     color: '#94A3B8' },
  yaml: { icon: FileType,     color: '#94A3B8' },
  yml:  { icon: FileType,     color: '#94A3B8' },
  css:  { icon: FileCode,     color: '#EC4899' },
  html: { icon: FileCode,     color: '#F97316' },
  sh:   { icon: FileTerminal, color: '#22C55E' },
  svg:  { icon: FileImage,    color: '#6366F1' },
  txt:  { icon: FileText,     color: '#64748B' },
}

export default function FileIcon({ filename, size = 14 }: Props) {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const { icon: Icon, color } = EXT_MAP[ext] ?? { icon: File, color: '#64748B' }
  return <Icon size={size} strokeWidth={1.75} style={{ color, flexShrink: 0 }} />
}
