type Props = {
  conclusions: {
    potentially_useful: string[]
    weak_or_uncertain: string[]
    redundant: string[]
    non_linear_candidates: string[]
    requires_more_history: string[]
    next_phase_features: string[]
  }
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <p className="text-xs font-semibold text-slate-700">{title}</p>
      <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

export function DrawCredibilityResearchConclusionsPanel({ conclusions }: Props) {
  return (
    <section className="rounded-2xl border border-violet-200/80 bg-violet-50/30 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-violet-900">Conclusioni esplorative</h3>
      <p className="mb-3 text-xs text-violet-800">
        Derivate dalle metriche calcolate — non modificano il modello produttivo.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <ListBlock title="Potenzialmente utili" items={conclusions.potentially_useful} />
        <ListBlock title="Deboli o incerte" items={conclusions.weak_or_uncertain} />
        <ListBlock title="Ridondanti" items={conclusions.redundant} />
        <ListBlock title="Non lineari" items={conclusions.non_linear_candidates} />
        <ListBlock title="Serve più storia" items={conclusions.requires_more_history} />
        <ListBlock title="Prossima fase" items={conclusions.next_phase_features} />
      </div>
    </section>
  )
}
