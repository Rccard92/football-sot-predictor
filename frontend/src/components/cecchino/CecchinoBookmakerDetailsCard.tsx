import type { CecchinoBookmakerOddsDetailRow } from '../../lib/cecchinoTodayApi'
import { fmtKpiCell } from './cecchinoKpiUiUtils'
import { todayCard, todayCardPadding, todaySectionTitle } from './cecchinoTodayStyles'

function sourceLabel(source: string): string {
  switch (source) {
    case 'raw_betfair':
      return 'Betfair raw'
    case 'derived_from_1x2':
      return 'Derivato 1X2'
    case 'not_available':
      return 'Non disponibile'
    default:
      return source
  }
}

type Props = {
  rows: CecchinoBookmakerOddsDetailRow[]
}

export function CecchinoBookmakerDetailsCard({ rows }: Props) {
  if (!rows.length) return null

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Dettaglio quote Betfair</h3>
        <p className="mt-1 text-xs text-slate-500">
          Quote per mercato su Betfair con origine e stato.
        </p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 md:overflow-visible">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <th className="px-4 py-3">Mercato</th>
              <th className="px-4 py-3 text-center tabular-nums">Quota Betfair</th>
              <th className="px-4 py-3 text-center">Source</th>
              <th className="px-4 py-3 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.market_key} className="border-t border-slate-100 hover:bg-slate-50/80">
                <td className="px-4 py-2.5 font-medium text-slate-800">{row.label}</td>
                <td className="px-4 py-2.5 text-center tabular-nums text-slate-700">
                  {fmtKpiCell(row.quota_betfair, true)}
                </td>
                <td className="px-4 py-2.5 text-center text-xs text-slate-600">
                  {sourceLabel(row.source)}
                </td>
                <td className="px-4 py-2.5 text-center text-xs text-slate-600">
                  {row.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
