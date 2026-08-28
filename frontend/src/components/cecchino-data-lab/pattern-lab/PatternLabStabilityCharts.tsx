import ReactECharts from 'echarts-for-react'
import type { PatternLabBreakdownBucket } from '../../../lib/patternLabApi'
import { formatPct } from '../../../lib/patternLabApi'
import { overviewColors, roiColor } from '../overview/overviewTheme'

type Props = {
  bySeason: PatternLabBreakdownBucket[]
  byCompetition: PatternLabBreakdownBucket[]
  byMarket: PatternLabBreakdownBucket[]
}

function StabilityChart({
  title,
  rows,
}: {
  title: string
  rows: PatternLabBreakdownBucket[]
}) {
  const data = rows.slice(0, 24)
  const option = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8aa0b5' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f1c2c',
      borderColor: 'rgba(120,190,220,0.2)',
      textStyle: { color: '#e8f1f8' },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const i = params[0]?.dataIndex ?? 0
        const r = data[i]
        if (!r) return ''
        return `${r.key}<br/>N: ${r.selections}<br/>WR: ${formatPct(r.win_rate)}<br/>ROI: ${formatPct(r.roi)}`
      },
    },
    grid: { left: 90, right: 48, top: 16, bottom: 28 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    yAxis: {
      type: 'category',
      data: data.map((r) => r.key),
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
      axisLabel: { width: 80, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        data: data.map((r) => ({
          value: r.roi ?? 0,
          itemStyle: {
            color: (r.roi ?? 0) >= 0 ? overviewColors.positive : overviewColors.negative,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: {
          show: true,
          position: 'right',
          color: '#8aa0b5',
          formatter: (p: { dataIndex: number }) => `n=${data[p.dataIndex]?.selections ?? 0}`,
        },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ xAxis: 0 }],
          lineStyle: { color: 'rgba(232,241,248,0.35)', type: 'dashed' },
        },
      },
    ],
  }

  const negativeShare =
    data.length > 0 ? data.filter((r) => (r.roi ?? 0) < 0).length / data.length : 0
  const suspect = data.length >= 2 && negativeShare >= 0.6

  return (
    <div className="lab-card rounded-xl p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
          {title}
        </h3>
        {suspect ? (
          <span className="lab-badge-warn rounded px-2 py-0.5 text-[11px]">
            Pattern instabile
          </span>
        ) : null}
      </div>
      {data.length ? (
        <ReactECharts option={option} style={{ height: Math.max(180, data.length * 28) }} opts={{ renderer: 'canvas' }} />
      ) : (
        <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessun segmento.
        </p>
      )}
      {data.length > 0 && data.length <= 8 ? (
        <div className="mt-2 max-h-40 overflow-auto text-xs">
          <table className="lab-table w-full">
            <thead>
              <tr>
                <th>Segmento</th>
                <th>N</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.key}>
                  <td>{r.key}</td>
                  <td>{r.selections}</td>
                  <td style={{ color: roiColor(r.roi) }}>{formatPct(r.roi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export function PatternLabStabilityCharts({ bySeason, byCompetition, byMarket }: Props) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Stabilità del pattern
      </h2>
      <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
        ROI e sample size per stagione, campionato e mercato. Un ROI totale positivo con molti
        segmenti negativi è sospetto.
      </p>
      <div className="grid gap-4 lg:grid-cols-3">
        <StabilityChart title="ROI per stagione" rows={bySeason} />
        <StabilityChart title="ROI per campionato" rows={byCompetition} />
        <StabilityChart title="ROI per mercato" rows={byMarket} />
      </div>
    </section>
  )
}
