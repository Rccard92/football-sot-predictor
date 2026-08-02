type Props = { rows?: number; className?: string }

export function HistoricalKpiSkeleton({ rows = 3, className = '' }: Props) {
  return (
    <div className={`space-y-3 animate-pulse ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-16 rounded-lg"
          style={{ background: 'var(--lab-surface-2)' }}
        />
      ))}
    </div>
  )
}
