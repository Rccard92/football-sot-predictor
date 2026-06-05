import type { CecchinoKpiRow } from '../../lib/cecchinoApi'
import { fmtKpiCell } from './cecchinoKpiUiUtils'
import { todayCard, todayCardPadding, todaySectionTitle } from './cecchinoTodayStyles'

const BOOK_NAMES = ['Bet365', 'Betfair', 'Pinnacle'] as const

function countPresentBooks(row: CecchinoKpiRow): number {
  const bm = row.bookmakers || {}
  return BOOK_NAMES.filter((n) => bm[n] != null).length
}

function hasBookmakerData(row: CecchinoKpiRow): boolean {
  return countPresentBooks(row) > 0
}

function displayAverage(row: CecchinoKpiRow): number | null {
  const present = countPresentBooks(row)
  if (present === 0) return null
  return row.book_average != null ? (row.book_average as number) : null
}

export function CecchinoBookmakerDetailsCard({ rows }: { rows: CecchinoKpiRow[] }) {
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
              const avg = displayAverage(row)
              const isPartial = row.status === 'partial'
              return (
                <tr key={row.label} className="border-t border-slate-100 hover:bg-slate-50/80">
                  <td className="px-4 py-2.5 font-medium text-slate-800">
                    <span>{row.label}</span>
                    {isPartial ? (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-900">
                        Parziale
                      </span>
                    ) : null}
                  </td>
                  {BOOK_NAMES.map((n) => (
                    <td key={n} className="px-4 py-2.5 text-center tabular-nums text-slate-700">
                      {fmtKpiCell(bm[n] as number | null, true)}
                    </td>
                  ))}
                  <td className="px-4 py-2.5 text-center font-medium tabular-nums text-indigo-700">
                    {fmtKpiCell(avg, true)}
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
