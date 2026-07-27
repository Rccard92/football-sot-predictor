import ReactECharts from 'echarts-for-react'
import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { overviewColors } from './overviewTheme'

type Props = {
  outcomes: CecchinoLabAnalyticsOverview['outcomes_1x2']
  goals: CecchinoLabAnalyticsOverview['goals']
}

export function FlatRoiExplorer({ outcomes, goals }: Props) {
  const rows = [
    { name: '1', roi: outcomes.home.flat_roi_pct, n: outcomes.home.sample_size ?? 0, profit: outcomes.home.flat_profit_units, color: overviewColors.home },
    { name: 'X', roi: outcomes.draw.flat_roi_pct, n: outcomes.draw.sample_size ?? 0, profit: outcomes.draw.flat_profit_units, color: overviewColors.draw },
    { name: '2', roi: outcomes.away.flat_roi_pct, n: outcomes.away.sample_size ?? 0, profit: outcomes.away.flat_profit_units, color: overviewColors.away },
    { name: 'Over 2.5', roi: goals.over_25.flat_roi_pct ?? null, n: goals.over_25.sample_size ?? 0, profit: goals.over_25.flat_profit_units ?? null, color: overviewColors.over },
    { name: 'Under 2.5', roi: goals.under_25.flat_roi_pct ?? null, n: goals.under_25.sample_size ?? 0, profit: goals.under_25.flat_profit_units ?? null, color: overviewColors.under },
  ]

  const option = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8aa0b5' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f1c2c',
      borderColor: 'rgba(120,190,220,0.2)',
      textStyle: { color: '#e8f1f8' },
      formatter: (params: Array<{ dataIndex: number; value: number }>) => {
        const i = params[0]?.dataIndex ?? 0
        const r = rows[i]
        return `${r.name}<br/>Giocate: ${r.n}<br/>Profitto: ${r.profit ?? '—'} u<br/>ROI: ${r.roi ?? '—'}%`
      },
    },
    grid: { left: 80, right: 24, top: 20, bottom: 30 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((r) => r.name),
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.roi ?? 0,
          itemStyle: {
            color: (r.roi ?? 0) >= 0 ? overviewColors.positive : overviewColors.negative,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ xAxis: 0 }],
          lineStyle: { color: 'rgba(232,241,248,0.35)', type: 'dashed' },
        },
      },
    ],
  }

  const empty = rows.every((r) => r.n === 0)

  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: 'linear-gradient(160deg, rgba(21,38,58,0.95), rgba(12,24,38,0.98))',
        border: '1px solid var(--lab-border)',
      }}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
          Flat ROI Explorer
        </h2>
        <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
          <MetricTooltip metric="roi_flat">ROI storico flat 1u</MetricTooltip>
        </span>
      </div>
      {empty ? (
        <div className="py-10 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessuna giocata eleggibile (quote mancanti escluse).
        </div>
      ) : (
        <ReactECharts option={option} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
      )}
    </section>
  )
}
