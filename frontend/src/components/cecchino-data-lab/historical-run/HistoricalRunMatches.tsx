import type { HistoricalRunMatchRow } from '../../../lib/cecchinoLabApi'

type Props = {
  items: HistoricalRunMatchRow[]
  total: number
  offset: number
  limit: number
  onPage: (offset: number) => void
  onOpen: (snapshotId: number) => void
}

export function HistoricalRunMatches({
  items,
  total,
  offset,
  limit,
  onPage,
  onOpen,
}: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Match Explorer</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        {total} partite · pagina {Math.floor(offset / limit) + 1}
      </p>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Data</th>
              <th>Campionato</th>
              <th>Partita</th>
              <th>Elig.</th>
              <th>Rating max</th>
              <th>Segnali</th>
              <th>Balance</th>
              <th>Quote</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr
                key={m.snapshot_id}
                className="cursor-pointer hover:bg-white/5"
                onClick={() => onOpen(m.snapshot_id)}
              >
                <td>{m.date?.slice(0, 10) ?? '—'}</td>
                <td>{m.competition}</td>
                <td>
                  {m.home_team} vs {m.away_team}
                </td>
                <td>{m.eligibility}</td>
                <td>
                  {m.highest_rating_market ?? '—'} {m.highest_rating ?? ''}
                </td>
                <td>{m.active_signal_models.join(',') || '—'}</td>
                <td>{m.balance_class}</td>
                <td>
                  R{m.quote_coverage.real}/D{m.quote_coverage.derived}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="lab-btn text-xs"
          disabled={offset <= 0}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Precedente
        </button>
        <button
          type="button"
          className="lab-btn text-xs"
          disabled={offset + limit >= total}
          onClick={() => onPage(offset + limit)}
        >
          Successiva
        </button>
      </div>
    </section>
  )
}
