import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { HistoricalRunSectionError } from '../components/cecchino-data-lab/historical-run/HistoricalRunSectionError'
import { HistoricalRunSignalModels } from '../components/cecchino-data-lab/historical-run/HistoricalRunSignalModels'
import { HistoricalKpiSkeleton } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiSkeleton'
import {
  getHistoricalSignalsAfActivations,
  getHistoricalSignalsAfSummary,
  type HistoricalSignalsAfActivation,
  type HistoricalSignalsAfActivationsResponse,
  type HistoricalSignalsAfFilters,
  type HistoricalSignalsAfSummary,
} from '../lib/cecchinoLabApi'

type SectionState<T> = { data: T | null; error: string | null; loading: boolean }

const ACTIVATIONS_LIMIT = 50
const MODEL_KEYS = ['A', 'B', 'C', 'D', 'E', 'F'] as const

const DEFAULT_FILTERS: HistoricalSignalsAfFilters = {
  quote_type: 'real',
}

function parseFiltersFromSearch(search: string): HistoricalSignalsAfFilters {
  const params = new URLSearchParams(search)
  const quoteRaw = params.get('quote_type')
  const quote_type: HistoricalSignalsAfFilters['quote_type'] =
    quoteRaw === 'derived' || quoteRaw === 'all' ? quoteRaw : 'real'
  const modelRaw = params.get('model_key')
  const model_key =
    modelRaw && MODEL_KEYS.includes(modelRaw.toUpperCase() as (typeof MODEL_KEYS)[number])
      ? modelRaw.toUpperCase()
      : undefined
  const consensusRaw = params.get('minimum_consensus_models')
  let minimum_consensus_models: number | undefined
  if (consensusRaw) {
    const n = Number(consensusRaw)
    if (Number.isFinite(n) && n >= 1) minimum_consensus_models = Math.round(n)
  }
  const onlyF = params.get('only_current_model_F')
  return {
    competition: params.get('competition') || undefined,
    date_from: params.get('date_from') || undefined,
    date_to: params.get('date_to') || undefined,
    model_key,
    market_key: params.get('market_key') || undefined,
    quote_type,
    minimum_consensus_models,
    only_current_model_F: onlyF === 'true' || onlyF === '1',
  }
}

function filtersToSearchParams(filters: HistoricalSignalsAfFilters): URLSearchParams {
  const params = new URLSearchParams()
  const merged = { ...DEFAULT_FILTERS, ...filters }
  for (const [k, v] of Object.entries(merged)) {
    if (v === false) continue
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  return params
}

function idleSection<T>(): SectionState<T> {
  return { data: null, error: null, loading: false }
}

export function CecchinoLabHistoricalSignalsAfPage() {
  const { runId: runIdParam } = useParams()
  const runId = Number(runIdParam)
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(
    () => parseFiltersFromSearch(searchParams.toString()),
    [searchParams],
  )

  const [summary, setSummary] = useState<SectionState<HistoricalSignalsAfSummary>>({
    data: null,
    error: null,
    loading: true,
  })
  const [activations, setActivations] = useState<
    SectionState<HistoricalSignalsAfActivationsResponse>
  >(idleSection())
  const [activationsOffset, setActivationsOffset] = useState(0)

  const setFilters = useCallback(
    (next: HistoricalSignalsAfFilters) => {
      setActivationsOffset(0)
      setSearchParams(filtersToSearchParams(next), { replace: true })
    },
    [setSearchParams],
  )

  const loadActivations = useCallback(
    async (signal: AbortSignal, offset: number) => {
      setActivations((s) => ({ ...s, loading: true, error: null }))
      try {
        const data = await getHistoricalSignalsAfActivations(
          runId,
          filters,
          { limit: ACTIVATIONS_LIMIT, offset },
          { signal },
        )
        if (signal.aborted) return
        setActivations({ data, error: null, loading: false })
      } catch (e) {
        if (signal.aborted) return
        setActivations({
          data: null,
          error: e instanceof Error ? e.message : 'Errore attivazioni A–F',
          loading: false,
        })
      }
    },
    [runId, filters],
  )

  const loadAll = useCallback(
    async (signal: AbortSignal) => {
      setSummary({ data: null, error: null, loading: true })
      setActivations(idleSection())
      try {
        const data = await getHistoricalSignalsAfSummary(runId, filters, { signal })
        if (signal.aborted) return
        setSummary({ data, error: null, loading: false })
        await loadActivations(signal, 0)
      } catch (e) {
        if (signal.aborted) return
        setSummary({
          data: null,
          error: e instanceof Error ? e.message : 'Errore riepilogo A–F',
          loading: false,
        })
      }
    },
    [runId, filters, loadActivations],
  )

  useEffect(() => {
    if (!Number.isFinite(runId)) return
    const controller = new AbortController()
    void loadAll(controller.signal)
    return () => controller.abort()
  }, [runId, loadAll])

  if (!Number.isFinite(runId)) {
    return (
      <CecchinoLabShell className="p-6">
        <p className="text-[var(--lab-err)]">Run ID non valido.</p>
        <Link to="/cecchino-lab" className="mt-2 inline-block text-sm text-[var(--lab-cyan)]">
          ← Cecchino Lab
        </Link>
      </CecchinoLabShell>
    )
  }

  const competitions = useMemo(() => {
    return [] as string[]
  }, [])

  return (
    <CecchinoLabShell className="p-4 md:p-6">
      <div className="space-y-6" data-testid="historical-signals-af-page">
        <header className="space-y-2">
          <Link
            to="/cecchino-lab"
            className="text-sm text-[var(--lab-cyan)] underline-offset-2 hover:underline"
          >
            ← Cecchino Lab
          </Link>
          <h1 className="text-2xl font-semibold">Segnali A–F</h1>
          {summary.data?.run ? (
            <p className="text-sm text-[var(--lab-muted)]">
              Run #{summary.data.run.run_id} · {summary.data.run.season_label} ·{' '}
              {summary.data.run.status} · scope {summary.data.run.scope}
            </p>
          ) : null}
          <p className="text-xs text-[var(--lab-muted)]">
            Le celle attive non sono scommesse indipendenti. F = modello corrente.
          </p>
        </header>

        <SignalsAfFiltersBar
          filters={filters}
          competitions={competitions}
          onChange={setFilters}
          onReset={() => setFilters({ quote_type: 'real' })}
        />

        {summary.loading && !summary.data ? (
          <HistoricalKpiSkeleton rows={3} />
        ) : summary.error ? (
          <HistoricalRunSectionError
            title="Errore riepilogo Segnali A–F"
            error={summary.error}
            onRetry={() => {
              const c = new AbortController()
              void loadAll(c.signal)
            }}
          />
        ) : summary.data ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard label="Opportunità uniche" value={summary.data.unique_opportunities} />
              <StatCard label="Celle attive (diagnostica)" value={summary.data.active_cells} />
              <StatCard
                label="Filtrate (dettaglio)"
                value={summary.data.filtered_opportunity_count}
              />
            </div>
            <p className="text-xs text-[var(--lab-muted)]">
              Quote reali: {summary.data.quote_buckets.real} · derivate:{' '}
              {summary.data.quote_buckets.derived} (non sommate)
            </p>

            <div data-testid="signals-af-model-cards">
              <HistoricalRunSignalModels
                models={summary.data.models as never}
                note={summary.data.note}
                currentModelKey={summary.data.current_model_key}
                opportunityRows={summary.data.unique_opportunities}
                cellRows={summary.data.active_cells}
                concurrentActiveSignals={Object.fromEntries(
                  Object.entries(summary.data.concurrent_active_signals).map(([k, v]) => [
                    k,
                    v,
                  ]),
                )}
                modelOverlapMatrix={summary.data.model_overlap_matrix}
                consensusDistribution={
                  summary.data.consensus_distribution as never
                }
                reconciliation={
                  (summary.data.signal_export_reconciliation as never) ?? null
                }
                onModelClick={(modelKey) =>
                  setFilters({
                    ...filters,
                    model_key: filters.model_key === modelKey ? undefined : modelKey,
                  })
                }
                activeModelKey={filters.model_key}
              />
            </div>
          </>
        ) : null}

        {activations.loading && !activations.data ? (
          <HistoricalKpiSkeleton rows={4} />
        ) : activations.error ? (
          <HistoricalRunSectionError
            title="Errore dettaglio opportunità"
            error={activations.error}
            onRetry={() => {
              const c = new AbortController()
              void loadActivations(c.signal, activationsOffset)
            }}
          />
        ) : activations.data ? (
          <SignalsAfActivationsTable
            items={activations.data.items}
            total={activations.data.total}
            offset={activations.data.offset}
            limit={ACTIVATIONS_LIMIT}
            onPage={(offset) => {
              setActivationsOffset(offset)
              const c = new AbortController()
              void loadActivations(c.signal, offset)
            }}
          />
        ) : null}
      </div>
    </CecchinoLabShell>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <div className="text-xs text-[var(--lab-muted)]">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  )
}

function SignalsAfFiltersBar({
  filters,
  competitions,
  onChange,
  onReset,
}: {
  filters: HistoricalSignalsAfFilters
  competitions: string[]
  onChange: (next: HistoricalSignalsAfFilters) => void
  onReset: () => void
}) {
  function setField(key: keyof HistoricalSignalsAfFilters, value: string) {
    if (key === 'only_current_model_F') {
      onChange({ ...filters, only_current_model_F: value === 'true' })
      return
    }
    if (key === 'minimum_consensus_models') {
      const n = value ? Number(value) : undefined
      onChange({
        ...filters,
        minimum_consensus_models: n != null && Number.isFinite(n) ? n : undefined,
      })
      return
    }
    onChange({ ...filters, [key]: value || undefined })
  }

  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      data-testid="signals-af-filters"
    >
      <div className="mb-2 flex justify-between gap-2">
        <span className="text-xs font-medium text-[var(--lab-cyan)]">Filtri Segnali A–F</span>
        <button type="button" className="lab-btn-ghost text-xs" onClick={onReset}>
          Reset
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
        <label className="text-[11px] text-[var(--lab-muted)]">
          Campionato
          <input
            className="lab-input mt-0.5 w-full text-sm"
            value={filters.competition ?? ''}
            list="af-competitions"
            onChange={(e) => setField('competition', e.target.value)}
          />
          <datalist id="af-competitions">
            {competitions.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          Da
          <input
            className="lab-input mt-0.5 w-full text-sm"
            type="date"
            value={filters.date_from ?? ''}
            onChange={(e) => setField('date_from', e.target.value)}
          />
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          A
          <input
            className="lab-input mt-0.5 w-full text-sm"
            type="date"
            value={filters.date_to ?? ''}
            onChange={(e) => setField('date_to', e.target.value)}
          />
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          Modello
          <select
            className="lab-input mt-0.5 w-full text-sm"
            value={filters.model_key ?? ''}
            onChange={(e) => setField('model_key', e.target.value)}
          >
            <option value="">Tutti</option>
            {MODEL_KEYS.map((k) => (
              <option key={k} value={k}>
                {k}
                {k === 'F' ? ' (corrente)' : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          Mercato
          <input
            className="lab-input mt-0.5 w-full text-sm"
            value={filters.market_key ?? ''}
            onChange={(e) => setField('market_key', e.target.value)}
            placeholder="es. HOME"
          />
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          Tipo quota
          <select
            className="lab-input mt-0.5 w-full text-sm"
            value={filters.quote_type ?? 'real'}
            onChange={(e) => setField('quote_type', e.target.value)}
          >
            <option value="real">Quote reali</option>
            <option value="derived">Quote derivate</option>
            <option value="all">Tutte (separate)</option>
          </select>
        </label>
        <label className="text-[11px] text-[var(--lab-muted)]">
          Consenso minimo
          <input
            className="lab-input mt-0.5 w-full text-sm"
            type="number"
            min={1}
            max={6}
            value={filters.minimum_consensus_models ?? ''}
            onChange={(e) => setField('minimum_consensus_models', e.target.value)}
          />
        </label>
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-[var(--lab-muted)]">
        <input
          type="checkbox"
          checked={Boolean(filters.only_current_model_F)}
          onChange={(e) =>
            onChange({ ...filters, only_current_model_F: e.target.checked })
          }
        />
        Solo modello corrente F
      </label>
    </div>
  )
}

function SignalsAfActivationsTable({
  items,
  total,
  offset,
  limit,
  onPage,
}: {
  items: HistoricalSignalsAfActivation[]
  total: number
  offset: number
  limit: number
  onPage: (offset: number) => void
}) {
  const page = Math.floor(offset / limit) + 1
  const totalPages = Math.max(1, Math.ceil(total / limit))
  return (
    <section data-testid="signals-af-activations">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">Dettaglio opportunità</h3>
        <div className="text-xs text-[var(--lab-muted)]">
          {total} totali · pagina {page}/{totalPages}
        </div>
      </div>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Una riga per opportunità unica. Le celle attive non sono scommesse indipendenti.
      </p>
      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Kickoff</th>
              <th>Partita</th>
              <th>Campionato</th>
              <th>Modello</th>
              <th>Mercato</th>
              <th>Celle</th>
              <th>Consenso</th>
              <th>Quota</th>
              <th>Tipo</th>
              <th>Esito</th>
              <th>Profitto</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={11} className="text-[var(--lab-muted)]">
                  Nessuna opportunità per i filtri correnti.
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.opportunity_id}>
                  <td>{row.kickoff_at?.slice(0, 16).replace('T', ' ') ?? '—'}</td>
                  <td>
                    {row.home_team ?? '—'} — {row.away_team ?? '—'}
                  </td>
                  <td>{row.competition_name ?? '—'}</td>
                  <td>
                    {row.model_key}
                    {row.model_key === 'F' ? ' ★' : ''}
                  </td>
                  <td>{row.market_label || row.market_key || '—'}</td>
                  <td>{row.active_cell_count}</td>
                  <td>{row.consensus_model_count ?? '—'}</td>
                  <td>{row.quota_book ?? '—'}</td>
                  <td>{row.quote_type ?? '—'}</td>
                  <td>
                    {row.won === true ? 'Vinto' : row.won === false ? 'Perso' : '—'}
                  </td>
                  <td>
                    {row.quote_type === 'derived'
                      ? (row.profit_1u_synthetic ?? '—')
                      : (row.profit_1u_real ?? '—')}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          className="lab-btn-ghost text-xs"
          disabled={offset <= 0}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Precedente
        </button>
        <button
          type="button"
          className="lab-btn-ghost text-xs"
          disabled={offset + limit >= total}
          onClick={() => onPage(offset + limit)}
        >
          Successiva
        </button>
      </div>
    </section>
  )
}
