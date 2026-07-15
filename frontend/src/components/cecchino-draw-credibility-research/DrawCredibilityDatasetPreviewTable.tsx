import type { DrawCredibilityDatasetRow } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  rows: DrawCredibilityDatasetRow[]
  page: number
  totalPages: number
  totalRows: number
  onPageChange: (page: number) => void
}

const COLUMNS: Array<{ key: keyof DrawCredibilityDatasetRow; label: string }> = [
  { key: 'provider_fixture_id', label: 'Fixture' },
  { key: 'league_name', label: 'Lega' },
  { key: 'home_team_name', label: 'Casa' },
  { key: 'away_team_name', label: 'Trasferta' },
  { key: 'ft_score', label: 'FT' },
  { key: 'result_1x2', label: '1X2' },
  { key: 'draw_ft', label: 'Draw' },
  { key: 'prob_x_norm', label: 'P(X) norm' },
  { key: 'x_rank', label: 'X rank' },
  { key: 'f36_score_existing', label: 'F36' },
  { key: 'dominance_pp', label: 'Dom pp' },
  { key: 'conviction_index_candidate', label: 'Conviction' },
  { key: 'gap_coherence_index_candidate', label: 'Gap coh.' },
  { key: 'deviation_x_pp', label: 'Dev X pp' },
  { key: 'leakage_status', label: 'Leakage' },
]

function cellValue(row: DrawCredibilityDatasetRow, key: keyof DrawCredibilityDatasetRow): string {
  const v = row[key]
  if (v == null) return '—'
  if (typeof v === 'boolean') return v ? 'sì' : 'no'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v)
}

export function DrawCredibilityDatasetPreviewTable({
  rows,
  page,
  totalPages,
  totalRows,
  onPageChange,
}: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">Anteprima dataset</h3>
        <p className="text-xs text-slate-500">
          Pagina {page} / {totalPages} · {totalRows} righe totali
        </p>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {COLUMNS.map((col) => (
                <th key={col.key} className="whitespace-nowrap px-2 py-2 font-medium">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-6 text-center text-slate-500">
                  Nessuna riga da mostrare.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${row.provider_fixture_id}-${row.today_fixture_id_feature}`} className="border-t border-slate-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="whitespace-nowrap px-2 py-1.5 tabular-nums">
                      {cellValue(row, col.key)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 ? (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="rounded border border-slate-200 px-2 py-1 text-xs disabled:opacity-40"
          >
            Precedente
          </button>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="rounded border border-slate-200 px-2 py-1 text-xs disabled:opacity-40"
          >
            Successiva
          </button>
        </div>
      ) : null}
    </section>
  )
}
