import { useMemo, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { SignalsSummaryResponse, WeightModelSummary } from '../../lib/cecchinoSignalsApi'
import {
  rankTopSignals,
  TOP_SORT_OPTIONS,
  type TopSortKey,
} from './signalsLabUtils'

echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

type MetricKey = 'win_rate' | 'taken_profit_indicator' | 'avg_won_book_odds'

const METRIC_OPTIONS: Array<{ value: MetricKey; label: string }> = [
  { value: 'win_rate', label: 'Win Rate' },
  { value: 'taken_profit_indicator', label: 'Rendimento' },
  { value: 'avg_won_book_odds', label: 'Quota prese' },
]

type Props = {
  models: WeightModelSummary[]
  summary: SignalsSummaryResponse
}

export function SignalsTrendChart({ models, summary }: Props) {
  const [metric, setMetric] = useState<MetricKey>('win_rate')
  const [topSort, setTopSort] = useState<TopSortKey>('taken_profit')

  const compareOption = useMemo(() => {
    const labels = models.map((m) => `Modello ${m.model_key}`)
    const values = models.map((m) => {
      const v = m[metric]
      if (v == null) return 0
      if (metric === 'win_rate') return v
      if (metric === 'taken_profit_indicator') return Math.round(v * 1000) / 10
      return v
    })
    const yName =
      metric === 'win_rate' ? '%' : metric === 'taken_profit_indicator' ? '% rend.' : 'quota'
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      xAxis: { type: 'category' as const, data: labels, axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' as const, name: yName },
      series: [
        {
          type: 'bar' as const,
          data: values,
          itemStyle: {
            borderRadius: [6, 6, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#818cf8' },
              { offset: 1, color: '#6366f1' },
            ]),
          },
        },
      ],
    }
  }, [models, metric])

  const donutOption = useMemo(() => {
    const o = summary.overall
    return {
      tooltip: { trigger: 'item' as const },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      series: [
        {
          type: 'pie' as const,
          radius: ['42%', '68%'],
          avoidLabelOverlap: true,
          label: { show: false },
          data: [
            { value: o.won, name: 'Vinti', itemStyle: { color: '#10b981' } },
            { value: o.lost, name: 'Persi', itemStyle: { color: '#ef4444' } },
            { value: o.pending, name: 'Pending', itemStyle: { color: '#0ea5e9' } },
            { value: o.not_evaluable, name: 'Non valutabili', itemStyle: { color: '#94a3b8' } },
          ],
        },
      ],
    }
  }, [summary.overall])

  const topRows = useMemo(
    () => rankTopSignals(summary, topSort, 5, 8),
    [summary, topSort],
  )

  const topOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' as const },
      grid: { left: 120, right: 24, top: 8, bottom: 24 },
      xAxis: { type: 'value' as const },
      yAxis: {
        type: 'category' as const,
        data: topRows.map(
          (r) => `${r.signal_label} · ${r.source_column.replace('EXCEL_', 'E')}`,
        ),
        axisLabel: { fontSize: 10 },
      },
      series: [
        {
          type: 'bar' as const,
          data: topRows.map((r) =>
            Math.round((r.taken_profit_indicator ?? 0) * 1000) / 10,
          ),
          itemStyle: { color: '#14b8a6', borderRadius: [0, 4, 4, 0] },
        },
      ],
    }),
    [topRows],
  )

  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Confronto modelli</h3>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricKey)}
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
          >
            {METRIC_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <ReactEChartsCore echarts={echarts} option={compareOption} style={{ height: 280 }} notMerge lazyUpdate />
      </div>
      <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">Distribuzione esiti — modello selezionato</h3>
        <ReactEChartsCore echarts={echarts} option={donutOption} style={{ height: 280 }} notMerge lazyUpdate />
      </div>
      <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm lg:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Top segnali per rendimento</h3>
          <select
            value={topSort}
            onChange={(e) => setTopSort(e.target.value as TopSortKey)}
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
          >
            {TOP_SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <ReactEChartsCore
          echarts={echarts}
          option={topOption}
          style={{ height: Math.max(220, topRows.length * 36) }}
          notMerge
          lazyUpdate
        />
      </div>
    </section>
  )
}
