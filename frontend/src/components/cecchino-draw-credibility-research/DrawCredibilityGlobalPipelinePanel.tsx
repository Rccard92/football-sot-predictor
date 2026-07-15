import type { GlobalPipelineSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  pipeline: GlobalPipelineSummary
}

const METRICS: Array<{ key: keyof GlobalPipelineSummary; label: string }> = [
  { key: 'raw_database_rows', label: 'Righe DB' },
  { key: 'unique_provider_fixtures', label: 'Fixture globali uniche' },
  { key: 'global_duplicates_collapsed', label: 'Duplicati globali' },
  { key: 'groups_with_built_row', label: 'Gruppi con riga dataset' },
  { key: 'groups_excluded', label: 'Gruppi esclusi' },
  { key: 'all_internal_safe_rows', label: 'Righe interne safe' },
]

export function DrawCredibilityGlobalPipelinePanel({ pipeline }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Universo storico globale</h3>
      <p className="mt-1 text-xs text-slate-500">
        Metriche sull&apos;intero range DB prima del filtro coorte selezionata.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {METRICS.map(({ key, label }) => (
          <div key={key} className="rounded-xl border border-slate-100 bg-white px-3 py-3 shadow-sm">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{pipeline[key]}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
