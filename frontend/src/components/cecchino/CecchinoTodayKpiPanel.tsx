import type { CecchinoKpiV2Panel } from '../../lib/cecchinoTodayApi'
import {
  edgeClassName,
  fmtKpiCell,
  fmtProbPct,
  fmtScoreAcquisto,
  fmtVantaggioProb,
  formatEdgePct,
  isKpiPrimaryRow,
  ratingBadgeClass,
  vantaggioClassName,
} from './cecchinoKpiUiUtils'

type Props = {
  panel: CecchinoKpiV2Panel
  bookmakerStatus?: string
}

export function CecchinoTodayKpiPanel({ panel, bookmakerStatus }: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'

  return (
    <section className="overflow-hidden rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3 text-center">
        <h3 className="text-sm font-bold tracking-wide text-white sm:text-base">PANNELLO KPI</h3>
        <p className="mt-1 text-[10px] text-slate-300 sm:text-xs">
          Bookmaker: {panel.bookmaker?.name ?? 'Betfair'}
        </p>
        {status === 'not_available' && (
          <p className="mt-1 text-[10px] text-amber-100 sm:text-xs">
            Quote Betfair non disponibili
          </p>
        )}
      </div>

      <div className="hidden bg-[#163352] md:block">
        <table className="w-full table-fixed border-collapse text-center text-[11px] text-white">
          <colgroup>
            <col className="w-[9%]" />
            <col className="w-[9%]" />
            <col className="w-[9%]" />
            <col className="w-[10%]" />
            <col className="w-[10%]" />
            <col className="w-[11%]" />
            <col className="w-[9%]" />
            <col className="w-[11%]" />
            <col className="w-[22%]" />
          </colgroup>
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-slate-400/50 bg-[#0f2847]">
              <th className="border-r border-slate-500/40 px-1 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-300">
                Segno
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Quota Book
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-amber-200">
                Quota Cecchino
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Prob. Book
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Prob. Cecchino
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Vant. Prob.
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Edge %
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Score
              </th>
              <th className="px-1 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Rating
              </th>
            </tr>
          </thead>
          <tbody>
            {(panel.rows || []).map((row) => {
              const primary = isKpiPrimaryRow(row.segno)
              const rowBg = primary ? 'bg-[#1a3d5c]/60' : 'bg-transparent'
              const labelClass = primary
                ? 'font-semibold text-white'
                : 'font-medium text-slate-300'

              return (
                <tr
                  key={row.market_key}
                  className={`border-b border-slate-600/40 hover:bg-slate-800/25 ${rowBg}`}
                >
                  <td className={`border-r border-slate-500/40 px-1.5 py-2 text-left ${labelClass}`}>
                    {row.segno}
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2 tabular-nums text-slate-100">
                    {fmtKpiCell(row.quota_book, true)}
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2 font-semibold tabular-nums text-amber-100">
                    {fmtKpiCell(row.quota_cecchino, true)}
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2 tabular-nums text-slate-100">
                    {fmtProbPct(row.prob_book)}
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2 tabular-nums text-slate-100">
                    {fmtProbPct(row.prob_cecchino)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-1 py-2 tabular-nums ${vantaggioClassName(row.vantaggio_prob)}`}>
                    {fmtVantaggioProb(row.vantaggio_prob)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-1 py-2 tabular-nums ${edgeClassName(row.edge_pct)}`}>
                    {formatEdgePct(row.edge_pct)}
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2 tabular-nums text-slate-300">
                    {fmtScoreAcquisto(row.score_acquisto)}
                  </td>
                  <td className="px-1 py-2">
                    {row.rating != null ? (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                      >
                        <span className="tabular-nums">{row.rating}</span>
                        {row.rating_label && (
                          <span className="hidden lg:inline">{row.rating_label}</span>
                        )}
                      </span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 bg-[#163352] p-3 md:hidden">
        {(panel.rows || []).map((row) => (
          <article
            key={row.market_key}
            className="rounded-lg border border-slate-500/40 bg-[#1a3d5c]/40 p-3 text-xs text-white"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold">{row.segno}</span>
              {row.rating != null && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                >
                  {row.rating} {row.rating_label}
                </span>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
              <dt className="text-slate-400">Quota Book</dt>
              <dd>{fmtKpiCell(row.quota_book, true)}</dd>
              <dt className="text-slate-400">Quota Cecchino</dt>
              <dd className="text-amber-100">{fmtKpiCell(row.quota_cecchino, true)}</dd>
              <dt className="text-slate-400">Edge %</dt>
              <dd className={edgeClassName(row.edge_pct)}>{formatEdgePct(row.edge_pct)}</dd>
              <dt className="text-slate-400">Vant. Prob.</dt>
              <dd className={vantaggioClassName(row.vantaggio_prob)}>
                {fmtVantaggioProb(row.vantaggio_prob)}
              </dd>
            </dl>
          </article>
        ))}
      </div>

      {(panel.warnings ?? []).length > 0 && (
        <div className="border-t border-slate-500/40 bg-[#0f2847] px-4 py-3 text-xs text-amber-200">
          <ul className="list-disc space-y-1 pl-4">
            {(panel.warnings ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
