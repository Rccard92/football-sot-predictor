import type { DrawCredibilityExclusionReason } from '../../lib/cecchinoDrawCredibilityResearchApi'

const REASON_LABELS: Record<string, string> = {
  not_finished: 'Partita non conclusa',
  missing_fulltime_result: 'Risultato FT mancante',
  unsupported_payload_version: 'Payload Cecchino non supportato',
  missing_cecchino_final: 'Final Cecchino non disponibile',
  missing_cecchino_1x2_odds: 'Quote Cecchino 1/X/2 mancanti',
  missing_cecchino_1x2_probabilities: 'Probabilità Cecchino 1/X/2 mancanti',
  missing_cecchino_under_2_5: 'Under 2.5 Cecchino mancante',
  missing_cecchino_over_2_5: 'Over 2.5 Cecchino mancante',
  missing_book_1x2: 'Book 1/X/2 mancante',
  missing_book_under_2_5: 'Book Under 2.5 mancante',
  missing_book_over_2_5: 'Book Over 2.5 mancante',
  invalid_numeric_value: 'Valore numerico non valido',
}

type Props = {
  reasons: DrawCredibilityExclusionReason[]
}

export function DrawCredibilityExclusionTable({ reasons }: Props) {
  const rows = reasons.filter((r) => r.count > 0)
  if (rows.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Problemi dati</h2>
        <p className="mt-2 text-sm text-slate-500">Nessun motivo di esclusione registrato.</p>
      </section>
    )
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Problemi dati</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Motivo</th>
              <th className="px-4 py-2 font-medium">Conteggio</th>
              <th className="px-4 py-2 font-medium">% totale</th>
              <th className="px-4 py-2 font-medium">% concluse</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.reason} className="border-t border-slate-100">
                <td className="px-4 py-2 text-slate-800">
                  {REASON_LABELS[row.reason] ?? row.reason}
                </td>
                <td className="px-4 py-2 tabular-nums">{row.count}</td>
                <td className="px-4 py-2 tabular-nums">{row.pct_total.toFixed(2)}%</td>
                <td className="px-4 py-2 tabular-nums">{row.pct_finished.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
