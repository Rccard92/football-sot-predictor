import { useCallback, useState } from 'react'
import type {
  CecchinoExpectedGoalEngineDiagnostics,
  CecchinoExpectedGoalEngineVariable,
} from '../../lib/cecchinoTodayApi'
import { backfillCurrentSeasonXg } from '../../lib/cecchinoTodayApi'
import { CecchinoApiRawInspectorPanel } from './CecchinoApiRawInspectorPanel'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  diagnostics?: CecchinoExpectedGoalEngineDiagnostics
  todayFixtureId?: number
  onDiagnosticsRefresh?: () => void
}

const XG_SOURCE = 'current_season_historical_xg'

const STATUS_LABELS: Record<string, string> = {
  available: 'Disponibile',
  partial: 'Parziale',
  missing: 'Mancante',
  not_supported: 'Non supportata',
  insufficient_sample: 'Campione basso',
}

const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'Alta',
  medium: 'Media',
  partial: 'Parziale',
  insufficient: 'Insufficiente',
}

const OVERVIEW_STATE: Record<string, string> = {
  high: 'Pronto',
  medium: 'Parziale',
  partial: 'Parziale',
  insufficient: 'Insufficiente',
}

function fmtVal(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return String(v)
}

function statusBadgeClass(status?: string): string {
  switch (status) {
    case 'available':
      return 'bg-teal-100 text-teal-900'
    case 'insufficient_sample':
    case 'partial':
      return 'bg-amber-100 text-amber-900'
    case 'not_supported':
      return 'bg-slate-200 text-slate-700'
    default:
      return 'bg-red-100 text-red-900'
  }
}

function readinessLabel(flag?: boolean): string {
  if (flag === true) return 'Sì'
  if (flag === false) return 'No'
  return '—'
}

function isXgRow(row: CecchinoExpectedGoalEngineVariable): boolean {
  return Boolean(row.key?.includes('xg_') && row.source === XG_SOURCE)
}

function fmtSource(row: CecchinoExpectedGoalEngineVariable): string {
  if (isXgRow(row)) {
    return 'xG storico stagione corrente'
  }
  return row.source ?? '—'
}

function fmtSourceField(row: CecchinoExpectedGoalEngineVariable): string {
  if (isXgRow(row)) {
    return 'fixture_statistics → expected_goals'
  }
  return row.source_field ?? '—'
}

function fmtSample(row: CecchinoExpectedGoalEngineVariable): string {
  if (row.key?.includes('xg_') && row.sample_size != null) {
    return `${row.sample_size} partite precedenti con xG`
  }
  return row.sample_size != null ? String(row.sample_size) : '—'
}

function fmtNotes(row: CecchinoExpectedGoalEngineVariable): string {
  const parts: string[] = []
  if (row.note) parts.push(row.note)
  if (row.warnings?.length) parts.push(...row.warnings)
  return parts.join(' · ') || '—'
}

function VariableTable({ rows }: { rows: CecchinoExpectedGoalEngineVariable[] }) {
  if (!rows.length) return null
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="px-2 py-2 font-medium">Variabile</th>
            <th className="px-2 py-2 font-medium">Peso</th>
            <th className="px-2 py-2 font-medium">Stato</th>
            <th className="px-2 py-2 font-medium">Valore</th>
            <th className="px-2 py-2 font-medium">Fonte</th>
            <th className="px-2 py-2 font-medium">Campo sorgente</th>
            <th className="px-2 py-2 font-medium">Campione</th>
            <th className="px-2 py-2 font-medium">Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-slate-100 align-top">
              <td className="px-2 py-2 font-medium text-slate-800">{row.label ?? row.key}</td>
              <td className="px-2 py-2 tabular-nums">{row.weight != null ? row.weight.toFixed(2) : '—'}</td>
              <td className="px-2 py-2">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusBadgeClass(row.availability_status)}`}
                >
                  {STATUS_LABELS[row.availability_status ?? ''] ?? row.availability_status ?? '—'}
                </span>
              </td>
              <td className="px-2 py-2 tabular-nums">{fmtVal(row.value)}</td>
              <td className="px-2 py-2">{fmtSource(row)}</td>
              <td className="max-w-[160px] truncate px-2 py-2" title={fmtSourceField(row)}>
                {fmtSourceField(row)}
              </td>
              <td className="px-2 py-2 tabular-nums">{fmtSample(row)}</td>
              <td className="max-w-[200px] px-2 py-2 text-slate-600">{fmtNotes(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BlockAccordion({
  title,
  rows,
}: {
  title: string
  rows: CecchinoExpectedGoalEngineVariable[]
}) {
  return (
    <details className="rounded-lg border border-slate-200 bg-white text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
        {title} ({rows.length})
      </summary>
      <div className="border-t border-slate-200 px-2 py-3">
        <VariableTable rows={rows} />
      </div>
    </details>
  )
}

export function CecchinoExpectedGoalEngineDiagnosticsPanel({
  diagnostics,
  todayFixtureId,
  onDiagnosticsRefresh,
}: Props) {
  const [recalcLoading, setRecalcLoading] = useState(false)
  const [recalcMessage, setRecalcMessage] = useState<string | null>(null)

  const handleRecalcXg = useCallback(async () => {
    if (!todayFixtureId) return
    setRecalcLoading(true)
    setRecalcMessage(null)
    try {
      const res = await backfillCurrentSeasonXg(todayFixtureId, { forceRefresh: true })
      if (res.status === 'ok' || res.status === 'cached') {
        setRecalcMessage('Profilo xG aggiornato.')
        onDiagnosticsRefresh?.()
      } else {
        setRecalcMessage(res.message ?? 'Ricalcolo non riuscito.')
      }
    } catch (err) {
      setRecalcMessage(err instanceof Error ? err.message : 'Errore di rete.')
    } finally {
      setRecalcLoading(false)
    }
  }, [todayFixtureId, onDiagnosticsRefresh])

  if (!diagnostics || diagnostics.status !== 'available' || !diagnostics.blocks) {
    return (
      <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
        <h3 className={todaySectionTitle}>Expected Goal Engine — Diagnostica Variabili</h3>
        <p className={todaySectionSubtitle}>Audit variabili per il futuro motore Expected Goal.</p>
        <p className="mt-3 text-sm text-slate-500">Dati diagnostici non disponibili.</p>
        <CecchinoApiRawInspectorPanel todayFixtureId={todayFixtureId} />
      </section>
    )
  }

  const { coverage, engine_readiness, blocks, xg_profiles, xg_api_usage, warnings } = diagnostics
  const confidence = coverage?.confidence ?? 'insufficient'
  const overviewState = coverage?.engine_ready ? 'Pronto' : OVERVIEW_STATE[confidence] ?? 'Insufficiente'
  const productionRows = blocks.production_goal ?? []
  const xgRows = productionRows.filter(isXgRow)
  const hasXgWarning = xgRows.some(
    (r) => r.availability_status === 'missing' || r.availability_status === 'insufficient_sample',
  )

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Expected Goal Engine — Diagnostica Variabili</h3>
        <p className={todaySectionSubtitle}>
          Questa sezione non genera ancora goal attesi. Serve a verificare quali variabili sono
          disponibili per costruire il motore Expected Goal.
        </p>
      </div>

      <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-4 text-sm text-violet-950">
        <p className="text-xs font-semibold uppercase tracking-wide opacity-80">Expected Goal Engine</p>
        <p className="mt-1 text-lg font-bold">Diagnostica Variabili</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <div>
            <dt className="text-xs opacity-70">Stato</dt>
            <dd className="font-semibold">{overviewState}</dd>
          </div>
          <div>
            <dt className="text-xs opacity-70">Variabili obbligatorie</dt>
            <dd className="font-semibold tabular-nums">
              {coverage?.required_available ?? 0}/{coverage?.required_total ?? 15}
            </dd>
          </div>
          <div>
            <dt className="text-xs opacity-70">Correttori avanzati</dt>
            <dd className="font-semibold tabular-nums">
              {coverage?.advanced_available ?? 0}/{coverage?.advanced_total ?? 5}
            </dd>
          </div>
          <div>
            <dt className="text-xs opacity-70">Confidence</dt>
            <dd className="font-semibold">{CONFIDENCE_LABELS[confidence] ?? confidence}</dd>
          </div>
          <div>
            <dt className="text-xs opacity-70">Engine ready</dt>
            <dd className="font-semibold">{coverage?.engine_ready ? 'Sì' : 'No'}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-950">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide opacity-80">xG storico automatico</p>
            <p className="mt-1 text-sm">
              Calcolato automaticamente sulle partite precedenti della stagione corrente. La partita
              analizzata è esclusa per evitare leakage.
            </p>
            {xg_api_usage && (
              <p className="mt-2 text-xs opacity-80">
                Cache: {xg_api_usage.cache_hits ?? 0} hit · API: {xg_api_usage.external_calls_made ?? 0}{' '}
                chiamate · {xg_api_usage.fixtures_checked ?? 0} fixture controllate
              </p>
            )}
          </div>
          {todayFixtureId != null && (
            <button
              type="button"
              onClick={() => void handleRecalcXg()}
              disabled={recalcLoading}
              className="shrink-0 rounded-md border border-teal-300 bg-white px-3 py-1.5 text-xs font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
            >
              {recalcLoading ? 'Ricalcolo…' : 'Ricalcola xG storico'}
            </button>
          )}
        </div>
        {recalcMessage && <p className="mt-2 text-xs">{recalcMessage}</p>}
        {hasXgWarning && (
          <p className="mt-2 text-xs font-medium text-amber-800">
            Attenzione: campione xG insufficiente o mancante — verificare storico partite e cache
            statistiche.
          </p>
        )}
        {(warnings?.length ?? 0) > 0 && (
          <p className="mt-2 text-xs text-amber-800">Warning pipeline: {(warnings ?? []).join(', ')}</p>
        )}
        {xg_profiles?.anti_leakage && (
          <p className="mt-2 text-xs opacity-80">
            Anti-leakage: cutoff{' '}
            {String(
              (xg_profiles.anti_leakage as { fixture_date_cutoff?: string }).fixture_date_cutoff ??
                '—',
            )}
          </p>
        )}
      </div>

      <BlockAccordion title="Produzione Goal" rows={productionRows} />
      <BlockAccordion title="Distribuzione Temporale" rows={blocks.temporal_distribution ?? []} />
      <BlockAccordion title="Correttori Avanzati" rows={blocks.advanced_correctors ?? []} />

      {engine_readiness && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Cosa possiamo calcolare?
          </p>
          <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="flex justify-between gap-2">
              <dt>Goal Attesi Finali</dt>
              <dd className="font-medium">{readinessLabel(engine_readiness.can_compute_expected_goals_ft)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Goal Attesi Primo Tempo</dt>
              <dd className="font-medium">{readinessLabel(engine_readiness.can_compute_expected_goals_ht)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Goal Casa/Ospite</dt>
              <dd className="font-medium">
                {readinessLabel(engine_readiness.can_compute_home_away_expected_goals)}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Probabilità Over</dt>
              <dd className="font-medium">{readinessLabel(engine_readiness.can_compute_over_probabilities)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>GG/NG</dt>
              <dd className="font-medium">{readinessLabel(engine_readiness.can_compute_gg_ng)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Risultati compatibili</dt>
              <dd className="font-medium">{readinessLabel(engine_readiness.can_compute_scorelines)}</dd>
            </div>
          </dl>
          {(engine_readiness.missing_critical_fields?.length ?? 0) > 0 && (
            <p className="mt-3 text-xs text-slate-600">
              Campi critici mancanti: {engine_readiness.missing_critical_fields?.join(', ')}
            </p>
          )}
        </div>
      )}

      <details className="rounded-lg border border-slate-200 bg-white text-sm">
        <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
          Payload diagnostico JSON
        </summary>
        <pre className="max-h-96 overflow-auto border-t border-slate-200 bg-slate-950 p-4 text-xs text-slate-100">
          {JSON.stringify(diagnostics, null, 2)}
        </pre>
      </details>

      <CecchinoApiRawInspectorPanel todayFixtureId={todayFixtureId} />
    </section>
  )
}
