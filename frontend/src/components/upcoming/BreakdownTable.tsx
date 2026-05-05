import type { UpcomingCalculationBreakdown } from '../../lib/api'
import { formatNum } from './format'

const BREAKDOWN_ROWS: {
  key:
    | 'season_avg_sot_for'
    | 'opponent_season_avg_sot_conceded'
    | 'home_away_avg_sot_for'
    | 'opponent_home_away_avg_sot_conceded'
    | 'last5_avg_sot_for'
    | 'opponent_last5_avg_sot_conceded'
  label: string
}[] = [
  { key: 'season_avg_sot_for', label: 'Media stagionale tiri in porta' },
  { key: 'opponent_season_avg_sot_conceded', label: 'Tiri concessi dall’avversario (stagione)' },
  { key: 'home_away_avg_sot_for', label: 'Media in casa o in trasferta' },
  {
    key: 'opponent_home_away_avg_sot_conceded',
    label: 'Avversario concede in casa o in trasferta',
  },
  { key: 'last5_avg_sot_for', label: 'Forma recente (ultime 5 partite)' },
  { key: 'opponent_last5_avg_sot_conceded', label: 'Avversario ultime 5 partite (concesse)' },
]

export function BreakdownTable({
  teamName,
  breakdown,
}: {
  teamName: string
  breakdown: UpcomingCalculationBreakdown | null | undefined
}) {
  if (!breakdown) {
    return (
      <p className="text-sm text-slate-500">
        Dettaglio numerico non disponibile per {teamName}: rigenera le previsioni se la partita è stata creata con una
        versione precedente del sistema.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/90 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <th className="px-3 py-2.5">Fattore</th>
            <th className="px-3 py-2.5 text-right">Valore usato</th>
            <th className="px-3 py-2.5 text-right">Peso</th>
            <th className="px-3 py-2.5 text-right">Contributo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {BREAKDOWN_ROWS.map(({ key, label }) => {
            const val = breakdown[key]
            const w = breakdown[`${key}_weight` as keyof UpcomingCalculationBreakdown] as number
            const c = breakdown[`${key}_contribution` as keyof UpcomingCalculationBreakdown] as number
            const fb = breakdown[`${key}_fallback_used` as keyof UpcomingCalculationBreakdown] as boolean | undefined
            const note = breakdown[`${key}_fallback_note` as keyof UpcomingCalculationBreakdown] as
              | string
              | null
              | undefined
            return (
              <tr key={key} className="text-slate-800">
                <td className="px-3 py-2">
                  <span className="font-medium">{label}</span>
                  {fb ? (
                    <span className="mt-0.5 block text-xs font-normal text-amber-800">
                      {note ?? 'Dato sostituito.'}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatNum(Number(val))}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatNum(Number(w), 2)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{formatNum(Number(c), 4)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-200 bg-slate-50/80 font-semibold text-slate-900">
            <td className="px-3 py-2.5" colSpan={3}>
              Tiri in porta attesi (squadra)
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums">{formatNum(breakdown.expected_sot_total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

