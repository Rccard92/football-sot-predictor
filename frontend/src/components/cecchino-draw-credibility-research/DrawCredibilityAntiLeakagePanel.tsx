import type { CohortAntiLeakage } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  selected: CohortAntiLeakage
  globalStats?: CohortAntiLeakage
}

export function DrawCredibilityAntiLeakagePanel({ selected, globalStats }: Props) {
  const selectedItems = [
    { label: 'Safe (incluse)', value: selected.safe, tone: 'text-emerald-700 bg-emerald-50' },
    { label: 'Unknown', value: selected.unknown, tone: 'text-amber-700 bg-amber-50' },
    { label: 'Unsafe', value: selected.unsafe, tone: 'text-rose-700 bg-rose-50' },
    {
      label: 'Senza snapshot pre-match',
      value: selected.excluded_no_pre_match_snapshot,
      tone: 'text-slate-700 bg-slate-50',
    },
  ]

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Anti-leakage — coorte selezionata</h3>
      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {selectedItems.map((item) => (
          <div key={item.label} className={`rounded-xl px-3 py-3 ${item.tone}`}>
            <p className="text-[10px] font-medium uppercase tracking-wide opacity-80">{item.label}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums">{item.value}</p>
          </div>
        ))}
      </div>

      {globalStats ? (
        <details className="mt-4 rounded-lg border border-slate-100 bg-slate-50/50 p-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">
            Anti-leakage — universo storico compatibile
          </summary>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Safe globali</dt>
              <dd className="font-semibold tabular-nums">{globalStats.safe}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Unknown</dt>
              <dd className="font-semibold tabular-nums">{globalStats.unknown}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Unsafe</dt>
              <dd className="font-semibold tabular-nums">{globalStats.unsafe}</dd>
            </div>
            <div>
              <dt className="text-slate-500">No snapshot</dt>
              <dd className="font-semibold tabular-nums">{globalStats.excluded_no_pre_match_snapshot}</dd>
            </div>
          </dl>
        </details>
      ) : null}
    </section>
  )
}
