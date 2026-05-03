import type { ReactNode } from 'react'

type CardProps = {
  title?: string
  children: ReactNode
  className?: string
}

export function Card({ title, children, className = '' }: CardProps) {
  return (
    <div
      className={`rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm ${className}`}
    >
      {title ? (
        <h2 className="mb-3 text-lg font-semibold text-slate-900">{title}</h2>
      ) : null}
      <div className="text-slate-600">{children}</div>
    </div>
  )
}
