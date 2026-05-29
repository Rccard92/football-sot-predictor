import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { DEFAULT_SEASON, buildMatchAuditUrl } from '../lib/api'
import { useCompetition } from '../contexts/CompetitionContext'
import { formatFetchError } from '../utils/formatFetchError'

type FixturesListItem = {
  fixture_id: number
  kickoff_at: string
  round: string | null
  home_team_name: string
  away_team_name: string
}

type FixturesListResponse = {
  fixtures: FixturesListItem[]
}

type DebugModelComparisonResponse = {
  status: 'success' | 'error'
  fixture?: {
    fixture_id: number
    api_fixture_id: number
    round: string | null
    kickoff_at: string
    home_team: { id: number; name: string; logo_url: string | null }
    away_team: { id: number; name: string; logo_url: string | null }
  }
  available_models?: string[]
  active_model_version?: string | null
  model_comparison?: {
    home: Array<Record<string, unknown>>
    away: Array<Record<string, unknown>>
    match_total: Array<Record<string, unknown>>
  }
  diagnostics?: {
    overall_status: 'stable' | 'inspect' | 'red_flag'
    overall_label: string
    summary: string
    red_flags: string[]
    confidence_notes: string[]
  }
  team_diagnostics?: {
    home: Record<string, unknown>
    away: Record<string, unknown>
  }
  component_breakdown?: Record<string, unknown>
  message?: string
  failed_step?: string
  details?: string
}

type DebugUpcomingResponse = {
  status: 'success' | 'error'
  season: number
  fixtures_analyzed: number
  summary?: Record<string, unknown>
  matches?: Array<Record<string, unknown>>
  message?: string
  failed_step?: string
  details?: string
}

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

function apiBase(): string {
  return String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`)
  const parsed = (await res.json()) as T
  if (!res.ok) throw new Error(JSON.stringify(parsed))
  return parsed
}

export function ModelDebug() {
  const qs = useQuery()
  const { selectedCompetitionId } = useCompetition()
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')

  const [fixtures, setFixtures] = useState<FixturesListItem[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [includeRaw, setIncludeRaw] = useState(false)

  const [loading, setLoading] = useState(false)
  const [fixturesError, setFixturesError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<DebugModelComparisonResponse | null>(null)

  const [loadingUpcoming, setLoadingUpcoming] = useState(false)
  const [upcoming, setUpcoming] = useState<DebugUpcomingResponse | null>(null)

  useEffect(() => {
    const loadFixtures = async () => {
      setFixturesError(null)
      try {
        const res = await fetchJson<FixturesListResponse>(
          `/api/match-analysis/fixtures?scope=upcoming&limit=60`,
        )
        setFixtures(res.fixtures ?? [])
        if (fixtureId == null && res.fixtures?.length) {
          setFixtureId(res.fixtures[0].fixture_id)
        }
      } catch (e) {
        setFixtures([])
        setFixturesError(formatFetchError(e, 'GET /api/match-analysis/fixtures'))
      }
    }
    void loadFixtures()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const load = async () => {
      if (!fixtureId) return
      setLoading(true)
      setError(null)
      try {
        const res = await fetchJson<DebugModelComparisonResponse>(
          `/api/debug/sot/fixture/${fixtureId}/model-comparison?include_raw=${String(includeRaw)}`,
        )
        setData(res)
      } catch (e) {
        setData(null)
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [fixtureId, includeRaw])

  useEffect(() => {
    const loadUpcoming = async () => {
      setLoadingUpcoming(true)
      try {
        const res = await fetchJson<DebugUpcomingResponse>(
          `/api/debug/sot/serie-a/${DEFAULT_SEASON}/model-comparison/upcoming`,
        )
        setUpcoming(res)
      } catch (e) {
        setUpcoming(null)
      } finally {
        setLoadingUpcoming(false)
      }
    }
    void loadUpcoming()
  }, [])

  const diag = data?.diagnostics

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Debug Modello</h1>
            <p className="mt-1 text-sm text-slate-600">
              Confronto automatico delle versioni modello su una singola partita e sulla prossima giornata (read-only).
            </p>
          </div>
          <Link to="/model-legend" className="text-sm font-medium text-slate-700 underline">
            Legenda modello
          </Link>
        </div>

        <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-3">
          <div className="md:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Seleziona partita
            </label>
            <select
              value={fixtureId ?? ''}
              onChange={(e) => setFixtureId(Number(e.target.value))}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
            >
              {fixtures.map((f) => (
                <option key={f.fixture_id} value={f.fixture_id}>
                  {f.round ? `${f.round} · ` : ''}
                  {f.home_team_name} - {f.away_team_name}
                </option>
              ))}
            </select>
            {fixtureId && selectedCompetitionId != null ? (
              <Link
                to={buildMatchAuditUrl({
                  competitionId: selectedCompetitionId,
                  fixtureId,
                })}
                className="mt-2 inline-block text-sm font-medium text-slate-700 underline"
              >
                Apri spiegazione previsione (audit fixture)
              </Link>
            ) : null}
          </div>
          <div className="flex items-end justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={includeRaw}
                onChange={(e) => setIncludeRaw(e.target.checked)}
              />
              Mostra raw_json (tecnico)
            </label>
          </div>
        </div>
      </header>

      {fixturesError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
          {fixturesError}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
          <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
        </div>
      ) : data?.status === 'success' && data.fixture && diag ? (
        <section className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-lg font-semibold text-slate-900">
                {data.fixture.home_team.name} - {data.fixture.away_team.name}
              </p>
              <span
                className={`rounded-full px-3 py-0.5 text-xs font-medium ring-1 ${
                  diag.overall_status === 'stable'
                    ? 'bg-emerald-50 text-emerald-800 ring-emerald-100'
                    : diag.overall_status === 'red_flag'
                      ? 'bg-red-50 text-red-800 ring-red-100'
                      : 'bg-amber-50 text-amber-900 ring-amber-100'
                }`}
              >
                {diag.overall_label}
              </span>
            </div>

            <p className="mt-2 text-sm text-slate-700">{diag.summary}</p>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Modelli disponibili</p>
                <p className="mt-2 text-sm text-slate-800">{(data.available_models ?? []).join(', ') || '—'}</p>
                <p className="mt-2 text-xs text-slate-600">
                  Modello attivo (per fixture):{' '}
                  <span className="font-medium text-slate-900">{data.active_model_version ?? '—'}</span>
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Red flags</p>
                {(diag.red_flags ?? []).length ? (
                  <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-800">
                    {diag.red_flags.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-700">Nessuna red flag rilevante.</p>
                )}
              </div>
            </div>
          </div>

          <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-slate-900 marker:hidden [&::-webkit-details-marker]:hidden">
              Dettaglio confronto (home/away/totale)
            </summary>
            <div className="space-y-6 border-t border-slate-200 px-5 py-5">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="md:col-span-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Home</p>
                  <pre className="mt-2 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify(data.model_comparison?.home ?? [], null, 2)}
                  </pre>
                </div>
                <div className="md:col-span-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Away</p>
                  <pre className="mt-2 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify(data.model_comparison?.away ?? [], null, 2)}
                  </pre>
                </div>
                <div className="md:col-span-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Totale match</p>
                  <pre className="mt-2 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify(data.model_comparison?.match_total ?? [], null, 2)}
                  </pre>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Breakdown (sintetico)</p>
                <pre className="mt-2 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify(data.component_breakdown ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          </details>
        </section>
      ) : data?.status === 'error' ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950 shadow-sm">
          <p className="font-medium">{data.message || 'Debug non disponibile'}</p>
          <p className="mt-1 text-xs text-amber-900">
            {data.failed_step ? `Step: ${data.failed_step}` : ''} {data.details ? `· ${data.details}` : ''}
          </p>
        </div>
      ) : null}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Prossima giornata (rischi)</h2>
            <p className="mt-1 text-sm text-slate-600">Lista ordinata per criticità (red_flag → inspect → stable).</p>
          </div>
        </div>

        {loadingUpcoming ? (
          <div className="mt-4 h-24 animate-pulse rounded-2xl bg-slate-200/80" />
        ) : upcoming?.status === 'success' ? (
          <div className="mt-4 space-y-3">
            <pre className="overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify({ summary: upcoming.summary, fixtures_analyzed: upcoming.fixtures_analyzed }, null, 2)}
            </pre>
            <pre className="overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
{JSON.stringify(upcoming.matches ?? [], null, 2)}
            </pre>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-600">Debug prossima giornata non disponibile.</p>
        )}
      </section>
    </div>
  )
}

