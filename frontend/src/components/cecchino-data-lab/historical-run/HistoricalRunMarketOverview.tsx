import ReactECharts from 'echarts-for-react'
import {
  formatNullableNumber,
  formatOdd,
  type HistoricalRunDashboardMarket,
} from '../../../lib/cecchinoLabApi'

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
          `hit ${m.hit_rate != null ? `${(m.hit_rate * 100).toFixed(1)}%` : '—'}`,
          `quote reali ${m.real_quote_count} · derivate ${m.derived_quote_count} · N/D ${m.unavailable_quote_count}`,
          `odds reali ${formatOdd(m.average_real_odds)} · derivate ${formatOdd(m.average_derived_odds)}`,
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
        data: markets.map((m) => (m.hit_rate != null ? m.hit_rate : null)),
        itemStyle: { color: '#2ee6ff' },
      },
    ],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">14 mercati</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Mercati indipendenti — ROI reale e sintetico separati. Non sommare i mercati. Quote N/D
        conteggiate; medie assenti mostrate come —.
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
              <th>Fair q.</th>
              <th>Rating</th>
              <th>Reali</th>
              <th>Derivate</th>
              <th>N/D</th>
              <th>Odds reali</th>
              <th>Odds der.</th>
              <th>ROI reale</th>
              <th>ROI synth</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((m) => (
              <tr key={m.market_key}>
                <td>{m.label}</td>
                <td>{m.sample_size}</td>
                <td>
                  {m.hit_rate != null ? `${(m.hit_rate * 100).toFixed(1)}%` : '—'}
                </td>
                <td>
                  {m.with_cecchino_probability != null
                    ? m.with_cecchino_probability
                    : '—'}
                  {m.average_cecchino_probability != null
                    ? ` · ${formatNullableNumber(m.average_cecchino_probability, 3)}`
                    : ''}
                </td>
                <td>{m.with_cecchino_fair_quote ?? m.with_cecchino_quote ?? '—'}</td>
                <td>
                  {m.average_rating != null
                    ? formatNullableNumber(m.average_rating, 1)
                    : '—'}
                </td>
                <td>{m.real_quote_count}</td>
                <td>{m.derived_quote_count}</td>
                <td>{m.unavailable_quote_count}</td>
                <td>{formatOdd(m.average_real_odds)}</td>
                <td>{formatOdd(m.average_derived_odds)}</td>
                <td>{m.real_roi_pct != null ? `${m.real_roi_pct}%` : '—'}</td>
                <td>{m.synthetic_roi_pct != null ? `${m.synthetic_roi_pct}%` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
