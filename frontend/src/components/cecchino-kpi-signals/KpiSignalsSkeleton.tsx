function Shimmer({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 bg-[length:200%_100%] ${className ?? ''}`}
    />
  )
}

export function KpiSignalsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Shimmer key={i} className="h-44 rounded-2xl" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 10 }).map((_, i) => (
          <Shimmer key={i} className="h-20 rounded-xl" />
        ))}
      </div>
      <Shimmer className="h-80 rounded-2xl" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Shimmer className="h-64 rounded-2xl" />
        <Shimmer className="h-64 rounded-2xl" />
        <Shimmer className="h-64 rounded-2xl" />
      </div>
      <Shimmer className="h-96 rounded-2xl" />
    </div>
  )
}
