import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { MatchExplanationView } from '../components/match-explanation/MatchExplanationView'
import type { FixturesListItem, FixturesListResponse } from '../components/audit/types'
import type { SotFixtureExplanationResponse } from '../types/sotExplanation'

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export function MatchVariableAudit() {
  const qs = useQuery()
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')

  const [fixtures, setFixtures] = useState<FixturesListItem[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SotFixtureExplanationResponse | null>(null)

  useEffect(() => {
    const loadFixtures = async () => {
      setError(null)
      try {
        const res = (await fetch(
          `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')}/api/match-analysis/fixtures?scope=all&limit=120`,
        ).then((r) => r.json())) as FixturesListResponse
        setFixtures(res.fixtures ?? [])
        if (fixtureId == null && res.fixtures?.length) {
          setFixtureId(res.fixtures[0].fixture_id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
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
        const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
        const url = `${base}/api/debug/sot/fixture/${fixtureId}/explanation`
        const res = await fetch(url)
        const parsed = (await res.json()) as SotFixtureExplanationResponse
        if (!res.ok) {
          setData(null)
          setError(parsed.message || `Errore HTTP ${res.status}`)
          return
        }
        if (parsed.status === 'error') {
          setData(null)
          setError(parsed.message || 'Risposta di errore dal server')
          return
        }
        setData(parsed)
      } catch (e) {
        setData(null)
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [fixtureId])

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
              disabled={!fixtures.length}
            >
              {!fixtures.length ? <option value="">Nessuna fixture caricata</option> : null}
              {fixtures.map((f) => (
                <option key={f.fixture_id} value={f.fixture_id}>
                  {f.kickoff_at?.slice(0, 10)} — {f.home_team.name} vs {f.away_team.name} ({f.status_short})
                </option>
              ))}
            </select>
          </div>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">{error}</div>
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
