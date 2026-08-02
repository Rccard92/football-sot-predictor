import { Link } from 'react-router-dom'
import {
  formatNullableNumber,
  type HistoricalRunOfficialPurchasability,
} from '../../../lib/cecchinoLabApi'

type Props = {
  data: HistoricalRunOfficialPurchasability
  runId: number
}

function formatRoi(roi: number | null | undefined): string {
  if (roi == null || Number.isNaN(Number(roi))) return '—'
  return `${Number(roi).toFixed(2)}%`
}

function replayCtaPath(data: HistoricalRunOfficialPurchasability, runId: number): string {
  if (data.cta?.path) return data.cta.path
  return `/cecchino-lab/purchasability-replay?run_id=${runId}`
}

export function HistoricalRunPurchasability({ data, runId }: Props) {
  if (data.status === 'unavailable') {
    const path = replayCtaPath(data, runId)
    const label = data.cta?.label || 'Verifica o avvia replay Acquistabilità'
    return (
      <section data-testid="historical-run-purchasability-v3">
        <h3 className="mb-2 text-lg font-semibold">Acquistabilità V3</h3>
        <p
          className="mb-3 rounded-lg border px-3 py-2 text-sm"
          style={{
            borderColor: 'var(--lab-warn)',
            color: 'var(--lab-warn)',
            background: 'rgba(224,122,95,0.08)',
          }}
          data-testid="purchasability-v3-unavailable"
        >
          Acquistabilità V3 non disponibile
          {data.message ? (
            <span className="mt-1 block text-xs opacity-90">{data.message}</span>
          ) : null}
        </p>
        <Link
          to={path}
          className="inline-flex text-sm font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
          data-testid="purchasability-v3-cta"
        >
          {label}
        </Link>
      </section>
    )
  }

  const byMarket = data.by_market || {}
  const marketKeys = Object.keys(byMarket).sort()

  return (
    <section data-testid="historical-run-purchasability-v3">
      <div className="mb-2 flex flex-wrap items-baseline gap-2">
        <h3 className="text-lg font-semibold">Acquistabilità V3</h3>
        <span className="text-[11px] text-[var(--lab-muted)]">V3 · Replay</span>
      </div>

      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Replay ID {data.replay_id ?? '—'} · stato {data.replay_status || data.status || '—'} ·
        formula {data.formula_version || '—'}
      </p>

      <div
        className="mb-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3"
        data-testid="purchasability-v3-summary"
      >
        <div>Risultati persistiti: {data.results_persisted ?? '—'}</div>
        <div>Valutazioni: {data.evaluations_total ?? '—'}</div>
        <div>Scored: {data.scored ?? '—'}</div>
        <div>Gate falliti: {data.gate_failed ?? '—'}</div>
        <div>Unavailable: {data.unavailable ?? '—'}</div>
        <div>Quote reali: {data.real_quote_count ?? '—'}</div>
        <div>Quote derivate: {data.derived_quote_count ?? '—'}</div>
        <div data-testid="purchasability-v3-recon">
          Riconciliazione: {data.reconciliation_status || data.reconciliation?.status || '—'}
        </div>
        <div data-testid="purchasability-v3-roi-real">
          ROI reale: {formatRoi(data.performance_real?.roi_pct)}
          {data.performance_real?.profit_units != null
            ? ` · profitto ${formatNullableNumber(data.performance_real.profit_units, 2)}`
            : ''}
        </div>
        <div data-testid="purchasability-v3-roi-synthetic">
          ROI sintetico: {formatRoi(data.performance_synthetic?.roi_pct)}
          {data.performance_synthetic?.profit_units != null
            ? ` · profitto ${formatNullableNumber(data.performance_synthetic.profit_units, 2)}`
            : ''}
        </div>
      </div>

      {marketKeys.length > 0 ? (
        <div className="lab-table-wrap mb-2 overflow-x-auto">
          <table className="lab-table w-full text-xs">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Valutazioni</th>
                <th>Scored</th>
                <th>Gate falliti</th>
                <th>Unavailable</th>
                <th>Quote reali</th>
                <th>Quote derivate</th>
              </tr>
            </thead>
            <tbody>
              {marketKeys.map((mk) => {
                const m = byMarket[mk] || {}
                return (
                  <tr key={mk}>
                    <td>{mk}</td>
                    <td>{String(m.evaluations_total ?? '—')}</td>
                    <td>{String(m.scored ?? '—')}</td>
                    <td>{String(m.gate_failed ?? '—')}</td>
                    <td>{String(m.unavailable ?? '—')}</td>
                    <td>{String(m.real_quote ?? m.real ?? '—')}</td>
                    <td>{String(m.derived_quote ?? m.synthetic ?? '—')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-[var(--lab-muted)]">Nessun dettaglio per mercato.</p>
      )}
    </section>
  )
}
