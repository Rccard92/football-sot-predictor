import ReactECharts from 'echarts-for-react'
import type {
  HistoricalKpiSignalsFilters,
  HistoricalKpiTimelinePoint,
  HistoricalKpiTimelineResponse,
} from '../../../lib/cecchinoLabApi'
import {
  formatProfit,
  formatRoi,
  formatWinRate,
  roiColorClass,
} from './historicalKpiUtils'

type Props = {
  timeline?: HistoricalKpiTimelineResponse | null
  points?: HistoricalKpiTimelinePoint[]
  groupingFallback?: string | null
  quoteType?: HistoricalKpiSignalsFilters['quote_type']
}

function extractProfit(point: HistoricalKpiTimelinePoint, quoteType: string): number | null {
  if (quoteType === 'all') {
    const real = point.real?.profit_units
    return real ?? point.synthetic?.profit_units ?? null
  }
  return point.profit_units ?? null
}

function extractCumulative(point: HistoricalKpiTimelinePoint, quoteType: string): number | null {
  const cum = point.cumulative_profit_units
  if (cum == null) return null
  if (typeof cum === 'number') return cum
  if (quoteType === 'derived') return cum.synthetic ?? null
  if (quoteType === 'all') return cum.real ?? cum.synthetic ?? null
  return cum.real ?? null
}

export function HistoricalKpiTimeline({
  timeline,
  points: pointsProp,
  groupingFallback: fallbackProp,
  quoteType = 'real',
}: Props) {
  const points = pointsProp ?? timeline?.points ?? []
  const groupingFallback = fallbackProp ?? timeline?.grouping_fallback ?? null
  const qt = quoteType ?? 'real'

  const labels = points.map((p) => p.group_label)
  const periodProfit = points.map((p) => extractProfit(p, qt))
  const cumulativeProfit = points.map((p) => extractCumulative(p, qt))

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#8aa0b5' } },
    grid: { left: 48, right: 24, top: 40, bottom: 50 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: '#8aa0b5', rotate: 30, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      name: 'Profitto (u)',
      axisLabel: { color: '#8aa0b5' },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [
      {
        name: 'Profitto periodo',
        type: 'bar',
        data: periodProfit,
        itemStyle: { color: 'rgba(46,230,255,0.45)' },
      },
      {
        name: 'Profitto cumulativo',
        type: 'line',
        data: cumulativeProfit,
        itemStyle: { color: '#3dd68c' },
        lineStyle: { width: 2 },
      },
    ],
  }

  return (
    <section data-testid="historical-kpi-timeline">
      <h3 className="mb-2 text-lg font-semibold">Timeline giornate</h3>
      {groupingFallback === 'date' ? (
        <p className="mb-3 text-xs" style={{ color: 'var(--lab-warn)' }}>
          La giornata originale non è disponibile: raggruppamento per data.
        </p>
      ) : (
        <p className="mb-3 text-xs text-[var(--lab-muted)]">
          Andamento profitto per periodo e cumulato sui kickoff storici filtrati.
        </p>
      )}
      <div
        className="mb-4 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 280 }} />
      </div>
      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Giornata</th>
              <th>Segnali</th>
              <th>Valutati</th>
              <th>Win rate</th>
              <th>Profitto</th>
              <th>ROI</th>
              <th>Cumulativo</th>
              <th>Fasce (sintesi)</th>
            </tr>
          </thead>
          <tbody>
            {points.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-[var(--lab-muted)]">
                  Nessun punto timeline.
                </td>
              </tr>
            ) : (
              points.map((p) => {
                const profit = extractProfit(p, qt)
                const roi =
                  qt === 'all'
                    ? (p.real?.roi_pct ?? p.synthetic?.roi_pct ?? null)
                    : (p.roi_pct ?? null)
                const cum = extractCumulative(p, qt)
                const signals =
                  qt === 'all'
                    ? (p.real?.signals_count ?? 0) + (p.synthetic?.signals_count ?? 0)
                    : (p.signals_count ?? p.real?.signals_count ?? 0)
                const evaluated =
                  qt === 'all'
                    ? (p.real?.evaluated_count ?? 0) + (p.synthetic?.evaluated_count ?? 0)
                    : (p.evaluated_count ?? p.real?.evaluated_count ?? 0)
                const winRate =
                  qt === 'all' ? (p.real?.win_rate_pct ?? p.synthetic?.win_rate_pct ?? null) : p.win_rate_pct
                const bucketHint =
                  p.by_rating_bucket
                    ?.filter((b) => b.evaluated_count > 0)
                    .slice(0, 3)
                    .map((b) => `${b.rating_bucket}:${formatRoi(b.roi_pct)}`)
                    .join(' · ') ?? '—'

                return (
                  <tr key={p.group_key}>
                    <td>{p.group_label}</td>
                    <td>{signals}</td>
                    <td>{evaluated}</td>
                    <td>{formatWinRate(winRate)}</td>
                    <td className={roiColorClass(roi)}>{formatProfit(profit)}</td>
                    <td className={roiColorClass(roi)}>{formatRoi(roi)}</td>
                    <td className={roiColorClass(roi)}>{formatProfit(cum)}</td>
                    <td className="max-w-[220px] truncate text-xs text-[var(--lab-muted)]" title={bucketHint}>
                      {bucketHint}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
