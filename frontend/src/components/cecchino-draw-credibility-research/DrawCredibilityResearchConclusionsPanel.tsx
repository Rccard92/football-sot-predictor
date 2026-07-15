import type { DrawCredibilityResearchConclusions } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  conclusions: DrawCredibilityResearchConclusions
  nextPhaseRecommendations?: DrawCredibilityResearchConclusions['next_phase_feature_recommendations']
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null
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

export function DrawCredibilityResearchConclusionsPanel({
  conclusions,
  nextPhaseRecommendations,
}: Props) {
  const modest = conclusions.modest_candidates ?? []
  const redundantGroups = conclusions.redundant_groups ?? []
  const recommended = conclusions.recommended_representatives ?? []
  const nextRecs =
    nextPhaseRecommendations ??
    conclusions.next_phase_feature_recommendations ??
    []
  const unstable = conclusions.unstable_features ?? []

  return (
    <section className="rounded-2xl border border-violet-200/80 bg-violet-50/30 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-violet-900">Conclusioni esplorative</h3>
      <p className="mb-3 text-xs text-violet-800">
        Derivate dalle metriche calcolate — non modificano il modello produttivo.
      </p>

      <div className="mb-4 grid gap-4 sm:grid-cols-2">
        <ListBlock title="Potenzialmente utili" items={conclusions.potentially_useful ?? []} />
        <ListBlock title="Candidati modest" items={modest} />
        <ListBlock title="Deboli o incerte" items={conclusions.weak_or_uncertain ?? []} />
        <ListBlock title="Non lineari" items={conclusions.non_linear_candidates ?? []} />
        <ListBlock title="Feature instabili (Prim/Sens)" items={unstable} />
        <ListBlock
          title="Interazioni candidate"
          items={conclusions.candidate_interactions ?? []}
        />
        <ListBlock title="Serve più storia" items={conclusions.requires_more_history ?? []} />
        <ListBlock title="Prossima fase (nome)" items={conclusions.next_phase_features ?? []} />
      </div>

      {redundantGroups.length > 0 ? (
        <div className="mb-4">
          <p className="mb-1 text-xs font-semibold text-slate-700">Gruppi ridondanti</p>
          <ul className="space-y-1 text-xs text-slate-600">
            {redundantGroups.map((g, i) => (
              <li key={i} className="rounded-lg border border-violet-100 bg-white/60 px-2 py-1.5">
                {(g.features ?? []).join(' ↔ ')}
                {g.level ? ` · ${g.level}` : ''}
                {typeof g.pearson === 'number' ? ` · r=${g.pearson.toFixed(3)}` : ''}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {recommended.length > 0 ? (
        <div className="mb-4">
          <p className="mb-1 text-xs font-semibold text-slate-700">Rappresentanti raccomandati</p>
          <ul className="space-y-1 text-xs text-slate-600">
            {recommended.map((r) => (
              <li key={r.family} className="rounded-lg border border-violet-100 bg-white/60 px-2 py-1.5">
                <span className="font-medium text-slate-800">{r.family}</span>: {r.representative}
                {r.note ? ` — ${r.note}` : ''}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {nextRecs.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-700">
            Raccomandazioni feature prossima fase
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="border-b border-violet-200 text-violet-800/80">
                <tr>
                  <th className="px-2 py-2 text-left">Feature</th>
                  <th className="px-2 py-2 text-left">Motivo</th>
                  <th className="px-2 py-2 text-left">Forma preferita</th>
                </tr>
              </thead>
              <tbody>
                {nextRecs.map((r) => (
                  <tr key={r.feature} className="border-b border-violet-100/80">
                    <td className="px-2 py-1.5 font-medium text-slate-800">{r.feature}</td>
                    <td className="px-2 py-1.5 text-slate-600">{r.reason}</td>
                    <td className="px-2 py-1.5">{r.preferred_form}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}
