import { useState, type ReactNode } from 'react'

type Props = {
  title?: string
  text: string
  children?: ReactNode
}

/** Tooltip info accessibile minimale — stesso look MetricTooltip Lab. */
export function LabInfoTooltip({ title, text, children }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <span
      className="relative inline-flex items-center gap-1"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      <button
        type="button"
        aria-label={title || 'Informazioni'}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold"
        style={{
          background: 'var(--lab-cyan-dim)',
          color: 'var(--lab-cyan)',
          border: '1px solid var(--lab-border)',
        }}
      >
        i
      </button>
      {open ? (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-40 mt-2 w-72 rounded-lg px-3 py-2 text-xs leading-relaxed shadow-lg"
          style={{
            background: '#0f1c2c',
            border: '1px solid var(--lab-border)',
            color: 'var(--lab-text)',
          }}
        >
          {title ? (
            <div className="mb-1 font-semibold" style={{ color: 'var(--lab-cyan)' }}>
              {title}
            </div>
          ) : null}
          {text}
        </span>
      ) : null}
    </span>
  )
}
