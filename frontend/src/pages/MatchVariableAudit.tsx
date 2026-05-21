import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { MatchExplanationView } from '../components/match-explanation/MatchExplanationView'
import type { FixturesListItem, FixturesListResponse } from '../components/audit/types'
import type { SotFixtureExplanationResponse } from '../types/sotExplanation'
import { MODEL_OPTIONS_AUDIT } from '../lib/modelVersions'
import { formatExplanationApiError, formatFetchError } from '../utils/formatFetchError'

const MODEL_OPTIONS = MODEL_OPTIONS_AUDIT

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export function MatchVariableAudit() {
  const qs = useQuery()
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')
  const modelFromQS = (qs.get('model_version') || '').trim()

  const [fixtures, setFixtures] = useState<FixturesListItem[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [modelVersion, setModelVersion] = useState<string>(
    MODEL_OPTIONS.some((o) => o.value === modelFromQS) ? modelFromQS : '',
  )

  const [loading, setLoading] = useState(false)
  const [fixturesError, setFixturesError] = useState<string | null>(null)
  const [explanationError, setExplanationError] = useState<string | null>(null)
  const [data, setData] = useState<SotFixtureExplanationResponse | null>(null)

  useEffect(() => {
    const loadFixtures = async () => {
      setFixturesError(null)
      try {
        const url = `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')}/api/match-analysis/fixtures?scope=upcoming&only_next_round=true&limit=40`
        const res = await fetch(url)
        const body = (await res.json()) as FixturesListResponse & { message?: string }
        if (!res.ok) {
          setFixtures([])
          setFixturesError(body.message || `Errore HTTP ${res.status} su /match-analysis/fixtures`)
          return
        }
        const list = body.fixtures ?? []
        setFixtures(list)
        if (list.length === 0) {
          setFixtureId(null)
          return
        }
        const ids = new Set(list.map((f) => f.fixture_id))
        const qsValid = Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 && ids.has(fixtureIdFromQS)
        if (qsValid) {
          setFixtureId(fixtureIdFromQS)
        } else if (fixtureId == null || !ids.has(fixtureId)) {
          setFixtureId(list[0].fixture_id)
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
      setExplanationError(null)
      try {
        const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
        const q = new URLSearchParams()
        if (modelVersion) q.set('model_version', modelVersion)
        const qsStr = q.toString()
        const url = `${base}/api/debug/sot/fixture/${fixtureId}/explanation${qsStr ? `?${qsStr}` : ''}`
        const res = await fetch(url)
        const parsed = (await res.json()) as SotFixtureExplanationResponse
        if (!res.ok || parsed.status === 'error') {
          setData(null)
          setExplanationError(formatExplanationApiError(parsed))
          return
        }
        setData(parsed)
      } catch (e) {
        setData(null)
        setExplanationError(formatFetchError(e, `GET .../fixture/${fixtureId}/explanation`))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [fixtureId, modelVersion])

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-6xl space-y-6 px-4 sm:px-6">
        <header className="rounded-2xl border border-slate-200/80 bg-white px-4 py-4 shadow-sm">
          <h1 className="text-xl font-semibold text-slate-900">Spiegazione previsione partita</h1>
          <p className="mt-1 text-sm text-slate-600">
            Audit read-only: come il modello attivo ha costruito i tiri in porta attesi, usando solo dati già salvati.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="text-xs font-medium text-slate-600" htmlFor="fixture-select">
              Partita
            </label>
            <select
              id="fixture-select"
              className="max-w-xl rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
              value={fixtureId ?? ''}
              onChange={(e) => setFixtureId(Number(e.target.value) || null)}
              disabled={fixtures.length === 0}
            >
              {fixtures.length === 0 ? (
                <option value="">Nessuna partita futura disponibile</option>
              ) : null}
              {fixtures.map((f) => (
                <option key={f.fixture_id} value={f.fixture_id}>
                  {f.kickoff_at?.slice(0, 10)} — {f.home_team.name} vs {f.away_team.name} ({f.status_short})
                </option>
              ))}
            </select>
            <label className="text-xs font-medium text-slate-600" htmlFor="model-version-select">
              Modello
            </label>
            <select
              id="model-version-select"
              className="max-w-md rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
              value={modelVersion}
              onChange={(e) => setModelVersion(e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value || 'auto'} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </header>

        {fixtures.length === 0 && !fixturesError ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
            Nessuna partita futura disponibile. Aggiorna il calendario da Admin.
          </div>
        ) : null}

        {fixturesError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {fixturesError}
          </div>
        ) : null}

        {explanationError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {explanationError}
          </div>
        ) : null}

        {loading ? (
          <div className="space-y-3">
            <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
            <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
          </div>
        ) : null}

        {!loading && data?.status === 'ok' && data.fixture && data.prediction_summary ? (
          <MatchExplanationView data={data} />
        ) : null}

        {!loading && data?.status === 'missing' ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
            {data.message ?? 'Dati insufficienti per questa fixture.'}
          </div>
        ) : null}
      </div>
    </div>
  )
}
