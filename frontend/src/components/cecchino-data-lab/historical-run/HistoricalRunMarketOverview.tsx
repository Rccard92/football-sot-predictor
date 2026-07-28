import ReactECharts from 'echarts-for-react'
import type { HistoricalRunDashboardMarket } from '../../../lib/cecchinoLabApi'

type Props = { markets: HistoricalRunDashboardMarket[] }

export function HistoricalRunMarketOverview({ markets }: Props) {
  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ dataIndex: number }>) => {
        const i = params[0]?.dataIndex ?? 0
        const m = markets[i]
        if (!m) return ''
        return [
          `<b>${m.label}</b>`,
          `sample ${m.sample_size} · W ${m.wins} L ${m.losses}`,
          `hit ${(m.hit_rate ?? 0) * 100}%`,
          `quote reali ${m.real_quote_count} · derivate ${m.derived_quote_count}`,
          `ROI reale ${m.real_roi_pct ?? '—'}% · synth ${m.synthetic_roi_pct ?? '—'}%`,
          m.warnings?.includes('small_sample') ? '⚠ campione piccolo' : '',
        ]
          .filter(Boolean)
          .join('<br/>')
      },
    },
    grid: { left: 40, right: 20, top: 30, bottom: 60 },
    xAxis: {
      type: 'category',
      data: markets.map((m) => m.label),
      axisLabel: { color: '#8aa0b5', rotate: 35, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8aa0b5', formatter: (v: number) => `${Math.round(v * 100)}%` },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [
      {
        name: 'Hit rate',
        type: 'bar',
        data: markets.map((m) => m.hit_rate ?? 0),
        itemStyle: { color: '#2ee6ff' },
      },
    ],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">14 mercati</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Mercati indipendenti — ROI reale e sintetico separati. Non sommare i mercati.
      </p>
      <div
        className="mb-4 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 280 }} />
      </div>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Mercato</th>
              <th>N</th>
              <th>Hit</th>
              <th>P(Cecchino)</th>
              <th>Gap cal.</th>
              <th>Rating</th>
              <th>Reali</th>
              <th>Derivate</th>
              <th>ROI reale</th>
              <th>ROI synth</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((m) => (
              <tr key={m.market_key}>
                <td>{m.label}</td>
                <td>{m.sample_size}</td>
                <td>{m.hit_rate != null ? `${(m.hit_rate * 100).toFixed(1)}%` : '—'}</td>
                <td>
                  {m.average_cecchino_probability != null
                    ? `${(m.average_cecchino_probability * 100).toFixed(1)}%`
                    : '—'}
                </td>
                <td>{m.calibration_gap ?? '—'}</td>
                <td>{m.average_rating ?? '—'}</td>
                <td>{m.real_quote_count}</td>
                <td>{m.derived_quote_count}</td>
                <td style={{ color: (m.real_roi_pct ?? 0) >= 0 ? 'var(--lab-ok)' : 'var(--lab-err)' }}>
                  {m.real_roi_pct != null ? `${m.real_roi_pct}%` : '—'}
                </td>
                <td>{m.synthetic_roi_pct != null ? `${m.synthetic_roi_pct}%` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
