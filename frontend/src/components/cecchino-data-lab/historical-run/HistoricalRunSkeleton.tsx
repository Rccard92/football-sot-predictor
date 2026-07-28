export function HistoricalRunSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3 animate-pulse">
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
