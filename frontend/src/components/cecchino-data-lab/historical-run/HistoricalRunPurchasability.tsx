import ReactECharts from 'echarts-for-react'
import type { HistoricalRunPurchasabilityAnalytics } from '../../../lib/cecchinoLabApi'

type Props = { data: HistoricalRunPurchasabilityAnalytics }

export function HistoricalRunPurchasability({ data }: Props) {
  const bands = data.bands
  const values = bands.map((b) => Number(data.distribution[b]?.sample_size ?? 0))
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: 'category',
      data: bands,
      axisLabel: { color: '#8aa0b5', rotate: 35, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8aa0b5' },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [{ type: 'bar', data: values, itemStyle: { color: '#3dd68c' } }],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Acquistabilità Lab</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Modulo osservazionale — non decisione finale di acquisto. Completi {data.complete_count} ·
        parziali {data.partial_count} · N/D {data.unavailable_count}.
      </p>
      <div
        className="rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 260 }} />
      </div>
    </section>
  )
}
