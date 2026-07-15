export function DrawCredibilityResearchSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl bg-slate-200/70" />
        ))}
      </div>
      <div className="h-48 rounded-2xl bg-slate-200/70" />
      <div className="h-40 rounded-2xl bg-slate-200/70" />
    </div>
  )
}
