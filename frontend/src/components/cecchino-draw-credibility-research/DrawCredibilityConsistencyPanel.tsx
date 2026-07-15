import type { DrawCredibilityDatasetResponse } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  checks: DrawCredibilityDatasetResponse['consistency_checks']
}

export function DrawCredibilityConsistencyPanel({ checks }: Props) {
  const rows = [
    {
      label: 'Primary',
      expected: checks.expected_primary_from_audit,
      actual: checks.actual_primary_rows,
      diff: checks.difference_primary_vs_audit,
    },
    {
      label: 'Sensitivity',
      expected: checks.expected_sensitivity_from_audit,
      actual: checks.actual_sensitivity_rows,
      diff: checks.difference_sensitivity_vs_audit,
    },
    {
      label: 'Market',
      expected: checks.expected_market_from_audit,
      actual: checks.actual_market_rows,
      diff: checks.difference_market_vs_audit,
    },
  ]

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Consistenza vs audit 1A</h3>
      <p className="mt-1 text-xs text-slate-500">{checks.difference_reason}</p>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Coorte</th>
              <th className="px-3 py-2 font-medium">Atteso audit</th>
              <th className="px-3 py-2 font-medium">Dataset reale</th>
              <th className="px-3 py-2 font-medium">Delta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{row.label}</td>
                <td className="px-3 py-2 tabular-nums">{row.expected}</td>
                <td className="px-3 py-2 tabular-nums">{row.actual}</td>
                <td
                  className={`px-3 py-2 tabular-nums ${
                    row.diff === 0 ? 'text-emerald-700' : 'text-amber-700'
                  }`}
                >
                  {row.diff > 0 ? '+' : ''}
                  {row.diff}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <dt className="text-slate-500">Duplicati rimossi</dt>
          <dd className="font-semibold tabular-nums">{checks.duplicates_removed}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <dt className="text-slate-500">Leakage rimossi</dt>
          <dd className="font-semibold tabular-nums">{checks.leakage_removed}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <dt className="text-slate-500">Versioni legacy</dt>
          <dd className="font-semibold tabular-nums">{checks.version_removed}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <dt className="text-slate-500">Feature invalide</dt>
          <dd className="font-semibold tabular-nums">{checks.invalid_features_removed}</dd>
        </div>
      </dl>
    </section>
  )
}
