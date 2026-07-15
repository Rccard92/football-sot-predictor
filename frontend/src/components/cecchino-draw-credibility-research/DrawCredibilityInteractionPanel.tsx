type Props = {
  interactions: Array<Record<string, unknown>>
  categorical: Array<Record<string, unknown>>
}

export function DrawCredibilityInteractionPanel({ interactions, categorical }: Props) {
  const fallback = categorical.slice(0, 3)
  const rows = interactions.length > 0 ? interactions : fallback

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Interazioni / categorie</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">Nessuna interazione calcolata su questo campione.</p>
      ) : (
        <div className="space-y-3">
          {rows.map((block, idx) => {
            const cats = (block.categories as Array<Record<string, unknown>>) ?? []
            const title = String(block.feature ?? block.pattern ?? `Blocco ${idx + 1}`)
            return (
              <div key={title}>
                <p className="mb-1 text-xs font-medium text-slate-700">{title}</p>
                <table className="min-w-full text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="py-1 pr-2">Categoria</th>
                      <th className="py-1 pr-2">N</th>
                      <th className="py-1 pr-2">Draw %</th>
                      <th className="py-1">Lift pp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cats.slice(0, 8).map((c) => (
                      <tr key={String(c.category)} className="border-t border-slate-100">
                        <td className="py-1 pr-2">{String(c.category)}</td>
                        <td className="py-1 pr-2 tabular-nums">{String(c.count)}</td>
                        <td className="py-1 pr-2 tabular-nums">
                          {typeof c.draw_rate_pct === 'number' ? c.draw_rate_pct.toFixed(1) : '—'}
                        </td>
                        <td className="py-1 tabular-nums">
                          {typeof c.lift_vs_baseline_pp === 'number'
                            ? c.lift_vs_baseline_pp.toFixed(1)
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
