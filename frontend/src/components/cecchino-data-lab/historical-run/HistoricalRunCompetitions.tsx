import type { HistoricalRunCompetitionAnalytics } from '../../../lib/cecchinoLabApi'

type Props = {
  competitions: HistoricalRunCompetitionAnalytics[]
  onSelect: (competition: string) => void
}

export function HistoricalRunCompetitions({ competitions, onSelect }: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">League DNA</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Confronto campionati. Nessun profitto globale del campionato. Click = filtro globale.
      </p>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Campionato</th>
              <th>Proc.</th>
              <th>Elig.</th>
              <th>Escl.</th>
              <th>Cov.</th>
              <th>Quote reali</th>
              <th>Best ROI</th>
              <th>Worst ROI</th>
            </tr>
          </thead>
          <tbody>
            {competitions.map((c) => (
              <tr
                key={c.competition_name}
                className="cursor-pointer hover:bg-white/5"
                onClick={() => onSelect(c.competition_name)}
              >
                <td className="text-[var(--lab-cyan)] underline-offset-2 hover:underline">
                  {c.competition_name}
                </td>
                <td>{c.processed}</td>
                <td>{c.eligible}</td>
                <td>{c.excluded}</td>
                <td>{c.coverage_pct}%</td>
                <td>{c.real_quote_coverage}%</td>
                <td>{c.best_market_by_real_roi ?? '—'}</td>
                <td>{c.worst_market_by_real_roi ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
