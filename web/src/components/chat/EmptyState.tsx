import { motion } from 'framer-motion'

interface Props { onPrompt: (p: string) => void }


export default function EmptyState({ onPrompt }: Props) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-8" style={{ maxWidth: 800, margin: '0 auto', width: '100%' }}>
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="flex flex-col items-center text-center mb-12"
      >

        <h1
          className="gradient-text font-bold mb-3"
          style={{ fontSize: 28, letterSpacing: '-0.02em', lineHeight: 1.2 }}
        >
          AI Development Platform
        </h1>
        <p style={{ fontSize: 15, color: 'var(--text-2)', maxWidth: 420, lineHeight: 1.7 }}>
          Describe what you want to build. The AI will generate code,
          run tests, and review quality — all inside this interface.
        </p>
      </motion.div>


    </div>
  )
}

