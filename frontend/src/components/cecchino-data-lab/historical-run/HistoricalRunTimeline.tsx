import ReactECharts from 'echarts-for-react'
import type { HistoricalRunTimelinePoint } from '../../../lib/cecchinoLabApi'

type Props = {
  points: HistoricalRunTimelinePoint[]
  granularity: string
  onGranularity: (g: string) => void
}

export function HistoricalRunTimeline({ points, granularity, onGranularity }: Props) {
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#8aa0b5' } },
    grid: { left: 40, right: 20, top: 40, bottom: 50 },
    xAxis: {
      type: 'category',
      data: points.map((p) => p.period_label),
      axisLabel: { color: '#8aa0b5', rotate: 30, fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Hit',
        axisLabel: { color: '#8aa0b5', formatter: (v: number) => `${Math.round(v * 100)}%` },
        splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
      },
      {
        type: 'value',
        name: 'N',
        axisLabel: { color: '#8aa0b5' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Hit rate',
        type: 'line',
        data: points.map((p) => p.hit_rate ?? null),
        itemStyle: { color: '#2ee6ff' },
      },
      {
        name: 'Eleggibili',
        type: 'bar',
        yAxisIndex: 1,
        data: points.map((p) => p.eligible),
        itemStyle: { color: 'rgba(61,214,140,0.35)' },
      },
    ],
  }

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">Season Timeline</h3>
        <div className="flex gap-2 text-xs">
          {['week', 'month', 'chronological_block'].map((g) => (
            <button
              key={g}
              type="button"
              className="rounded px-2 py-1"
              style={{
                background: granularity === g ? 'rgba(46,230,255,0.2)' : 'var(--lab-surface-2)',
              }}
              onClick={() => onGranularity(g)}
            >
              {g}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Asse = kickoff storico (non data di scansione).
      </p>
      <div
        className="rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 280 }} />
      </div>
    </section>
  )
}
