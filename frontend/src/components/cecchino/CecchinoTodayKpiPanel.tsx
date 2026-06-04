import type { CecchinoKpiPanel as CecchinoKpiPanelType } from '../../lib/cecchinoApi'
import {
  edgeClassName,
  fmtKpiCell,
  formatEdgePct,
  isKpiAnalysisRow,
  isKpiPrimaryRow,
} from './cecchinoKpiUiUtils'

type Props = {
  panel: CecchinoKpiPanelType
  bookmakerStatus?: string
}

export function CecchinoTodayKpiPanel({ panel, bookmakerStatus }: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'

  return (
    <section className="overflow-hidden rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-5 py-4 text-center">
        <h3 className="text-base font-bold tracking-wide text-white">PANNELLO KPI</h3>
        {status === 'partial' && (
          <span className="mt-2 inline-block rounded-full bg-amber-500 px-3 py-0.5 text-xs font-semibold text-white">
            Quote bookmaker parziali
          </span>
        )}
        {status === 'not_available' && (
          <p className="mt-2 text-xs text-amber-100">
            Quote bookmaker non disponibili — colonna BOOK vuota
          </p>
        )}
      </div>

      <div className="overflow-x-auto bg-[#163352]">
        <table className="w-full min-w-[720px] border-collapse text-center text-sm text-white">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-slate-400/50 bg-[#0f2847]">
              <th className="border-r border-slate-500/40 px-4 py-3 w-32 text-left text-xs font-semibold uppercase tracking-wide text-slate-300" />
              <th className="border-r border-slate-500/40 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-200">
                Statistica
              </th>
              <th className="border-r border-slate-500/40 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-amber-200">
                Cecchino
              </th>
              <th className="border-r border-slate-500/40 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-200">
                Book
              </th>
              <th className="border-r border-slate-500/40 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-200">
                Media
              </th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-200">
                Edge
              </th>
            </tr>
          </thead>
          <tbody>
            {(panel.rows || []).map((row) => {
              const primary = isKpiPrimaryRow(row.label)
              const analysis = isKpiAnalysisRow(row.label)
              const asDecimal = !analysis && typeof row.statistica === 'number'
              const rowBg = primary
                ? 'bg-[#1a3d5c]/60'
                : analysis
                  ? 'bg-[#122a42]/40'
                  : 'bg-transparent'
              const labelClass = primary
                ? 'font-semibold text-white'
                : analysis
                  ? 'font-normal text-slate-400'
                  : 'font-medium text-slate-300'
              const cellClass = analysis ? 'text-slate-400' : 'text-slate-100'

              return (
                <tr
                  key={row.label}
                  className={`border-b border-slate-600/40 hover:bg-slate-800/25 ${rowBg}`}
                >
                  <td className={`border-r border-slate-500/40 px-4 py-3 text-left ${labelClass}`}>
                    {row.label}
                  </td>
                  <td className={`border-r border-slate-500/40 px-4 py-3 tabular-nums ${cellClass}`}>
                    {fmtKpiCell(row.statistica, asDecimal)}
                  </td>
                  <td className="border-r border-slate-500/40 px-4 py-3 font-semibold tabular-nums text-amber-100">
                    {fmtKpiCell(row.cecchino, asDecimal)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-4 py-3 tabular-nums ${cellClass}`}>
                    {fmtKpiCell(row.book, asDecimal)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-4 py-3 tabular-nums ${cellClass}`}>
                    {fmtKpiCell(row.media, asDecimal)}
                  </td>
                  <td className={`px-4 py-3 ${edgeClassName(row.edge)}`}>
                    {formatEdgePct(row.edge)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="border-t border-slate-500/40 bg-[#0f2847] px-5 py-4 text-sm text-slate-200">
        <p className="font-semibold text-white">Metrica percentuale delta di forza</p>
        <ul className="mt-3 space-y-1.5">
          {(panel.delta_force_legend || []).map((item) => (
            <li key={item.range}>
              <span className="font-medium text-sky-300">{item.range}</span>
              <span className="text-slate-400"> — </span>
              {item.label}
            </li>
          ))}
        </ul>
        {(panel.warnings ?? []).length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-amber-200">
            {(panel.warnings ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
