import { useCallback, useState } from 'react'
import {
  confirmSportApiMapping,
  fetchSportApiLineups,
  getSportApiFixtureDebug,
  getSportApiLineups,
} from '../../lib/api'
import type { SportApiCandidate, SportApiFixtureDebugResponse, SportApiLineupsStoredResponse } from '../../types/sportapi'

function formatFetchError(e: unknown, label: string): string {
  const raw = e instanceof Error ? e.message : String(e)
  if (raw === 'Failed to fetch' || /network|abort/i.test(raw)) {
    return `${label}: errore di rete o backend non raggiungibile.`
  }
  return `${label}: ${raw}`
}

export function SportApiDebugPanel() {
  const [fixtureIdInput, setFixtureIdInput] = useState('')
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [debug, setDebug] = useState<SportApiFixtureDebugResponse | null>(null)
  const [stored, setStored] = useState<SportApiLineupsStoredResponse | null>(null)
  const [manualEventId, setManualEventId] = useState('')

  const fixtureId = () => {
    const n = parseInt(fixtureIdInput.trim(), 10)
    return Number.isFinite(n) && n > 0 ? n : null
  }

  const runDebug = useCallback(async () => {
    const fid = fixtureId()
    if (fid == null) {
      setError('Inserisci fixture_id interno (DB) numerico valido')
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

  const runConfirm = useCallback(async () => {
    const fid = fixtureId()
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
    } catch (e) {
      setError(formatFetchError(e, 'Salva mapping'))
    } finally {
      setLoading(null)
    }
  }, [fixtureIdInput, manualEventId, debug])

  const runFetchLineups = useCallback(async () => {
    const fid = fixtureId()
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
    } catch (e) {
      setError(formatFetchError(e, 'Importa lineups'))
    } finally {
      setLoading(null)
    }
  }, [fixtureIdInput])

  const runLoadStored = useCallback(async () => {
    const fid = fixtureId()
    if (fid == null) return
    setLoading('stored')
    setError(null)
    try {
      setStored(await getSportApiLineups(fid))
    } catch (e) {
      setError(formatFetchError(e, 'Carica dati salvati'))
    } finally {
      setLoading(null)
    }
  }, [fixtureIdInput])

  const enabled = debug?.sportapi_enabled !== false

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
        fixture_id (interno DB, non api_fixture_id)
        <input
          type="number"
          value={fixtureIdInput}
          onChange={(e) => setFixtureIdInput(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
          placeholder="es. ID da tabella fixtures"
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

      {debug?.fixture ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800">
          <p className="font-semibold">Fixture API-Football</p>
          <p>
            DB id {debug.fixture.fixture_id} · API {debug.fixture.api_fixture_id} ·{' '}
            {debug.fixture.home_team_name} vs {debug.fixture.away_team_name}
          </p>
          <p>
            {debug.fixture.kickoff_at} · {debug.fixture.match_date} · round {debug.fixture.round ?? '—'}
          </p>
          <p className="mt-1">
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

      {stored?.mapping || stored?.fetched_at ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 text-xs">
          <p className="font-semibold text-emerald-950">Dati SportAPI salvati</p>
          <p>
            event_id {stored.mapping?.provider_event_id ?? '—'} · confidence{' '}
            {stored.mapping?.confidence_score ?? '—'} · confirmed{' '}
            {String(stored.confirmed ?? '—')}
          </p>
          <p>Ultimo fetch: {stored.fetched_at ?? '—'}</p>
          <p className="mt-2 font-medium">Home — titolari {stored.home?.players?.length ?? 0}</p>
          <ul className="max-h-24 overflow-auto font-mono text-[10px]">
            {(stored.home?.players ?? []).map((p) => (
              <li key={p.provider_player_id}>
                {p.jersey_number ?? '·'} {p.player_name} ({p.position ?? '—'})
              </li>
            ))}
          </ul>
          <p className="mt-1 font-medium">Home missing {stored.home?.missing_players?.length ?? 0}</p>
          <ul className="max-h-20 overflow-auto font-mono text-[10px]">
            {(stored.home?.missing_players ?? []).map((m) => (
              <li key={m.provider_player_id}>
                {m.player_name} — {m.reason ?? m.description ?? '—'}
              </li>
            ))}
          </ul>
          <p className="mt-2 font-medium">Away — titolari {stored.away?.players?.length ?? 0}</p>
          <ul className="max-h-24 overflow-auto font-mono text-[10px]">
            {(stored.away?.players ?? []).map((p) => (
              <li key={p.provider_player_id}>
                {p.jersey_number ?? '·'} {p.player_name} ({p.position ?? '—'})
              </li>
            ))}
          </ul>
          <p className="mt-1 font-medium">Away missing {stored.away?.missing_players?.length ?? 0}</p>
          <ul className="max-h-20 overflow-auto font-mono text-[10px]">
            {(stored.away?.missing_players ?? []).map((m) => (
              <li key={m.provider_player_id}>
                {m.player_name} — {m.reason ?? m.description ?? '—'}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
