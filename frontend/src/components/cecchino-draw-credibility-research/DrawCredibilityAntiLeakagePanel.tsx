type Props = {
  safe: number
  unknown: number
  unsafe: number
  excludedNoPreMatch: number
}

export function DrawCredibilityAntiLeakagePanel({
  safe,
  unknown,
  unsafe,
  excludedNoPreMatch,
}: Props) {
  const items = [
    { label: 'Safe (inclusi nel dataset)', value: safe, tone: 'text-emerald-700 bg-emerald-50' },
    { label: 'Unknown (esclusi)', value: unknown, tone: 'text-amber-700 bg-amber-50' },
    { label: 'Unsafe (esclusi)', value: unsafe, tone: 'text-rose-700 bg-rose-50' },
    {
      label: 'Senza snapshot pre-match',
      value: excludedNoPreMatch,
      tone: 'text-slate-700 bg-slate-50',
    },
  ]

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Anti-leakage</h3>
      <p className="mt-1 text-xs text-slate-500">
        Solo righe con leakage <code className="rounded bg-slate-100 px-1">safe</code> entrano nelle coorti
        del dataset.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className={`rounded-xl px-3 py-3 ${item.tone}`}>
            <p className="text-[10px] font-medium uppercase tracking-wide opacity-80">{item.label}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums">{item.value}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
