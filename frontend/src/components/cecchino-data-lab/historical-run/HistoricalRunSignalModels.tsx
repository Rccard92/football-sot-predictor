import ReactECharts from 'echarts-for-react'
import type { HistoricalRunSignalModelAnalytics } from '../../../lib/cecchinoLabApi'

type Props = { models: HistoricalRunSignalModelAnalytics[]; note?: string }

export function HistoricalRunSignalModels({ models, note }: Props) {
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#8aa0b5' } },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: models.map((m) => (m.is_current_model ? `${m.model_key}★` : m.model_key)),
      axisLabel: { color: '#8aa0b5' },
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
        data: models.map((m) => ({
          value: m.hit_rate ?? 0,
          itemStyle: { color: m.is_current_model ? '#2ee6ff' : '#7c6cff' },
        })),
      },
    ],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Segnali A–F</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        {note ?? 'Prestazioni osservate dei modelli A–F. F = modello corrente. Nessun vincitore automatico.'}
      </p>
      <div
        className="mb-4 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 260 }} />
      </div>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Modello</th>
              <th>Segnali</th>
              <th>Hit</th>
              <th>ROI reale</th>
              <th>ROI synth</th>
              <th>Best mercato</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr
                key={m.model_key}
                style={
                  m.is_current_model
                    ? { background: 'rgba(46,230,255,0.08)' }
                    : undefined
                }
              >
                <td>
                  {m.model_short_label}
                  {m.is_current_model ? ' · corrente' : ''}
                </td>
                <td>{m.signals_activated}</td>
                <td>{m.hit_rate != null ? `${(m.hit_rate * 100).toFixed(1)}%` : '—'}</td>
                <td>{m.real_roi != null ? `${m.real_roi}%` : '—'}</td>
                <td>{m.synthetic_roi != null ? `${m.synthetic_roi}%` : '—'}</td>
                <td>{m.market_best ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
