import type { CecchinoUpcomingFixtureRow } from '../../lib/cecchinoApi'
import {
  canShowFinalOdds,
  computeBestSideFromRow,
  fmtKickoff,
  fmtNum,
  fmtPct,
  hasLowSampleWarning,
  statusBadgeClass,
  statusLabel,
} from '../../lib/cecchinoUtils'

type Props = {
  fixtures: CecchinoUpcomingFixtureRow[]
  selectedFixtureId: number | null
  onSelect: (fixtureId: number) => void
  roundLabel?: string | null
}

export function CecchinoFixturesTable({
  fixtures,
  selectedFixtureId,
  onSelect,
  roundLabel,
}: Props) {
  if (fixtures.length === 0) {
    return (
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
        Nessuna partita upcoming per questo campionato. Seleziona un altro campionato o attendi il
        prossimo turno.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-800">
        Prossime partite{roundLabel ? ` · ${roundLabel}` : ''}
      </h2>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[960px] w-full text-left text-xs text-slate-700">
          <thead className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Data/ora</th>
              <th className="px-3 py-2">Casa</th>
              <th className="px-3 py-2">Trasferta</th>
              <th className="px-3 py-2">Stato</th>
              <th className="px-2 py-2 text-center">1</th>
              <th className="px-2 py-2 text-center">X</th>
              <th className="px-2 py-2 text-center">2</th>
              <th className="px-2 py-2 text-center">P% 1</th>
              <th className="px-2 py-2 text-center">P% X</th>
              <th className="px-2 py-2 text-center">P% 2</th>
              <th className="px-2 py-2 text-center">Best</th>
              <th className="px-3 py-2 text-right">Azione</th>
            </tr>
          </thead>
          <tbody>
            {fixtures.map((row) => {
              const id = row.fixture.fixture_id
              const selected = selectedFixtureId === id
              const showOdds = canShowFinalOdds(row.calculation_status)
              const best = computeBestSideFromRow(row)
              const lowSample = hasLowSampleWarning(row.warnings)

              return (
                <tr
                  key={id}
                  className={`border-t border-slate-100 ${selected ? 'bg-indigo-50' : 'hover:bg-slate-50/80'}`}
                >
                  <td className="px-3 py-2 whitespace-nowrap tabular-nums text-slate-600">
                    {fmtKickoff(row.fixture.kickoff_at)}
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-900">{row.fixture.home_team.name}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">{row.fixture.away_team.name}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${statusBadgeClass(row.calculation_status)}`}
                    >
                      {statusLabel(row.calculation_status)}
                      {lowSample && (
                        <span title="Campione basso" className="text-amber-700" aria-hidden>
                          ⚠
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums font-medium">
                    {showOdds ? fmtNum(row.final_quota_1) : '—'}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums font-medium">
                    {showOdds ? fmtNum(row.final_quota_x) : '—'}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums font-medium">
                    {showOdds ? fmtNum(row.final_quota_2) : '—'}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums">
                    {fmtPct(row.final_prob_1_pct)}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums">
                    {fmtPct(row.final_prob_x_pct)}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums">
                    {fmtPct(row.final_prob_2_pct)}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {best ? (
                      <span className="rounded bg-indigo-100 px-2 py-0.5 font-bold text-indigo-800">
                        {best}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => onSelect(id)}
                      className="rounded-md border border-indigo-300 bg-white px-2.5 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-50"
                    >
                      Dettaglio
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
