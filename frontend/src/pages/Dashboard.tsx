import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  DEFAULT_SEASON,
  getBacktestBySide,
  getBacktestByTeam,
  getBacktestSummary,
  getDashboard,
  getIngestionRuns,
  getPredictionSummary,
  runBuildSotFeatures,
  runGenerateSotPredictions,
  runSotBacktest,
  type BacktestBySideListResponse,
  type BacktestByTeamListResponse,
  type BacktestNumericSummaryResponse,
  type IngestionRunSummary,
  type IngestionRunsResponse,
  type SerieADashboardResponse,
  type SotPredictionsSeasonSummaryResponse,
} from '../lib/api'

const SEASON = DEFAULT_SEASON

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('it-IT', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

function formatPercent(value: number): string {
  return `${value.toLocaleString('it-IT', { maximumFractionDigits: 2, minimumFractionDigits: 0 })}%`
}

function formatNum(value: number, decimals = 2): string {
  return value.toLocaleString('it-IT', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  })
}

function SectionCard({
  title,
  children,
  className = '',
}: {
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm ${className}`}
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-slate-200/80 ${className}`}
      aria-hidden
    />
  )
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-200/80 bg-red-50/80 px-4 py-3 text-sm text-red-900">
      {message}
    </div>
  )
}

type Slice<T> = { loading: boolean; data: T | null; error: string | null }

function emptySlice<T>(): Slice<T> {
  return { loading: true, data: null, error: null }
}

function pickSide(rows: BacktestBySideListResponse['sides'], key: 'home' | 'away') {
  const k = key.toLowerCase()
  return rows.find((r) => String(r.side).toLowerCase() === k) ?? null
}

function ingestionStatusClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'success' || s === 'completed' || s === 'ok') {
    return 'bg-emerald-100 text-emerald-800'
  }
  if (s === 'failed' || s === 'error') {
    return 'bg-rose-100 text-rose-800'
  }
  return 'bg-slate-100 text-slate-600'
}

function adminSuccessMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const o = payload as Record<string, unknown>
    if (typeof o.message === 'string' && o.message.trim()) return o.message
  }
  return fallback
}

type AdminActionState = { loading: boolean; ok: boolean | null; msg: string | null }

const ADMIN_IDLE: AdminActionState = { loading: false, ok: null, msg: null }

export function Dashboard() {
  const [dashboard, setDashboard] = useState<Slice<SerieADashboardResponse>>(emptySlice)
  const [predSummary, setPredSummary] = useState<Slice<SotPredictionsSeasonSummaryResponse>>(
    emptySlice,
  )
  const [btSummary, setBtSummary] = useState<Slice<BacktestNumericSummaryResponse>>(emptySlice)
  const [btTeam, setBtTeam] = useState<Slice<BacktestByTeamListResponse>>(emptySlice)
  const [btSide, setBtSide] = useState<Slice<BacktestBySideListResponse>>(emptySlice)
  const [ingest, setIngest] = useState<Slice<IngestionRunsResponse>>(emptySlice)

  const [pageInit, setPageInit] = useState(true)
  const [silentBusy, setSilentBusy] = useState(false)

  const [adminFeatures, setAdminFeatures] = useState<AdminActionState>(ADMIN_IDLE)
  const [adminPred, setAdminPred] = useState<AdminActionState>(ADMIN_IDLE)
  const [adminBt, setAdminBt] = useState<AdminActionState>(ADMIN_IDLE)

  const loadAll = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true
    if (!silent) {
      setDashboard({ loading: true, data: null, error: null })
      setPredSummary({ loading: true, data: null, error: null })
      setBtSummary({ loading: true, data: null, error: null })
      setBtTeam({ loading: true, data: null, error: null })
      setBtSide({ loading: true, data: null, error: null })
      setIngest({ loading: true, data: null, error: null })
    } else {
      setSilentBusy(true)
    }

    const results = await Promise.allSettled([
      getDashboard(SEASON),
      getPredictionSummary(SEASON),
      getBacktestSummary(SEASON),
      getBacktestByTeam(SEASON),
      getBacktestBySide(SEASON),
      getIngestionRuns(),
    ])

    const err = (e: unknown) => (e instanceof Error ? e.message : String(e))

    const [r0, r1, r2, r3, r4, r5] = results

    setDashboard(
      r0.status === 'fulfilled'
        ? { loading: false, data: r0.value, error: null }
        : { loading: false, data: null, error: err(r0.reason) },
    )
    setPredSummary(
      r1.status === 'fulfilled'
        ? { loading: false, data: r1.value, error: null }
        : { loading: false, data: null, error: err(r1.reason) },
    )
    setBtSummary(
      r2.status === 'fulfilled'
        ? { loading: false, data: r2.value, error: null }
        : { loading: false, data: null, error: err(r2.reason) },
    )
    setBtTeam(
      r3.status === 'fulfilled'
        ? { loading: false, data: r3.value, error: null }
        : { loading: false, data: null, error: err(r3.reason) },
    )
    setBtSide(
      r4.status === 'fulfilled'
        ? { loading: false, data: r4.value, error: null }
        : { loading: false, data: null, error: err(r4.reason) },
    )
    setIngest(
      r5.status === 'fulfilled'
        ? { loading: false, data: r5.value, error: null }
        : { loading: false, data: null, error: err(r5.reason) },
    )

    if (!silent) setPageInit(false)
    setSilentBusy(false)
  }, [])

  useEffect(() => {
    void loadAll({ silent: false })
  }, [loadAll])

  const d = dashboard.data
  const cov = d?.data_coverage

  const pipelineCards = d
    ? [
        { label: 'Teams importati', value: String(d.teams_total), hint: cov?.teams_imported ? 'Copertura squadre OK' : 'Squadre non ancora importate' },
        { label: 'Fixtures totali', value: String(d.fixtures_total) },
        { label: 'Fixtures concluse', value: String(d.fixtures_completed) },
        { label: 'Team stats coverage', value: formatPercent(d.team_stats_coverage_pct) },
        { label: 'SOT feature coverage', value: formatPercent(d.sot_feature_coverage_pct) },
        { label: 'Prediction coverage', value: formatPercent(d.sot_predictions_coverage_pct) },
        { label: 'Backtest coverage', value: formatPercent(d.sot_backtest_coverage_pct) },
      ]
    : []

  const lastFiveRuns: IngestionRunSummary[] = ingest.data?.runs?.slice(0, 5) ?? []

  return (
    <div className="min-h-screen bg-[#f4f6f9] pb-12 pt-2">
      <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Serie A SOT Predictor
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
            Monitoraggio dati, feature, prediction e backtest sui tiri in porta squadra
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Stagione {SEASON}
            {silentBusy ? (
              <span className="ml-2 text-slate-400">· Aggiornamento in corso…</span>
            ) : null}
          </p>
        </header>

        {/* Data pipeline */}
        <SectionCard title="Data pipeline">
          {!dashboard.loading && !dashboard.error && d ? (
            <div className="mb-6 grid gap-3 border-b border-slate-100 pb-6 sm:grid-cols-2 lg:grid-cols-5">
              <div className="rounded-xl bg-slate-50/80 px-3 py-2 text-sm">
                <p className="text-xs font-medium text-slate-500">Stato dati</p>
                <p className="mt-1 font-medium text-slate-800">
                  {cov?.teams_imported && cov?.fixtures_imported ? 'Copertura base OK' : 'Copertura incompleta'}
                </p>
              </div>
              <div className="rounded-xl bg-slate-50/80 px-3 py-2 text-sm">
                <p className="text-xs font-medium text-slate-500">Stato ingestion</p>
                <p className="mt-1 font-medium text-slate-800">
                  {d.last_ingestion_run
                    ? `${d.last_ingestion_run.status} · ${d.last_ingestion_run.source}`
                    : 'Nessuna run recente'}
                </p>
              </div>
              <div className="rounded-xl bg-slate-50/80 px-3 py-2 text-sm">
                <p className="text-xs font-medium text-slate-500">Stato feature SOT</p>
                <p className="mt-1 font-medium tabular-nums text-slate-800">
                  {formatPercent(d.sot_feature_coverage_pct)}
                </p>
              </div>
              <div className="rounded-xl bg-slate-50/80 px-3 py-2 text-sm">
                <p className="text-xs font-medium text-slate-500">Stato predictions</p>
                <p className="mt-1 font-medium tabular-nums text-slate-800">
                  {formatPercent(d.sot_predictions_coverage_pct)}
                </p>
              </div>
              <div className="rounded-xl bg-slate-50/80 px-3 py-2 text-sm">
                <p className="text-xs font-medium text-slate-500">Stato backtest</p>
                <p className="mt-1 font-medium tabular-nums text-slate-800">
                  {formatPercent(d.sot_backtest_coverage_pct)}
                </p>
              </div>
            </div>
          ) : null}
          {dashboard.loading && pageInit ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                  <SkeletonBlock className="h-3 w-24" />
                  <SkeletonBlock className="mt-3 h-8 w-16" />
                </div>
              ))}
            </div>
          ) : dashboard.error ? (
            <SectionError message={dashboard.error} />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {pipelineCards.map((c) => (
                <div
                  key={c.label}
                  className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm"
                >
                  <p className="text-xs font-medium text-slate-500">{c.label}</p>
                  <p className="mt-2 text-xl font-semibold tabular-nums text-slate-900">{c.value}</p>
                  {c.hint ? <p className="mt-1 text-xs text-slate-500">{c.hint}</p> : null}
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Backtest overview */}
          <SectionCard title="Backtest · Panoramica">
            {btSummary.loading && pageInit ? (
              <div className="space-y-3">
                <SkeletonBlock className="h-20 w-full" />
                <SkeletonBlock className="h-20 w-full" />
              </div>
            ) : btSummary.error ? (
              <SectionError message={btSummary.error} />
            ) : btSummary.data ? (
              <dl className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">MAE</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.mae)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500">Errore medio assoluto</p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">RMSE</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.rmse)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500">Penalizza maggiormente gli errori grandi</p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">Avg Expected SOT</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.avg_expected_sot)}
                  </dd>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">Avg Actual SOT</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.avg_actual_sot)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500 sm:col-span-2">
                    Confronto tra media prevista e media reale
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3 sm:col-span-2">
                  <dt className="text-xs font-medium text-slate-500">Max Absolute Error</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.max_absolute_error)}
                  </dd>
                </div>
              </dl>
            ) : null}
          </SectionCard>

          {/* Stato modello */}
          <SectionCard title="Stato modello">
            {btSummary.loading && pageInit ? (
              <SkeletonBlock className="h-32 w-full" />
            ) : btSummary.error ? (
              <SectionError message={btSummary.error} />
            ) : btSummary.data ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      btSummary.data.coverage_pct >= 100
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {btSummary.data.coverage_pct >= 100 ? 'Backtest completo' : 'Backtest parziale'}
                  </span>
                  <span className="text-xs text-slate-500">
                    model_version:{' '}
                    <span className="font-mono text-slate-700">{btSummary.data.model_version}</span>
                  </span>
                </div>
                <dl className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <dt className="text-xs text-slate-500">predictions_total</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {btSummary.data.predictions_total}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">backtests_total</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {btSummary.data.backtests_total}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">coverage_pct</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {formatPercent(btSummary.data.coverage_pct)}
                    </dd>
                  </div>
                </dl>
                {predSummary.data ? (
                  <p className="text-xs text-slate-500">
                    Prediction summary: {predSummary.data.predictions_total} predictions · copertura{' '}
                    {formatPercent(predSummary.data.coverage_pct)}
                  </p>
                ) : predSummary.error ? (
                  <p className="text-xs text-amber-800">Prediction summary: {predSummary.error}</p>
                ) : null}
              </div>
            ) : null}
          </SectionCard>
        </div>

        {/* Errori per squadra */}
        <SectionCard title="Errori per squadra">
          {btTeam.loading && pageInit ? (
            <SkeletonBlock className="h-48 w-full" />
          ) : btTeam.error ? (
            <SectionError message={btTeam.error} />
          ) : btTeam.data?.teams?.length ? (
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs font-medium uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2">Squadra</th>
                    <th className="px-3 py-2 text-right">Prediction</th>
                    <th className="px-3 py-2 text-right">Expected medio</th>
                    <th className="px-3 py-2 text-right">Actual medio</th>
                    <th className="px-3 py-2 text-right">Diff. media</th>
                    <th className="px-3 py-2 text-right">MAE</th>
                    <th className="px-3 py-2 text-right">RMSE</th>
                    <th className="px-3 py-2 text-right">Max err</th>
                  </tr>
                </thead>
                <tbody>
                  {btTeam.data.teams.map((row) => {
                    const diff = row.avg_actual_sot - row.avg_expected_sot
                    const diffClass =
                      diff > 0.001
                        ? 'bg-emerald-50/90'
                        : diff < -0.001
                          ? 'bg-rose-50/90'
                          : ''
                    return (
                      <tr key={row.team_id} className="border-b border-slate-100">
                        <td className="px-3 py-2 font-medium text-slate-800">{row.team_name}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {row.predictions_count}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {formatNum(row.avg_expected_sot)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {formatNum(row.avg_actual_sot)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right tabular-nums text-slate-900 ${diffClass}`}
                          title={
                            diff > 0
                              ? 'Modello tende a sottostimare (actual > expected)'
                              : diff < 0
                                ? 'Modello tende a sovrastimare'
                                : ''
                          }
                        >
                          {formatNum(diff)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {formatNum(row.mae)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {formatNum(row.rmse)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                          {formatNum(row.max_absolute_error)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-600">Nessun dato per squadra.</p>
          )}
        </SectionCard>

        {/* Casa / fuori */}
        <SectionCard title="Errori casa / fuori">
          {btSide.loading && pageInit ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <SkeletonBlock className="h-40 w-full" />
              <SkeletonBlock className="h-40 w-full" />
            </div>
          ) : btSide.error ? (
            <SectionError message={btSide.error} />
          ) : btSide.data ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {(['home', 'away'] as const).map((sideKey) => {
                const row = pickSide(btSide.data!.sides, sideKey)
                const title = sideKey === 'home' ? 'Home' : 'Away'
                return (
                  <div
                    key={sideKey}
                    className="rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 shadow-sm"
                  >
                    <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
                    {row ? (
                      <dl className="mt-4 space-y-2 text-sm">
                        <div className="flex justify-between gap-2">
                          <dt className="text-slate-500">predictions_count</dt>
                          <dd className="tabular-nums font-medium text-slate-900">
                            {row.predictions_count}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-slate-500">avg_expected_sot</dt>
                          <dd className="tabular-nums text-slate-800">{formatNum(row.avg_expected_sot)}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-slate-500">avg_actual_sot</dt>
                          <dd className="tabular-nums text-slate-800">{formatNum(row.avg_actual_sot)}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-slate-500">mae</dt>
                          <dd className="tabular-nums text-slate-800">{formatNum(row.mae)}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-slate-500">rmse</dt>
                          <dd className="tabular-nums text-slate-800">{formatNum(row.rmse)}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="mt-2 text-sm text-slate-500">Nessun dato per questo lato.</p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : null}
        </SectionCard>

        {/* Ingestion runs */}
        <SectionCard title="Ingestion runs (ultime 5)">
          {ingest.loading && pageInit ? (
            <SkeletonBlock className="h-36 w-full" />
          ) : ingest.error ? (
            <SectionError message={ingest.error} />
          ) : lastFiveRuns.length ? (
            <ul className="space-y-3">
              {lastFiveRuns.map((run) => (
                <li
                  key={run.id}
                  className="flex flex-col gap-2 rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-slate-800">{run.source}</span>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${ingestionStatusClass(run.status)}`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600">
                    <span className="tabular-nums">record: {run.records_processed}</span>
                    <span className="mx-2 text-slate-300">·</span>
                    <span>inizio {formatDateTime(run.started_at)}</span>
                    <span className="mx-2 text-slate-300">·</span>
                    <span>fine {formatDateTime(run.completed_at)}</span>
                  </div>
                  {run.error_message ? (
                    <p className="w-full text-xs text-rose-800">{run.error_message}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-600">Nessuna run disponibile.</p>
          )}
        </SectionCard>

        {/* Admin */}
        <SectionCard title="Azioni amministrative">
          <p className="mb-4 text-xs text-slate-500">
            Le operazioni possono richiedere tempo. Al termine con successo i dati in dashboard vengono
            ricaricati.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <button
              type="button"
              disabled={adminFeatures.loading}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={async () => {
                setAdminFeatures({ loading: true, ok: null, msg: null })
                try {
                  const out = await runBuildSotFeatures(SEASON)
                  setAdminFeatures({
                    loading: false,
                    ok: true,
                    msg: adminSuccessMessage(out, 'Feature SOT ricostruite.'),
                  })
                  await loadAll({ silent: true })
                } catch (e) {
                  setAdminFeatures({
                    loading: false,
                    ok: false,
                    msg: e instanceof Error ? e.message : String(e),
                  })
                }
              }}
            >
              {adminFeatures.loading ? 'Caricamento…' : 'Ricostruisci Feature SOT'}
            </button>
            <button
              type="button"
              disabled={adminPred.loading}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={async () => {
                setAdminPred({ loading: true, ok: null, msg: null })
                try {
                  const out = await runGenerateSotPredictions(SEASON)
                  setAdminPred({
                    loading: false,
                    ok: true,
                    msg: adminSuccessMessage(out, 'Prediction SOT rigenerate.'),
                  })
                  await loadAll({ silent: true })
                } catch (e) {
                  setAdminPred({
                    loading: false,
                    ok: false,
                    msg: e instanceof Error ? e.message : String(e),
                  })
                }
              }}
            >
              {adminPred.loading ? 'Caricamento…' : 'Rigenera Prediction SOT'}
            </button>
            <button
              type="button"
              disabled={adminBt.loading}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={async () => {
                setAdminBt({ loading: true, ok: null, msg: null })
                try {
                  const out = await runSotBacktest(SEASON)
                  setAdminBt({
                    loading: false,
                    ok: true,
                    msg: adminSuccessMessage(out, 'Backtest SOT completato.'),
                  })
                  await loadAll({ silent: true })
                } catch (e) {
                  setAdminBt({
                    loading: false,
                    ok: false,
                    msg: e instanceof Error ? e.message : String(e),
                  })
                }
              }}
            >
              {adminBt.loading ? 'Caricamento…' : 'Rilancia Backtest SOT'}
            </button>
          </div>
          {(adminFeatures.msg || adminPred.msg || adminBt.msg) && (
            <div className="mt-4 space-y-1 text-sm">
              {adminFeatures.msg ? (
                <p className={adminFeatures.ok === false ? 'text-rose-800' : 'text-slate-700'}>
                  Feature: {adminFeatures.msg}
                </p>
              ) : null}
              {adminPred.msg ? (
                <p className={adminPred.ok === false ? 'text-rose-800' : 'text-slate-700'}>
                  Prediction: {adminPred.msg}
                </p>
              ) : null}
              {adminBt.msg ? (
                <p className={adminBt.ok === false ? 'text-rose-800' : 'text-slate-700'}>
                  Backtest: {adminBt.msg}
                </p>
              ) : null}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
