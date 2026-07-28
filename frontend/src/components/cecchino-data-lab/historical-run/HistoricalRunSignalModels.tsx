import ReactECharts from 'echarts-for-react'
import type {
  HistoricalRunSignalModelAnalytics,
  HistoricalRunSignalsDashboard,
  HistoricalSignalConsensusBucket,
  HistoricalSignalExportReconciliation,
  HistoricalSignalOverlapCell,
} from '../../../lib/cecchinoLabApi'

type Props = {
  models: HistoricalRunSignalModelAnalytics[]
  note?: string
  currentModelKey?: string
  opportunityRows?: number
  cellRows?: number
  concurrentActiveSignals?: Record<string, number>
  modelOverlapMatrix?: HistoricalSignalOverlapCell[]
  consensusDistribution?: HistoricalSignalConsensusBucket[]
  reconciliation?: HistoricalSignalExportReconciliation | null
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v}%`
}

function fmtHit(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function oppCount(m: HistoricalRunSignalModelAnalytics): number {
  return m.opportunity_count ?? m.model_active_opportunity_count ?? m.matches_with_signal ?? 0
}

function cellCount(m: HistoricalRunSignalModelAnalytics): number {
  return m.active_cell_row_count ?? m.signals_activated ?? 0
}

export function HistoricalRunSignalModels({
  models,
  note,
  currentModelKey = 'F',
  opportunityRows,
  cellRows,
  concurrentActiveSignals,
  modelOverlapMatrix,
  consensusDistribution,
  reconciliation,
}: Props) {
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

  const cellDist = Object.entries(concurrentActiveSignals ?? {}).sort(
    (a, b) => Number(a[0]) - Number(b[0]),
  )

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Segnali A–F</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        {note ??
          'Prestazioni su opportunità uniche. F = modello corrente. Nessun vincitore automatico.'}
      </p>

      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <div
          className="rounded-xl border p-3"
          style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
        >
          <h4 className="mb-1 text-sm font-semibold">A. Opportunità uniche</h4>
          <p className="mb-2 text-[11px] text-[var(--lab-muted)]">
            Chiave: run + snapshot + modello + mercato. Le metriche di ROI usano solo questo livello.
          </p>
          <ul className="space-y-1 text-xs">
            <li>
              Opportunità uniche (totale):{' '}
              <strong>{opportunityRows ?? reconciliation?.opportunity_rows ?? '—'}</strong>
            </li>
            <li>
              Celle medie / opportunità:{' '}
              <strong>
                {models[0]?.average_active_cells_per_opportunity != null
                  ? models
                      .map((m) => m.average_active_cells_per_opportunity)
                      .filter((v): v is number => v != null)
                      .slice(0, 1)[0]
                      ?.toFixed(2) ?? '—'
                  : '—'}
              </strong>
            </li>
          </ul>
        </div>
        <div
          className="rounded-xl border p-3"
          style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
        >
          <h4 className="mb-1 text-sm font-semibold">B. Celle attive</h4>
          <p className="mb-2 text-[11px] text-[var(--lab-muted)]">
            Diagnostica overlapping. Non sommare profitto o stake per cella: non sono scommesse
            indipendenti.
          </p>
          <ul className="space-y-1 text-xs">
            <li>
              Righe cella (totale): <strong>{cellRows ?? reconciliation?.cell_rows ?? '—'}</strong>
            </li>
            <li>
              Attribution: <strong>overlapping</strong>
            </li>
          </ul>
          {cellDist.length > 0 ? (
            <p className="mt-2 text-[11px] text-[var(--lab-muted)]">
              Distribuzione active_cell_count:{' '}
              {cellDist.map(([k, v]) => `${k}→${v}`).join(' · ')}
            </p>
          ) : null}
        </div>
      </div>

      <div
        className="mb-4 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={option} style={{ height: 260 }} />
      </div>

      <div className="lab-table-wrap mb-4 overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Modello</th>
              <th>Opportunità uniche</th>
              <th>Celle attive</th>
              <th>Celle medie</th>
              <th>Hit</th>
              <th>ROI reale</th>
              <th>ROI synth</th>
              <th>Sovrapposizione con F</th>
              <th>Uniche vs F</th>
              <th>Best mercato</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr
                key={m.model_key}
                style={
                  m.is_current_model ? { background: 'rgba(46,230,255,0.08)' } : undefined
                }
              >
                <td>
                  {m.model_short_label}
                  {m.is_current_model ? ` · F — modello corrente` : ''}
                </td>
                <td>{oppCount(m)}</td>
                <td>{cellCount(m)}</td>
                <td>
                  {m.average_active_cells_per_opportunity != null
                    ? m.average_active_cells_per_opportunity.toFixed(2)
                    : m.average_active_cells != null
                      ? m.average_active_cells.toFixed(2)
                      : '—'}
                </td>
                <td>{fmtHit(m.hit_rate)}</td>
                <td>{fmtPct(m.real_roi ?? m.real_roi_pct)}</td>
                <td>{fmtPct(m.synthetic_roi ?? m.synthetic_roi_pct)}</td>
                <td>
                  {m.is_current_model
                    ? '—'
                    : m.overlap_with_current_model_F_count != null
                      ? `${m.overlap_with_current_model_F_count}${
                          m.overlap_with_current_model_F_pct != null
                            ? ` (${m.overlap_with_current_model_F_pct}%)`
                            : ''
                        }`
                      : '—'}
                </td>
                <td>
                  {m.is_current_model
                    ? '—'
                    : (m.unique_vs_current_model_F_count ?? '—')}
                </td>
                <td>{m.market_best ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {consensusDistribution && consensusDistribution.length > 0 ? (
        <div className="mb-4">
          <h4 className="mb-2 text-sm font-semibold">Consenso per mercato</h4>
          <p className="mb-2 text-[11px] text-[var(--lab-muted)]">
            Non aggregare mercati diversi in un unico ROI di consenso.
          </p>
          <div className="lab-table-wrap overflow-x-auto">
            <table className="lab-table w-full text-xs">
              <thead>
                <tr>
                  <th>Mercato</th>
                  <th>N modelli</th>
                  <th>Opportunità</th>
                  <th>Hit</th>
                  <th>ROI reale</th>
                  <th>ROI synth</th>
                </tr>
              </thead>
              <tbody>
                {consensusDistribution.slice(0, 40).map((row) => (
                  <tr key={`${row.market_key}-${row.consensus_model_count}`}>
                    <td>{row.market_key}</td>
                    <td>{row.consensus_model_count}</td>
                    <td>{row.opportunity_count}</td>
                    <td>{fmtHit(row.hit_rate)}</td>
                    <td>{fmtPct(row.real_roi_pct)}</td>
                    <td>{fmtPct(row.synthetic_roi_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {modelOverlapMatrix && modelOverlapMatrix.length > 0 ? (
        <div className="mb-2">
          <h4 className="mb-2 text-sm font-semibold">
            Matrice sovrapposizione A–F (opportunità snapshot+mercato)
          </h4>
          <div className="lab-table-wrap overflow-x-auto">
            <table className="lab-table w-full text-xs">
              <thead>
                <tr>
                  <th>A</th>
                  <th>B</th>
                  <th>∩</th>
                  <th>∪</th>
                  <th>Jaccard</th>
                </tr>
              </thead>
              <tbody>
                {modelOverlapMatrix
                  .filter((r) => r.model_a !== r.model_b)
                  .slice(0, 30)
                  .map((r) => (
                    <tr key={`${r.model_a}-${r.model_b}`}>
                      <td>
                        {r.model_a}
                        {r.model_a === currentModelKey ? ' (corrente)' : ''}
                      </td>
                      <td>
                        {r.model_b}
                        {r.model_b === currentModelKey ? ' (corrente)' : ''}
                      </td>
                      <td>{r.intersection_count}</td>
                      <td>{r.union_count}</td>
                      <td>{fmtPct(r.jaccard_pct)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}

/** Helper per passare l’intero payload dashboard segnali. */
export function HistoricalRunSignalModelsFromDashboard({
  data,
}: {
  data: HistoricalRunSignalsDashboard
}) {
  return (
    <HistoricalRunSignalModels
      models={data.models}
      note={data.note}
      currentModelKey={data.current_model_key}
      opportunityRows={data.opportunity_rows}
      cellRows={data.cell_rows}
      concurrentActiveSignals={data.concurrent_active_signals}
      modelOverlapMatrix={data.model_overlap_matrix}
      consensusDistribution={data.consensus_distribution}
      reconciliation={data.signal_export_reconciliation}
    />
  )
}
