import { useCallback, useEffect, useState } from 'react'
import {
  AdminHttpError,
  confirmSportApiMapping,
  fetchSportApiLineups,
  getSportApiFixtureDebug,
  getSportApiLineups,
} from '../../lib/api'
import {
  getSportApiPlayerMatchingPreview,
} from '../../lib/api'
import { LineupImpactSimulationCard } from '../sportapi/LineupImpactSimulationCard'
import {
  SportApiLineupsCard,
  sportApiLineupsFromStored,
} from '../sportapi/SportApiLineupsCard'
import type { LineupImpactSimulationPayload } from '../../types/lineupImpact'
import type { SportApiCandidate, SportApiFixtureDebugResponse, SportApiLineupsStoredResponse } from '../../types/sportapi'

const FIXTURE_NOT_FOUND_MSG =
  "Fixture non trovata. Verifica di aver inserito l'ID interno DB oppure l'api_fixture_id API-Football."

function formatFetchError(e: unknown, label: string): string {
  if (e instanceof AdminHttpError) {
    if (e.status === 404) {
      const detail =
        typeof e.body === 'object' &&
        e.body !== null &&
        'detail' in e.body &&
        typeof (e.body as { detail: unknown }).detail === 'string'
          ? (e.body as { detail: string }).detail
          : e.message
      return detail || FIXTURE_NOT_FOUND_MSG
    }
    return `${label}: ${e.message}`
  }
  const raw = e instanceof Error ? e.message : String(e)
  if (raw === 'Failed to fetch' || /network|abort/i.test(raw)) {
    return `${label}: errore di rete o backend non raggiungibile.`
  }
  return `${label}: ${raw}`
}

type SportApiDebugPanelProps = {
  initialFixtureRef?: string
}

export function SportApiDebugPanel({ initialFixtureRef }: SportApiDebugPanelProps) {
  const [fixtureIdInput, setFixtureIdInput] = useState('')
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [debug, setDebug] = useState<SportApiFixtureDebugResponse | null>(null)
  const [stored, setStored] = useState<SportApiLineupsStoredResponse | null>(null)
  const [lineupImpact, setLineupImpact] = useState<LineupImpactSimulationPayload | null>(null)
  const [manualEventId, setManualEventId] = useState('')

  useEffect(() => {
    const trimmed = initialFixtureRef?.trim()
    if (trimmed) {
      setFixtureIdInput(trimmed)
    }
  }, [initialFixtureRef])

  const fixtureId = () => {
    const n = parseInt(fixtureIdInput.trim(), 10)
    return Number.isFinite(n) && n > 0 ? n : null
  }

  const actionFixtureId = () => {
    if (debug?.fixture?.fixture_id != null) return debug.fixture.fixture_id
    return fixtureId()
  }

  const runDebug = useCallback(async () => {
    const fid = fixtureId()
    if (fid == null) {
      setError('Inserisci un ID numerico valido (ID interno DB o api_fixture_id API-Football)')
      return
    }
    setLoading('debug')
    setError(null)
    try {
      const data = await getSportApiFixtureDebug(fid)
      setDebug(data)
      const best = data.best_candidate
      if (best?.provider_event_id != null) {
        setManualEventId(String(best.provider_event_id))
      }
    } catch (e) {
      setDebug(null)
      setError(formatFetchError(e, 'Cerca match SportAPI'))
    } finally {
      setLoading(null)
    }
  }, [fixtureIdInput])

  const loadImpactPreview = useCallback(async (fid: number) => {
    try {
      const preview = await getSportApiPlayerMatchingPreview(fid)
      setLineupImpact(preview.lineup_impact_simulation ?? null)
    } catch {
      setLineupImpact(null)
    }
  }, [])

  const runConfirm = useCallback(async () => {
    const fid = actionFixtureId()
    const eid = parseInt(manualEventId.trim(), 10)
    if (fid == null || !Number.isFinite(eid)) {
      setError('fixture_id e provider_event_id validi richiesti')
      return
    }
    const score = debug?.best_candidate?.confidence_score ?? debug?.confidence_score ?? null
    if (score != null && score < 90) {
      const ok = window.confirm(
        `Score ${score} < 90 (non AUTO_SAFE). Salvare comunque il mapping event_id ${eid}?`,
      )
      if (!ok) return
    }
    setLoading('confirm')
    setError(null)
    try {
      await confirmSportApiMapping(fid, {
        provider_event_id: eid,
        confidence_score: score,
        matched_by: debug?.matched_by ?? 'admin_manual',
        raw_payload: (debug?.best_candidate as Record<string, unknown> | undefined) ?? null,
      })
      const lineups = await getSportApiLineups(fid)
      setStored(lineups)
      await loadImpactPreview(fid)
    } catch (e) {
      setError(formatFetchError(e, 'Salva mapping'))
    } finally {
      setLoading(null)
    }
  }, [manualEventId, debug, loadImpactPreview])

  const runFetchLineups = useCallback(async () => {
    const fid = actionFixtureId()
    if (fid == null) {
      setError('fixture_id valido richiesto')
      return
    }
    setLoading('fetch')
    setError(null)
    try {
      await fetchSportApiLineups(fid)
      const lineups = await getSportApiLineups(fid)
      setStored(lineups)
      await loadImpactPreview(fid)
    } catch (e) {
      setError(formatFetchError(e, 'Importa lineups'))
    } finally {
      setLoading(null)
    }
  }, [debug, fixtureIdInput, loadImpactPreview])

  const runLoadStored = useCallback(async () => {
    const fid = actionFixtureId()
    if (fid == null) return
    setLoading('stored')
    setError(null)
    try {
      setStored(await getSportApiLineups(fid))
      await loadImpactPreview(fid)
    } catch (e) {
      setError(formatFetchError(e, 'Carica dati salvati'))
    } finally {
      setLoading(null)
    }
  }, [debug, fixtureIdInput, loadImpactPreview])

  const enabled = debug?.sportapi_enabled !== false
  const fx = debug?.fixture

  return (
    <div className="space-y-4">
      <div className="rounded-xl border-2 border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-950">
        Dati non usati nel modello — solo audit/debug SportAPI
      </div>
      <p className="text-[11px] leading-relaxed text-amber-900">
        Piano RapidAPI Basic: limite chiamate molto basso. Usa solo azioni manuali (1 scheduled-events per
        &quot;Cerca match&quot;, 1 lineups per &quot;Importa&quot;). Nessun sync automatico.
      </p>

      <label className="block text-xs text-slate-600">
        Fixture ID o API-Football fixture_id
        <input
          type="number"
          value={fixtureIdInput}
          onChange={(e) => setFixtureIdInput(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
          placeholder="es. 1378236"
        />
      </label>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading !== null}
          onClick={() => void runDebug()}
          className="rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {loading === 'debug' ? 'Ricerca…' : 'Cerca match SportAPI'}
        </button>
        <button
          type="button"
          disabled={loading !== null || !enabled}
          onClick={() => void runConfirm()}
          className="rounded-lg bg-indigo-700 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-800 disabled:opacity-50"
        >
          {loading === 'confirm' ? 'Salvataggio…' : 'Salva mapping'}
        </button>
        <button
          type="button"
          disabled={loading !== null || !enabled}
          onClick={() => void runFetchLineups()}
          className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
        >
          {loading === 'fetch' ? 'Import…' : 'Importa lineups'}
        </button>
        <button
          type="button"
          disabled={loading !== null}
          onClick={() => void runLoadStored()}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading === 'stored' ? '…' : 'Ricarica salvati'}
        </button>
      </div>

      {debug?.status === 'disabled' ? (
        <p className="text-xs text-amber-800">
          SportAPI disabilitata sul server (SPORTAPI_ENABLED=false o chiave assente).
        </p>
      ) : null}

      {error ? <p className="text-xs text-rose-700">{error}</p> : null}

      {fx ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800">
          <p className="font-semibold">Fixture API-Football</p>
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
            <div>
              <dt className="text-slate-500">ID DB</dt>
              <dd className="font-mono">{fx.fixture_id}</dd>
            </div>
            <div>
              <dt className="text-slate-500">api_fixture_id</dt>
              <dd className="font-mono">{fx.api_fixture_id}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Casa</dt>
              <dd>{fx.home_team_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Trasferta</dt>
              <dd>{fx.away_team_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Kickoff</dt>
              <dd>{fx.kickoff_at ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Timestamp</dt>
              <dd className="font-mono">{fx.kickoff_timestamp ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Data partita</dt>
              <dd>{fx.match_date ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Timezone</dt>
              <dd>{fx.timezone ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Lega</dt>
              <dd>
                {fx.league_name ?? '—'}
                {fx.league_api_id != null ? ` (API ${fx.league_api_id})` : ''}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Giornata</dt>
              <dd>{fx.round ?? '—'}</dd>
            </div>
            {(fx.resolved_via ?? debug.resolved_via) ? (
              <div>
                <dt className="text-slate-500">Risolto via</dt>
                <dd className="font-mono">{fx.resolved_via ?? debug.resolved_via}</dd>
              </div>
            ) : null}
            {debug.input_id != null && debug.input_id !== fx.fixture_id ? (
              <div>
                <dt className="text-slate-500">Input inserito</dt>
                <dd className="font-mono">{debug.input_id}</dd>
              </div>
            ) : null}
          </dl>
          <p className="mt-2">
            Raccomandazione: <strong>{debug.recommendation ?? '—'}</strong>
            {debug.confidence_score != null ? ` · score ${debug.confidence_score}` : ''}
          </p>
          {debug.score_explanation ? <p className="mt-1 text-slate-600">{debug.score_explanation}</p> : null}
        </div>
      ) : null}

      <label className="block text-xs text-slate-600">
        SportAPI event_id (per salva mapping)
        <input
          type="number"
          value={manualEventId}
          onChange={(e) => setManualEventId(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
          placeholder="13980080"
        />
      </label>

      {(debug?.candidates?.length ?? 0) > 0 ? (
        <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-[10px]">
            <thead className="sticky top-0 bg-slate-100">
              <tr>
                <th className="px-2 py-1">Event</th>
                <th className="px-2 py-1">Score</th>
                <th className="px-2 py-1">Rec.</th>
                <th className="px-2 py-1">Partita</th>
                <th className="px-2 py-1">Breakdown</th>
              </tr>
            </thead>
            <tbody>
              {(debug?.candidates ?? []).map((c: SportApiCandidate) => (
                <tr key={c.provider_event_id} className="border-t border-slate-100">
                  <td className="px-2 py-1 font-mono">{c.provider_event_id}</td>
                  <td className="px-2 py-1">{c.confidence_score}</td>
                  <td className="px-2 py-1">{c.recommendation}</td>
                  <td className="px-2 py-1">
                    {c.home_team_name} – {c.away_team_name}
                  </td>
                  <td className="px-2 py-1 font-mono text-[9px]">
                    {JSON.stringify(c.score_breakdown)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {stored?.mapping || stored?.fetched_at || stored?.available ? (
        <>
          <SportApiLineupsCard
            compact
            data={sportApiLineupsFromStored(
              stored,
              debug?.fixture?.home_team_name ?? 'Casa',
              debug?.fixture?.away_team_name ?? 'Trasferta',
            )}
            apiFixtureId={debug?.fixture?.api_fixture_id}
          />
          <LineupImpactSimulationCard data={lineupImpact ?? undefined} />
        </>
      ) : null}
    </div>
  )
}
