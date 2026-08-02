import type { HistoricalKpiActivationRow } from '../../../lib/cecchinoLabApi'
import { formatOdds, formatProfit, roiColorClass } from './historicalKpiUtils'

type Props = {
  items: HistoricalKpiActivationRow[]
  total: number
  offset: number
  limit?: number
  onRowClick: (row: HistoricalKpiActivationRow) => void
  onPage: (offset: number) => void
}

function evaluationLabel(status: string | null): string {
  switch (status) {
    case 'won':
      return 'Vinto'
    case 'lost':
      return 'Perso'
    case 'settled':
      return 'Regolato'
    case 'pending':
      return 'In attesa'
    case 'void':
      return 'Void'
    default:
      return status ?? '—'
  }
}

export function HistoricalKpiActivationsTable({
  items,
  total,
  offset,
  limit = 50,
  onRowClick,
  onPage,
}: Props) {
  const page = Math.floor(offset / limit) + 1
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const canPrev = offset > 0
  const canNext = offset + limit < total

  return (
    <section data-testid="historical-kpi-activations">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">Attivazioni segnali</h3>
        <div className="text-xs text-[var(--lab-muted)]">
          {total} totali · pagina {page}/{totalPages} · {limit} per pagina
        </div>
      </div>
      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Kickoff</th>
              <th>Partita</th>
              <th>Campionato</th>
              <th>Mercato</th>
              <th>Rating</th>
              <th>Fascia</th>
              <th>Quota</th>
              <th>Tipo</th>
              <th>Esito</th>
              <th>Profitto</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-[var(--lab-muted)]">
                  Nessuna attivazione per i filtri correnti.
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr
                  key={`${row.source_snapshot_id}-${row.market_key}-${row.quote_type}`}
                  className="cursor-pointer"
                  onClick={() => onRowClick(row)}
                >
                  <td>{row.kickoff_at?.slice(0, 16).replace('T', ' ') ?? '—'}</td>
                  <td>
                    {row.home_team ?? '—'} — {row.away_team ?? '—'}
                  </td>
                  <td>{row.competition_name ?? '—'}</td>
                  <td>{row.market_label || row.market_key}</td>
                  <td>{row.rating ?? '—'}</td>
                  <td>{row.rating_bucket ?? '—'}</td>
                  <td>{formatOdds(row.quota_book)}</td>
                  <td>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        row.quote_type === 'real' ? 'lab-quote-real' : 'lab-quote-derived'
                      }`}
                    >
                      {row.quote_type === 'real' ? 'Reale' : 'Derivata'}
                    </span>
                  </td>
                  <td>{evaluationLabel(row.evaluation_status)}</td>
                  <td className={roiColorClass(row.profit_units)}>
                    {formatProfit(row.profit_units)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          className="lab-btn-ghost text-xs"
          disabled={!canPrev}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Precedente
        </button>
        <button
          type="button"
          className="lab-btn-ghost text-xs"
          disabled={!canNext}
          onClick={() => onPage(offset + limit)}
        >
          Successiva
        </button>
      </div>
    </section>
  )
}
