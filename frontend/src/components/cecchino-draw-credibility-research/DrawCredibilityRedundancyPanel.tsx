type Props = {
  redundancy: {
    pairs: Array<Record<string, unknown>>
    candidate_groups: Array<{ features: string[]; expected: boolean }>
  }
}

export function DrawCredibilityRedundancyPanel({ redundancy }: Props) {
  const highPairs = redundancy.pairs.filter(
    (p) => p.redundancy_level === 'high' || p.redundancy_level === 'very_high',
  )

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Ridondanza feature</h3>
      <p className="mb-2 text-xs text-slate-600">
        Coppie ad alta correlazione ({highPairs.length} su {redundancy.pairs.length})
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">A</th>
              <th className="py-1 pr-2">B</th>
              <th className="py-1 pr-2">Pearson</th>
              <th className="py-1 pr-2">Spearman</th>
              <th className="py-1">Livello</th>
            </tr>
          </thead>
          <tbody>
            {highPairs.slice(0, 15).map((p) => (
              <tr key={`${String(p.feature_a)}-${String(p.feature_b)}`} className="border-t border-slate-100">
                <td className="py-1 pr-2">{String(p.feature_a)}</td>
                <td className="py-1 pr-2">{String(p.feature_b)}</td>
                <td className="py-1 pr-2 tabular-nums">{String(p.pearson)}</td>
                <td className="py-1 pr-2 tabular-nums">{String(p.spearman ?? '—')}</td>
                <td className="py-1">{String(p.redundancy_level)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3">
        <p className="text-xs font-medium text-slate-700">Gruppi attesi</p>
        <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">
          {redundancy.candidate_groups.map((g) => (
            <li key={g.features.join('+')}>{g.features.join(' ↔ ')}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}
