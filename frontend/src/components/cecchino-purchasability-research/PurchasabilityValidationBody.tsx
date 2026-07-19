import type {
  PurchasabilityValidationFilters,
  PurchasabilityValidationHealth,
  PurchasabilityValidationJobStatus,
  PurchasabilityValidationReadiness,
  PurchasabilityValidationSummary,
} from '../../lib/cecchinoPurchasabilityValidationApi'
import { buildPurchasabilityValidationExportUrl } from '../../lib/cecchinoPurchasabilityValidationApi'

type Props = {
  health: PurchasabilityValidationHealth | null
  summary: PurchasabilityValidationSummary | null
  readiness: PurchasabilityValidationReadiness | null
  loading: boolean
  error: string | null
  job: PurchasabilityValidationJobStatus | null
  dateFrom: string
  dateTo: string
  marketKey: string
  bootstrapIterations: number
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onMarketKey: (v: string) => void
  onBootstrap: (v: number) => void
  onRefresh: () => void
  onStartJob: () => void
  filters: () => PurchasabilityValidationFilters
}

function fmt(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `${(Number(n) * 100).toFixed(1)}%`
}

function gateTone(pass: boolean | undefined, insufficient?: boolean): string {
  if (insufficient) return 'var(--muted, #888)'
  if (pass === true) return 'var(--ok, #2a7a3a)'
  if (pass === false) return 'var(--danger, #a33)'
  return 'var(--muted, #888)'
}

export function PurchasabilityValidationBody({
  health,
  summary,
  readiness,
  loading,
  error,
  job,
  dateFrom,
  dateTo,
  marketKey,
  bootstrapIterations,
  onDateFrom,
  onDateTo,
  onMarketKey,
  onBootstrap,
  onRefresh,
  onStartJob,
  filters,
}: Props) {
  const metrics = (summary?.metrics || {}) as Record<string, number | null>
  const span = (summary?.temporal_span || {}) as Record<string, unknown>
  const readinessStatus = readiness?.status || 'collecting_data'
  const jobRunning = job?.status === 'queued' || job?.status === 'running'
  const dataGates = readiness?.data_gates || {}
  const perfGates = readiness?.performance_gates || {}

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide opacity-60">Preview — non ufficiale</p>
        <h2 className="text-xl font-semibold">Validazione prospettica — Fase 5</h2>
        <p className="text-sm opacity-80 max-w-3xl">
          Monitoraggio della coorte pre-match persistita. candidate_2 resta in Preview:
          nessun promote automatico, nessun cambio pesi o integrazione Signals.
        </p>
        <div
          className="rounded-md border px-3 py-2 text-sm"
          style={{
            borderColor:
              readinessStatus === 'eligible_for_manual_promotion'
                ? 'var(--ok, #2a7a3a)'
                : 'var(--border, #333)',
          }}
        >
          Stato readiness: <strong>{readinessStatus}</strong>
          {readiness?.prima_data_teorica_promozione
            ? ` · prima data teorica ${String(readiness.prima_data_teorica_promozione)}`
            : null}
        </div>
      </header>

      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm">
          Da
          <input
            type="date"
            className="block mt-1 border rounded px-2 py-1 bg-transparent"
            value={dateFrom}
            onChange={(e) => onDateFrom(e.target.value)}
          />
        </label>
        <label className="text-sm">
          A
          <input
            type="date"
            className="block mt-1 border rounded px-2 py-1 bg-transparent"
            value={dateTo}
            onChange={(e) => onDateTo(e.target.value)}
          />
        </label>
        <label className="text-sm">
          Market
          <input
            className="block mt-1 border rounded px-2 py-1 bg-transparent"
            value={marketKey}
            placeholder="opzionale"
            onChange={(e) => onMarketKey(e.target.value)}
          />
        </label>
        <label className="text-sm">
          Bootstrap
          <input
            type="number"
            className="block mt-1 border rounded px-2 py-1 bg-transparent w-24"
            value={bootstrapIterations}
            min={10}
            max={2000}
            onChange={(e) => onBootstrap(Number(e.target.value) || 200)}
          />
        </label>
        <button
          type="button"
          className="border rounded px-3 py-1.5 text-sm"
          onClick={onRefresh}
          disabled={loading}
        >
          Aggiorna
        </button>
        <button
          type="button"
          className="border rounded px-3 py-1.5 text-sm"
          onClick={onStartJob}
          disabled={loading || jobRunning}
        >
          Job bootstrap
        </button>
        <a
          className="border rounded px-3 py-1.5 text-sm"
          href={buildPurchasabilityValidationExportUrl(filters())}
        >
          Export CSV
        </a>
      </div>

      {error ? (
        <p className="text-sm" style={{ color: 'var(--danger, #a33)' }}>
          {error}
        </p>
      ) : null}
      {loading || jobRunning ? (
        <p className="text-sm opacity-70">
          {jobRunning
            ? `Job ${job?.status}: ${job?.progress_message || job?.current_stage || '…'}`
            : 'Caricamento…'}
        </p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Coverage persistenza"
          value={fmtPct(health?.snapshot_persistence_coverage ?? null)}
        />
        <Stat label="Fixture settled" value={String(metrics.fixtures ?? '—')} />
        <Stat label="Righe settled" value={String(metrics.settled ?? '—')} />
        <Stat label="Win rate" value={fmtPct(metrics.win_rate ?? null)} />
        <Stat label="ROI %" value={fmt(metrics.roi_pct ?? null, 2)} />
        <Stat label="Realized margin" value={fmt(metrics.realized_margin ?? null)} />
        <Stat label="Zero score share" value={fmtPct(metrics.zero_score_share ?? null)} />
        <Stat
          label="Span giorni"
          value={String(span.span_days ?? '—')}
        />
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Score band</h3>
        <SimpleTable
          rows={summary?.by_score_band || []}
          columns={[
            ['score_band', 'Band'],
            ['rows', 'Righe'],
            ['fixtures', 'Fixture'],
            ['win_rate', 'WR'],
            ['realized_margin', 'Margin'],
            ['roi_pct', 'ROI'],
            ['average_phase_1', 'P1'],
            ['average_phase_2', 'P2'],
          ]}
        />
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Market family</h3>
        <SimpleTable
          rows={summary?.by_market_family || []}
          columns={[
            ['market_family', 'Family'],
            ['rows', 'Righe'],
            ['fixtures', 'Fixture'],
            ['win_rate', 'WR'],
            ['realized_margin', 'Margin'],
            ['roi_pct', 'ROI'],
          ]}
        />
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Phase 1 vs candidate</h3>
        <div className="text-sm space-y-1 opacity-90">
          <p>
            Δ Spearman residuale:{' '}
            {fmt(
              (summary?.phase1_comparison as { delta_point?: number } | undefined)
                ?.delta_point ?? null,
            )}
          </p>
          <p>
            Top/bottom residual spread:{' '}
            {fmt(
              (
                summary?.residual as {
                  top_bottom?: { residual_spread?: number }
                } | undefined
              )?.top_bottom?.residual_spread ?? null,
            )}
          </p>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Fold temporali</h3>
        <SimpleTable
          rows={summary?.temporal_folds || []}
          columns={[
            ['fold', 'Fold'],
            ['test_month', 'Mese test'],
            ['candidate_spearman', 'Cand ρ'],
            ['phase1_spearman', 'P1 ρ'],
            ['delta_candidate_minus_phase1', 'Δ'],
            ['positive_delta', 'Pos'],
          ]}
        />
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Gate data quality</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          {Object.entries(dataGates).map(([key, gate]) => (
            <div key={key} className="border rounded px-3 py-2 text-sm">
              <div className="flex justify-between gap-2">
                <span>{key}</span>
                <span style={{ color: gateTone(gate.pass as boolean | undefined) }}>
                  {gate.pass ? 'pass' : 'fail'}
                </span>
              </div>
              <div className="opacity-70 text-xs mt-1">
                valore={fmt(gate.value as number | null | undefined)} · soglia=
                {fmt(gate.threshold as number | null | undefined)}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-2">Gate performance</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          {(['test_a_residual_order', 'test_b_top_bottom', 'test_c_phase2_incremental'] as const).map(
            (key) => {
              const gate = (perfGates[key] || {}) as Record<string, unknown>
              return (
                <div key={key} className="border rounded px-3 py-2 text-sm">
                  <div className="flex justify-between gap-2">
                    <span>{key}</span>
                    <span
                      style={{
                        color: gateTone(
                          gate.pass as boolean | undefined,
                          gate.insufficient as boolean | undefined,
                        ),
                      }}
                    >
                      {gate.insufficient ? 'wait' : gate.pass ? 'pass' : 'fail'}
                    </span>
                  </div>
                </div>
              )
            },
          )}
        </div>
        {readiness?.recommended_next_step ? (
          <p className="text-sm mt-3 opacity-80">{readiness.recommended_next_step}</p>
        ) : null}
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border rounded px-3 py-2">
      <div className="text-xs opacity-60">{label}</div>
      <div className="text-lg font-medium">{value}</div>
    </div>
  )
}

function SimpleTable({
  rows,
  columns,
}: {
  rows: Array<Record<string, unknown>>
  columns: Array<[string, string]>
}) {
  if (!rows.length) {
    return <p className="text-sm opacity-60">Nessun dato settled nella coorte filtrata.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            {columns.map(([k, label]) => (
              <th key={k} className="text-left border-b px-2 py-1 font-medium opacity-70">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map(([k]) => {
                const v = row[k]
                let text = '—'
                if (typeof v === 'boolean') text = v ? 'sì' : 'no'
                else if (typeof v === 'number') text = Number.isInteger(v) ? String(v) : fmt(v)
                else if (v != null) text = String(v)
                return (
                  <td key={k} className="border-b px-2 py-1 whitespace-nowrap">
                    {text}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
