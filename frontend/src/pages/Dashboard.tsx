import { useEffect, useState } from 'react'
import { Card } from '../components/ui/Card'
import {
  getDashboard,
  getDataHealth,
  type SerieADashboardResponse,
  type SerieADataHealthResponse,
} from '../lib/api'

/** Stagione Serie A mostrata in dashboard (allineata agli endpoint backend). */
const SEASON = 2025

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

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string
  value: string | number
  hint?: string
}) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div
            key={i}
            className="animate-pulse rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
          >
            <div className="h-4 w-24 rounded bg-slate-200" />
            <div className="mt-3 h-8 w-16 rounded bg-slate-200" />
          </div>
        ))}
      </div>
      <div className="animate-pulse rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <div className="h-5 w-40 rounded bg-slate-200" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, j) => (
            <div key={j}>
              <div className="h-3 w-28 rounded bg-slate-200" />
              <div className="mt-2 h-7 w-14 rounded bg-slate-200" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [dashboard, setDashboard] = useState<SerieADashboardResponse | null>(null)
  const [health, setHealth] = useState<SerieADataHealthResponse | null>(null)
  const [dashboardError, setDashboardError] = useState<string | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setDashboardError(null)
      setHealthError(null)

      const [dResult, hResult] = await Promise.allSettled([
        getDashboard(SEASON),
        getDataHealth(SEASON),
      ])

      if (cancelled) return

      if (dResult.status === 'fulfilled') {
        setDashboard(dResult.value)
        setDashboardError(null)
      } else {
        setDashboard(null)
        setDashboardError(
          dResult.reason instanceof Error ? dResult.reason.message : String(dResult.reason),
        )
      }

      if (hResult.status === 'fulfilled') {
        setHealth(hResult.value)
        setHealthError(null)
      } else {
        setHealth(null)
        setHealthError(
          hResult.reason instanceof Error ? hResult.reason.message : String(hResult.reason),
        )
      }

      setLoading(false)
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const cov = dashboard?.data_coverage
  const last = dashboard?.last_ingestion_run

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          Serie A · stagione {SEASON} · dati dal backend in tempo reale.
        </p>
      </header>

      {(dashboardError || healthError) && (
        <div className="space-y-2 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          {dashboardError ? (
            <p>
              <span className="font-medium">Dashboard: </span>
              {dashboardError}
            </p>
          ) : null}
          {healthError ? (
            <p>
              <span className="font-medium">Data health: </span>
              {healthError}
            </p>
          ) : null}
        </div>
      )}

      {loading ? (
        <DashboardSkeleton />
      ) : dashboard ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard
            label="Squadre importate"
            value={dashboard.teams_total}
            hint={
              cov?.teams_imported
                ? 'Flag copertura: squadre presenti'
                : 'Flag copertura: squadre non ancora importate'
            }
          />
          <MetricCard label="Partite totali" value={dashboard.fixtures_total} />
          <MetricCard label="Partite concluse" value={dashboard.fixtures_completed} />
          <MetricCard label="Partite programmate" value={dashboard.fixtures_scheduled} />
          <MetricCard
            label="Partite con statistiche squadra"
            value={dashboard.fixtures_with_team_stats}
          />
          <MetricCard label="Righe statistiche squadra" value={dashboard.team_stats_rows_total} />
          <MetricCard
            label="Copertura statistiche"
            value={formatPercent(dashboard.team_stats_coverage_pct)}
          />
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:col-span-2 lg:col-span-2">
            <p className="text-sm font-medium text-slate-500">Ultimo job ingestion</p>
            {last ? (
              <ul className="mt-3 space-y-1 text-sm text-slate-700">
                <li>
                  <span className="text-slate-500">Sorgente: </span>
                  <span className="font-medium">{last.source}</span>
                </li>
                <li>
                  <span className="text-slate-500">Stato: </span>
                  <span className="font-medium">{last.status}</span>
                </li>
                <li>
                  <span className="text-slate-500">Record: </span>
                  {last.records_processed}
                </li>
                <li>
                  <span className="text-slate-500">Inizio: </span>
                  {formatDateTime(last.started_at)}
                </li>
                <li>
                  <span className="text-slate-500">Fine: </span>
                  {formatDateTime(last.completed_at)}
                </li>
                {last.error_message ? (
                  <li className="text-red-700">
                    <span className="text-slate-500">Errore: </span>
                    {last.error_message}
                  </li>
                ) : null}
              </ul>
            ) : (
              <p className="mt-2 text-slate-600">Nessun run registrato.</p>
            )}
          </div>
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Stato dati</p>
            <ul className="mt-3 space-y-2 text-sm text-slate-700">
              <li className="flex items-center justify-between gap-2">
                <span>Squadre</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    cov?.teams_imported
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-900'
                  }`}
                >
                  {cov?.teams_imported ? 'Importate' : 'Non importate'}
                </span>
              </li>
              <li className="flex items-center justify-between gap-2">
                <span>Partite</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    cov?.fixtures_imported
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-900'
                  }`}
                >
                  {cov?.fixtures_imported ? 'Importate' : 'Non importate'}
                </span>
              </li>
            </ul>
          </div>
        </div>
      ) : !loading && dashboardError ? (
        <p className="text-sm text-slate-600">Impossibile caricare le metriche principali.</p>
      ) : null}

      {health && !healthError ? (
        <Card title="Data Health">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {health.fixtures_missing_team_stats === 0 ? (
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-800">
                  Dati squadra completi
                </span>
              ) : (
                <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-900">
                  {health.fixtures_missing_team_stats} partite senza statistiche complete
                </span>
              )}
            </div>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Partite concluse
                </dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {health.fixtures_completed}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Con statistiche squadra
                </dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {health.fixtures_with_team_stats}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Senza statistiche complete
                </dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {health.fixtures_missing_team_stats}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Righe statistiche squadra
                </dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {health.team_stats_rows_total}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Copertura statistiche
                </dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {formatPercent(health.team_stats_coverage_pct)}
                </dd>
              </div>
            </dl>
            {health.missing_fixture_ids && health.missing_fixture_ids.length > 0 ? (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  ID partite mancanti (prime 10)
                </p>
                <p className="mt-1 font-mono text-sm text-slate-700">
                  {health.missing_fixture_ids.slice(0, 10).join(', ')}
                  {health.missing_fixture_ids.length > 10
                    ? ` … (+${health.missing_fixture_ids.length - 10})`
                    : ''}
                </p>
              </div>
            ) : null}
          </div>
        </Card>
      ) : null}
    </div>
  )
}
