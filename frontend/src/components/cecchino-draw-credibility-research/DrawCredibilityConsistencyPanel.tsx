import type { CohortConsistencyRow, DrawCredibilityDatasetResponse } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  rows: CohortConsistencyRow[]
  checks?: DrawCredibilityDatasetResponse['consistency_checks']
}

export function DrawCredibilityConsistencyPanel({ rows, checks }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Consistenza vs audit 1A</h3>
      {checks?.difference_reason ? (
        <p className="mt-1 text-xs text-slate-500">{checks.difference_reason}</p>
      ) : null}
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Coorte</th>
              <th className="px-3 py-2 font-medium">Audit atteso</th>
              <th className="px-3 py-2 font-medium">Candidati row-level</th>
              <th className="px-3 py-2 font-medium">Uniche dedup</th>
              <th className="px-3 py-2 font-medium">Dup. rimossi</th>
              <th className="px-3 py-2 font-medium">Finale</th>
              <th className="px-3 py-2 font-medium">Delta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.cohort} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{row.label}</td>
                <td className="px-3 py-2 tabular-nums">{row.expected_from_audit}</td>
                <td className="px-3 py-2 tabular-nums">{row.row_level_candidates}</td>
                <td className="px-3 py-2 tabular-nums">{row.unique_after_dedup}</td>
                <td className="px-3 py-2 tabular-nums">{row.duplicates_removed_within_cohort}</td>
                <td className="px-3 py-2 tabular-nums">{row.final_dataset_rows}</td>
                <td
                  className={`px-3 py-2 tabular-nums ${
                    row.delta_vs_audit === 0 ? 'text-emerald-700' : 'text-amber-700'
                  }`}
                >
                  {row.delta_vs_audit > 0 ? '+' : ''}
                  {row.delta_vs_audit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 space-y-1">
        {rows.map((row) => (
          <p key={`${row.cohort}-exp`} className="text-xs text-slate-600">
            {row.explanation}
          </p>
        ))}
      </div>
    </section>
  )
}
