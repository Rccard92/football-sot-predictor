import ReactECharts from 'echarts-for-react'
import type { HistoricalRunRatingCell } from '../../../lib/cecchinoLabApi'

type Props = { bands: string[]; matrix: HistoricalRunRatingCell[] }

export function HistoricalRunRatingHeatmap({ bands, matrix }: Props) {
  const markets = [...new Set(matrix.map((c) => c.market_key))]
  const data = matrix.map((c) => {
    const x = bands.indexOf(c.rating_band)
    const y = markets.indexOf(c.market_key)
    return [x, y, c.hit_rate ?? 0, c]
  })

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: { data: [number, number, number, HistoricalRunRatingCell] }) => {
        const c = p.data[3]
        return [
          `<b>${c.market_key} · ${c.rating_band}</b>`,
          `N ${c.sample_size} · W ${c.wins} L ${c.losses}`,
          `hit ${c.hit_rate != null ? (c.hit_rate * 100).toFixed(1) : '—'}%`,
          `ROI reale ${c.real_roi_pct ?? '—'}%`,
          `status ${c.confidence_status}`,
        ].join('<br/>')
      },
    },
    grid: { left: 90, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category',
      data: bands,
      axisLabel: { color: '#8aa0b5', rotate: 30, fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: markets,
      axisLabel: { color: '#8aa0b5', fontSize: 10 },
    },
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: '#8aa0b5' },
      inRange: { color: ['#122033', '#1a8a9e', '#2ee6ff'] },
    },
    series: [
      {
        type: 'heatmap',
        data: data.map((d) => [d[0], d[1], d[2], d[3]]),
      },
    ],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Rating Lab</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Heatmap mercato × fascia Rating. Fascia alta ≠ automaticamente migliore.
      </p>
      <div
        className="rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 420 }} />
      </div>
    </section>
  )
}
