import ReactECharts from 'echarts-for-react'
import {
  formatNullableNumber,
  type HistoricalRunPurchasabilityAnalytics,
} from '../../../lib/cecchinoLabApi'

type Props = { data: HistoricalRunPurchasabilityAnalytics }

type PurchRow = Record<string, unknown> & {
  keys?: string[]
  market_key?: string
  band?: string
  sample_size?: number
  hit_rate?: number | null
  real_roi_pct?: number | null
  real_quote_count?: number
  derived_quote_count?: number
}

function rowKeys(row: PurchRow): string[] {
  return Array.isArray(row.keys) ? row.keys.map(String) : []
}

export function HistoricalRunPurchasability({ data }: Props) {
  const byMarket = (data.by_market || []) as PurchRow[]
  const markets = [...new Set(byMarket.map((r) => String(rowKeys(r)[0] ?? r.market_key ?? '')))]
  const bands = data.bands

  // Heatmap primaria mercato × fascia (sample_size)
  const heatData: Array<[number, number, number | null, PurchRow]> = []
  for (const row of byMarket) {
    const keys = rowKeys(row)
    const mk = String(keys[0] ?? row.market_key ?? '')
    const band = String(keys[1] ?? row.band ?? '')
    const x = bands.indexOf(band)
    const y = markets.indexOf(mk)
    if (x < 0 || y < 0) continue
    const n = Number(row.sample_size ?? 0)
    heatData.push([x, y, n > 0 ? n : null, row])
  }

  const heatOption = {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: { data: [number, number, number | null, PurchRow] }) => {
        const c = p.data[3]
        const keys = rowKeys(c)
        const roi = c.real_roi_pct
        return [
          `<b>${String(keys[0] ?? '')} · ${String(keys[1] ?? '')}</b>`,
          `N ${String(c.sample_size ?? 0)}`,
          `hit ${c.hit_rate != null ? `${(Number(c.hit_rate) * 100).toFixed(1)}%` : '—'}`,
          `ROI reale ${roi != null ? `${roi}%` : '—'}`,
          `reali ${String(c.real_quote_count ?? 0)} · derivate ${String(c.derived_quote_count ?? 0)}`,
        ].join('<br/>')
      },
    },
    grid: { left: 90, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category',
      data: bands,
      axisLabel: { color: '#8aa0b5', rotate: 35, fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: markets,
      axisLabel: { color: '#8aa0b5', fontSize: 10 },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, ...heatData.map((d) => d[2] ?? 0)),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: '#8aa0b5' },
      inRange: { color: ['#122033', '#2a7a55', '#3dd68c'] },
    },
    series: [{ type: 'heatmap', data: heatData }],
  }

  // Distribuzione globale: solo conteggi diagnostici
  const distValues = bands.map((b) => Number(data.distribution[b]?.sample_size ?? 0))
  const distOption = {
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
    series: [{ type: 'bar', data: distValues, itemStyle: { color: '#3dd68c' } }],
  }

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Acquistabilità Lab</h3>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Vista primaria: mercato × fascia. Completi {data.complete_count} · parziali{' '}
        {data.partial_count} · N/D {data.unavailable_count}.
      </p>
      <p className="mb-3 text-xs" style={{ color: 'var(--lab-warn)' }}>
        {data.warning ||
          'I mercati sono valutazioni indipendenti. Le performance delle fasce sono confrontabili principalmente all’interno dello stesso mercato.'}
      </p>
      <div
        className="mb-4 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={heatOption} style={{ height: 360 }} />
      </div>
      <h4 className="mb-2 text-sm font-medium text-[var(--lab-muted)]">
        Distribuzione globale (diagnostica coverage — non ROI universale)
      </h4>
      <div
        className="rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={distOption} style={{ height: 200 }} />
      </div>
      {byMarket.length > 0 ? (
        <div className="lab-table-wrap mt-3 overflow-x-auto">
          <table className="lab-table w-full text-xs">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Fascia</th>
                <th>N</th>
                <th>Hit</th>
                <th>ROI reale</th>
                <th>Reali</th>
              </tr>
            </thead>
            <tbody>
              {byMarket.slice(0, 40).map((r, i) => {
                const keys = rowKeys(r)
                return (
                  <tr key={i}>
                    <td>{keys[0] ?? '—'}</td>
                    <td>{keys[1] ?? '—'}</td>
                    <td>{String(r.sample_size ?? 0)}</td>
                    <td>
                      {r.hit_rate != null
                        ? `${(Number(r.hit_rate) * 100).toFixed(1)}%`
                        : '—'}
                    </td>
                    <td>
                      {r.real_roi_pct != null
                        ? `${formatNullableNumber(Number(r.real_roi_pct), 2)}%`
                        : '—'}
                    </td>
                    <td>{String(r.real_quote_count ?? 0)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
