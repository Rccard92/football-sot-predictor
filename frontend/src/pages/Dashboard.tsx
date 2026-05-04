import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  DEFAULT_SEASON,
  getBacktestBySide,
  getBacktestByTeam,
  getBacktestSummary,
  getDashboard,
  getIngestionRuns,
  getPredictionSummary,
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

function maeQualityLabel(mae: number): string {
  if (mae < 1.5) return 'Buono'
  if (mae <= 2.0) return 'Accettabile'
  return 'Da migliorare'
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

  const loadAll = useCallback(async () => {
    setDashboard({ loading: true, data: null, error: null })
    setPredSummary({ loading: true, data: null, error: null })
    setBtSummary({ loading: true, data: null, error: null })
    setBtTeam({ loading: true, data: null, error: null })
    setBtSide({ loading: true, data: null, error: null })
    setIngest({ loading: true, data: null, error: null })

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

    setPageInit(false)
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const d = dashboard.data
  const cov = d?.data_coverage

  const pipelineCards = d
    ? [
        { label: 'Teams importati', value: String(d.teams_total), hint: cov?.teams_imported ? 'Copertura squadre OK' : 'Squadre non ancora importate' },
        { label: 'Fixtures totali', value: String(d.fixtures_total) },
        { label: 'Fixtures concluse', value: String(d.fixtures_completed) },
        { label: 'Copertura dati (statistiche squadra)', value: formatPercent(d.team_stats_coverage_pct) },
        { label: 'Dati preparati per il modello (copertura)', value: formatPercent(d.sot_feature_coverage_pct) },
        { label: 'Previsioni generate (copertura)', value: formatPercent(d.sot_predictions_coverage_pct) },
        { label: 'Copertura backtest', value: formatPercent(d.sot_backtest_coverage_pct) },
        { label: 'Partite prossime', value: String(d.upcoming_fixtures_total ?? 0) },
        { label: 'Feature su partite future', value: String(d.upcoming_sot_feature_rows_total ?? 0) },
        { label: 'Prediction su partite future', value: String(d.upcoming_sot_predictions_total ?? 0) },
      ]
    : []

  const lastFiveRuns: IngestionRunSummary[] = ingest.data?.runs?.slice(0, 5) ?? []

  return (
    <div className="min-h-screen bg-[#f4f6f9] pb-12 pt-2">
      <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Dashboard modello</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
            Metriche tecniche: pipeline dati, qualità del modello baseline su partite giocate e backtest
            numerico.
          </p>
          <p className="mt-1 text-xs text-slate-500">Stagione {SEASON}</p>
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
              {Array.from({ length: 10 }).map((_, i) => (
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

        {/* Step 9: layer giocatori / formazioni (copertura dati) */}
        <SectionCard title="Layer giocatori, formazioni e disponibilità">
          {!dashboard.loading && !dashboard.error && d ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Statistiche giocatori (copertura)</p>
                <p className="mt-2 text-xl font-semibold tabular-nums text-slate-900">
                  {formatPercent(d.player_stats_coverage_pct ?? 0)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Partite concluse con righe importate: {d.fixtures_with_player_stats ?? 0} /{' '}
                  {d.fixtures_completed}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Formazioni storiche (copertura)</p>
                <p className="mt-2 text-xl font-semibold tabular-nums text-slate-900">
                  {formatPercent(d.lineups_coverage_pct ?? 0)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Partite con almeno una formazione salvata: {d.fixtures_with_lineups ?? 0}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Profili impatto tiri in porta</p>
                <p className="mt-2 text-xl font-semibold tabular-nums text-slate-900">
                  {d.players_profiled_total ?? 0}
                </p>
                <p className="mt-1 text-xs text-slate-500">Giocatori con profilo calcolato per la stagione</p>
              </div>
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Eventi assenze / infortuni (import)</p>
                <p className="mt-2 text-xl font-semibold tabular-nums text-slate-900">
                  {d.availability_events_total ?? 0}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Record salvati (non usati ancora nel baseline)
                </p>
              </div>
            </div>
          ) : dashboard.loading && pageInit ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <SkeletonBlock key={i} className="h-24 w-full rounded-2xl" />
              ))}
            </div>
          ) : dashboard.error ? (
            <SectionError message={dashboard.error} />
          ) : null}
          {!dashboard.loading && !dashboard.error && d?.player_profiles_sot_data_suspicious ? (
            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
              Profili giocatore presenti, ma dati tiri in porta giocatore da verificare.
            </p>
          ) : null}
        </SectionCard>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Backtest overview */}
          <SectionCard title="Qualità modello (partite giocate)">
            {!dashboard.loading && !dashboard.error && d?.player_profiles_sot_data_suspicious ? (
              <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
                Profili giocatore presenti, ma dati tiri in porta giocatore da verificare (layer debug, non
                usati nel MAE/RMSE sopra).
              </p>
            ) : null}
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
                  <dt className="text-xs font-medium text-slate-500">Errore medio del modello (MAE)</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.mae)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500">
                    In media, il modello sbaglia di questo numero di tiri in porta per squadra.
                  </p>
                  <p className="mt-2 text-xs font-medium text-slate-600">
                    Interpretazione: {maeQualityLabel(btSummary.data.mae)} (&lt; 1,50 buono · 1,50–2,00
                    accettabile · &gt; 2,00 da migliorare)
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">
                    Errore sugli scostamenti grandi (RMSE)
                  </dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.rmse)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500">
                    Questo valore cresce quando ci sono errori molto grandi su alcune partite.
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">Media prevista tiri in porta</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.avg_expected_sot)}
                  </dd>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3">
                  <dt className="text-xs font-medium text-slate-500">Media reale tiri in porta</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                    {formatNum(btSummary.data.avg_actual_sot)}
                  </dd>
                  <p className="mt-1 text-xs text-slate-500">
                    Confronto tra media prevista e media reale sul campione backtestato.
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-3 sm:col-span-2">
                  <dt className="text-xs font-medium text-slate-500">Errore massimo assoluto</dt>
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
                    <dt className="text-xs text-slate-500">Previsioni generate</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {btSummary.data.predictions_total}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Righe backtest</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {btSummary.data.backtests_total}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Copertura dati (backtest)</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums">
                      {formatPercent(btSummary.data.coverage_pct)}
                    </dd>
                  </div>
                </dl>
                {predSummary.data ? (
                  <p className="text-xs text-slate-500">
                    Riepilogo prediction: {predSummary.data.predictions_total} previsioni · copertura{' '}
                    {formatPercent(predSummary.data.coverage_pct)}
                  </p>
                ) : predSummary.error ? (
                  <p className="text-xs text-amber-800">Riepilogo prediction: {predSummary.error}</p>
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
                    <th className="px-3 py-2 text-right">Err. medio</th>
                    <th className="px-3 py-2 text-right">Err. grandi</th>
                    <th className="px-3 py-2 text-right">Err. max</th>
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

        <p className="text-center text-xs text-slate-500">
          Azioni di ingestion e rigenerazione: usa la pagina{' '}
          <Link to="/admin" className="font-medium text-slate-700 underline">
            Admin
          </Link>
          .
        </p>
      </div>
    </div>
  )
}
