import type { CecchinoKpiRow } from '../../lib/cecchinoApi'
import { fmtKpiCell } from './cecchinoKpiUiUtils'
import { todayCard, todayCardPadding, todaySectionTitle } from './cecchinoTodayStyles'

const BOOK_NAMES = ['Bet365', 'Betfair', 'Pinnacle'] as const

type Props = {
  rows: CecchinoKpiRow[]
}

function hasBookmakerData(row: CecchinoKpiRow): boolean {
  const bm = row.bookmakers || {}
  return BOOK_NAMES.some((n) => bm[n] != null) || row.book_average != null
}

export function CecchinoBookmakerDetailsCard({ rows }: Props) {
  const withData = rows.filter(hasBookmakerData)
  if (withData.length === 0) return null

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Dettaglio quote bookmaker</h3>
        <p className="mt-1 text-xs text-slate-500">
          Quote per mercato su Bet365, Betfair e Pinnacle con media book.
        </p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <th className="px-4 py-3">Mercato</th>
              {BOOK_NAMES.map((n) => (
                <th key={n} className="px-4 py-3 text-center tabular-nums">
                  {n}
                </th>
              ))}
              <th className="px-4 py-3 text-center">Media book</th>
            </tr>
          </thead>
          <tbody>
            {withData.map((row) => {
              const bm = row.bookmakers || {}
              return (
                <tr key={row.label} className="border-t border-slate-100 hover:bg-slate-50/80">
                  <td className="px-4 py-2.5 font-medium text-slate-800">{row.label}</td>
                  {BOOK_NAMES.map((n) => (
                    <td key={n} className="px-4 py-2.5 text-center tabular-nums text-slate-700">
                      {fmtKpiCell(bm[n] as number | null, true)}
                    </td>
                  ))}
                  <td className="px-4 py-2.5 text-center font-medium tabular-nums text-indigo-700">
                    {fmtKpiCell(row.book_average, true)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
