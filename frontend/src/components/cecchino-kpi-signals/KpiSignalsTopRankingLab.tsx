import type { KpiSignalsSummaryResponse } from '../../lib/cecchinoKpiSignalsApi'
import {
  formatKpiProfit,
  formatKpiRoi,
  formatKpiWinRate,
  parseKpiTopRow,
  profitTextClass,
  type KpiTopRow,
} from './kpiSignalsLabUtils'

type Props = {
  top: KpiSignalsSummaryResponse['top']
  minSettled?: number
}

function RankingColumn({
  title,
  rows,
  tone,
  minSettled,
}: {
  title: string
  rows: KpiTopRow[]
  tone: 'emerald' | 'cyan' | 'rose'
  minSettled: number
}) {
  const header =
    tone === 'emerald'
      ? 'border-emerald-100 bg-emerald-50/30'
      : tone === 'rose'
        ? 'border-rose-100 bg-rose-50/30'
        : 'border-cyan-100 bg-cyan-50/30'

  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${header}`}>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.length === 0 ? (
          <p className="text-xs text-slate-500">Nessun dato sufficiente.</p>
        ) : (
          rows.map((row, idx) => {
            const settled = row.settled ?? 0
            const lowSample = settled > 0 && settled < minSettled
            return (
              <div
                key={`${title}-${idx}-${row.selection_label}-${row.rating_bucket}`}
                className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2.5 transition hover:border-cyan-100 hover:shadow-sm"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-700">
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">
                    {row.selection_label ?? '—'} · {row.rating_bucket ?? '—'}
                  </p>
                  <p className="text-xs text-slate-500">
                    {settled} valutati · WR {formatKpiWinRate(row.win_rate)}
                  </p>
                </div>
                <div className="text-right text-xs tabular-nums">
                  <p className={`font-semibold ${profitTextClass(row.profit_units)}`}>
                    {formatKpiProfit(row.profit_units)}
                  </p>
                  <p className="text-slate-500">ROI {formatKpiRoi(row.roi_pct)}</p>
                </div>
                {lowSample ? (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-800">
                    campione basso
                  </span>
                ) : null}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export function KpiSignalsTopRankingLab({ top, minSettled = 3 }: Props) {
  const bestProfit = (top.best_profit ?? []).map(parseKpiTopRow).slice(0, 5)
  const bestRoi = (top.best_roi ?? []).map(parseKpiTopRow).slice(0, 5)
  const worstProfit = (top.worst_profit ?? []).map(parseKpiTopRow).slice(0, 5)

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-800">Migliori combinazioni KPI</h2>
        <p className="mt-1 text-xs text-slate-500">Top profitto, top ROI e peggiori combinazioni per bucket e pronostico.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <RankingColumn title="Miglior profitto" rows={bestProfit} tone="emerald" minSettled={minSettled} />
        <RankingColumn title="Miglior ROI" rows={bestRoi} tone="cyan" minSettled={minSettled} />
        <RankingColumn title="Peggiori combinazioni" rows={worstProfit} tone="rose" minSettled={minSettled} />
      </div>
    </section>
  )
}
