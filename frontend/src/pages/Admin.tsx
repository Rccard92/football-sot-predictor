import { useCallback, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  adminIngestLineups,
  adminIngestPlayerStats,
  adminIngestStandings,
  adminIngestTeamStats,
  getIngestionRuns,
  getTeamShotStatsSummary,
  getPlayerMatchDbSummary,
  bootstrapCompetition,
  buildCompetitionPlayerProfiles,
  getCompetitionDataHealth,
  ingestCompetitionPlayerStats,
  ingestCompetitionTeamStats,
  type AdminRequestOpts,
} from '../lib/api'

import { CompetitionsAdminPanel } from '../components/admin/CompetitionsAdminPanel'
import { ContextBanner } from '../components/ContextBanner'
import { SportApiDebugPanel } from '../components/admin/SportApiDebugPanel'
import { useCompetition } from '../contexts/CompetitionContext'
import { useModelSelection } from '../contexts/ModelSelectionContext'

const SEASON = DEFAULT_SEASON

type OpResult = {
  endpoint: string
  httpStatus: number | string
  durationMs: number
  ok: boolean
  message: string
  body?: unknown
}

function pickMessage(payload: unknown, okFallback: string): string {
  if (payload && typeof payload === 'object') {
    const o = payload as Record<string, unknown>
    if (typeof o.status === 'string' && (o.fixtures_processed != null || o.player_match_stats_upserted != null)) {
      const p = o.fixtures_processed
      const s = o.fixtures_skipped
      const m = o.player_match_stats_upserted
      const pl = o.players_upserted
      return `Player match stats: status ${String(o.status)} · processate ${String(p ?? '—')} · saltate ${String(s ?? '—')} · righe match ${String(m ?? '—')} · giocatori toccati ${String(pl ?? '—')}`
    }
    if (typeof o.fixtures_checked === 'number' || typeof o.lineups_upserted === 'number') {
      const nav = Array.isArray(o.not_available_yet) ? o.not_available_yet.length : 0
      const errN = Array.isArray(o.errors) ? o.errors.length : 0
      return [
        `Formazioni: status ${String(o.status ?? '—')}`,
        `controllate ${String(o.fixtures_checked ?? '—')}`,
        `con lineups ${String(o.fixtures_with_lineups ?? '—')}`,
        `senza lineups ${String(o.fixtures_without_lineups ?? '—')}`,
        `upsert squadre ${String(o.lineups_upserted ?? '—')}`,
        `giocatori ${String(o.lineup_players_upserted ?? '—')}`,
        nav ? `non ancora disp. ${nav}` : '',
        errN ? `errori ${errN}` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    }
    if (typeof o.status === 'string' && o.profiles_created_or_updated != null) {
      const updated = o.profiles_created_or_updated
      const impact = o.profiles_with_shooting_impact
      const lowMin = o.profiles_without_enough_minutes
      const sample = Array.isArray(o.top_players_sample) ? o.top_players_sample : []
      const topName =
        sample.length > 0 && sample[0] && typeof sample[0] === 'object'
          ? String((sample[0] as Record<string, unknown>).player_name ?? '')
          : ''
      const warnN = Array.isArray(o.warnings) ? o.warnings.length : 0
      const errN = Array.isArray(o.errors) ? o.errors.length : 0
      return [
        `Profili giocatori: status ${String(o.status)}`,
        `aggiornati ${String(updated ?? '—')}`,
        `con shooting impact ${String(impact ?? '—')}`,
        `minuti insufficienti ${String(lowMin ?? '—')}`,
        topName ? `top: ${topName}` : '',
        warnN || errN ? `warnings ${warnN} · errori ${errN}` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    }
    if (typeof o.message === 'string' && o.message.trim()) return o.message
    if (typeof o.status === 'string' && o.status === 'skipped' && typeof o.reason === 'string') {
      return `Operazione saltata: ${o.reason}`
    }
  }
  return okFallback
}

type AdminAction = {
  id: string
  label: string
  description?: string
  endpoint: string
  run: (opts?: AdminRequestOpts) => Promise<unknown>
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      {subtitle ? <p className="mt-1 text-xs text-slate-600">{subtitle}</p> : null}
      <div className="mt-4">{children}</div>
    </div>
  )
}

function ActionButton({
  action,
  pendingId,
  onRun,
}: {
  action: AdminAction
  pendingId: string | null
  onRun: (a: AdminAction) => void
}) {
  const busy = pendingId === action.id
  const anyBusy = pendingId !== null
  return (
    <button
      type="button"
      disabled={anyBusy}
      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-800 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      onClick={() => onRun(action)}
    >
      <span className="block">{busy ? 'In corso…' : action.label}</span>
      {action.description ? (
        <span className="mt-1 block text-xs font-normal text-slate-500">{action.description}</span>
      ) : null}
      <span className="mt-1 block font-mono text-[10px] text-slate-400">{action.endpoint}</span>
    </button>
  )
}

export function Admin() {
  const { selectedCompetitionId } = useCompetition()
  const { selectedModelVersion } = useModelSelection()
  const [searchParams] = useSearchParams()
  const sportapiFixtureRef = searchParams.get('sportapi_fixture') ?? undefined
  const sportapiSectionRef = useRef<HTMLDivElement | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<OpResult | null>(null)

  const runAction = useCallback(async (action: AdminAction) => {
    const t0 = performance.now()
    setPendingId(action.id)
    try {
      const data = await action.run()
      const ms = Math.round(performance.now() - t0)
      const dataStatus =
        data && typeof data === 'object' && 'status' in data
          ? String((data as Record<string, unknown>).status)
          : 'success'
      const okish =
        dataStatus === 'success' ||
        dataStatus === 'partial_success' ||
        dataStatus === 'partial_error'
      setLastResult({
        endpoint: action.endpoint,
        httpStatus: 200,
        durationMs: ms,
        ok: okish,
        message: pickMessage(data, 'Operazione completata.'),
        body: data,
      })
    } catch (err) {
      const ms = Math.round(performance.now() - t0)
      if (err instanceof AdminHttpError) {
        const body = err.body
        const bodyStatus =
          body && typeof body === 'object' && 'status' in body
            ? String((body as Record<string, unknown>).status)
            : null
        const partial =
          bodyStatus === 'error' ||
          bodyStatus === 'partial_error' ||
          bodyStatus === 'partial_success'
        setLastResult({
          endpoint: action.endpoint,
          httpStatus: err.status,
          durationMs: ms,
          ok: partial,
          message: partial && body ? pickMessage(body, err.message) : err.message,
          body: err.body,
        })
      } else {
        const raw = err instanceof Error ? err.message : String(err)
        const isNetwork =
          raw === 'Failed to fetch' ||
          /network|abort|fetch/i.test(raw) ||
          err instanceof TypeError
        setLastResult({
          endpoint: action.endpoint,
          httpStatus: '—',
          durationMs: ms,
          ok: false,
          message: isNetwork
            ? 'Errore di rete o backend non raggiungibile. Controlla /api/health e Railway logs.'
            : raw,
        })
      }
    } finally {
      setPendingId(null)
    }
  }, [])

  const requireCompetition = () => {
    if (selectedCompetitionId == null) {
      throw new Error('Seleziona un campionato in alto prima di eseguire questa azione.')
    }
    return selectedCompetitionId
  }

  const section1: AdminAction[] = [
    {
      id: 'bootstrap',
      label: 'Aggiorna calendario e squadre',
      description: 'Bootstrap campionato selezionato da API-Football.',
      endpoint: `POST /api/admin/competitions/{id}/ingest/bootstrap`,
      run: () => bootstrapCompetition(requireCompetition(), false),
    },
    {
      id: 'official-lineups',
      label: 'Aggiorna formazioni ufficiali',
      description: 'Recupera fixtures/lineups per le partite vicine (48h) o in corso.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/lineups`,
      run: () => adminIngestLineups(SEASON),
    },
    {
      id: 'player-match-stats',
      label: 'Aggiorna statistiche giocatori',
      description: 'Importa fixtures/players per le partite finite e salva player_match_stats.',
      endpoint: `POST /api/admin/competitions/{id}/ingest/player-match-stats`,
      run: () => ingestCompetitionPlayerStats(requireCompetition(), false),
    },
    {
      id: 'player-season-profiles',
      label: 'Calcola profili giocatori',
      description: 'Aggrega player_match_stats e aggiorna player_season_profiles.',
      endpoint: `POST /api/admin/competitions/{id}/features/player-season-profiles/build`,
      run: () => buildCompetitionPlayerProfiles(requireCompetition(), false),
    },
    {
      id: 'team-stats',
      label: 'Aggiorna statistiche squadra partite finite',
      endpoint: `POST /api/admin/competitions/{id}/ingest/team-stats`,
      run: () => ingestCompetitionTeamStats(requireCompetition(), false),
    },
    {
      id: 'standings',
      label: 'Aggiorna classifica',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/standings`,
      run: () => adminIngestStandings(SEASON),
    },
    {
      id: 'player-lineups',
      label: 'Aggiorna dati giocatori e formazioni',
      description: 'Statistiche giocatori e formazioni partite finite (due step in sequenza).',
      endpoint: `POST …/player-stats poi …/lineups`,
      run: async () => {
        await adminIngestPlayerStats(SEASON)
        return adminIngestLineups(SEASON)
      },
    },
    {
      id: 'dataset-base',
      label: 'Aggiorna tutto il dataset base',
      description: 'Squadra finite + giocatori + formazioni in sequenza.',
      endpoint: `POST team-stats, player-stats, lineups`,
      run: async () => {
        await adminIngestTeamStats(SEASON)
        await adminIngestPlayerStats(SEASON)
        return adminIngestLineups(SEASON)
      },
    },
  ]

  const section2: AdminAction[] = [
    {
      id: 'player-db-summary',
      label: 'Riepilogo Player DB',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/player-db-summary`,
      run: () => getPlayerMatchDbSummary(SEASON),
    },
    {
      id: 'ingest-runs',
      label: 'Mostra ultimi ingestion runs',
      endpoint: `GET /api/admin/ingest/runs`,
      run: () => getIngestionRuns(),
    },
    {
      id: 'data-health',
      label: 'Controlla copertura dati',
      endpoint: `GET /api/admin/data-health/competitions/{id}`,
      run: () =>
        getCompetitionDataHealth(requireCompetition(), { modelVersion: selectedModelVersion }),
    },
    {
      id: 'team-shot-stats-summary',
      label: 'Verifica copertura statistiche tiri',
      description:
        'Bloccati e Shots off Goal: % copertura colonne fixture_team_stats; campione sintetico in risposta JSON.',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/team-shot-stats-summary`,
      run: () => getTeamShotStatsSummary(SEASON),
    },
  ]

  return (
    <div className="space-y-6 pb-8">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold text-slate-900">Admin / Strumenti tecnici</h1>
          <p className="mt-2 text-sm text-slate-600">
            Operazioni sul campionato selezionato. Ogni pulsante ha timeout lato client.
          </p>
          <ContextBanner showModelSelector={false} />
        </header>

        <CompetitionsAdminPanel />

        <Section
          title="1 — Aggiornamento dati campionato"
          subtitle="Ingestion da API-Football dove richiesto."
        >
          <div className="flex flex-col gap-3">
            {section1.map((a) => (
              <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
            ))}
          </div>
        </Section>

        <Section title="2 — Diagnostica" subtitle="Letture e controlli, nessuna scrittura.">
          <div className="flex flex-col gap-3">
            {section2.map((a) => (
              <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
            ))}
          </div>
        </Section>

        <div ref={sportapiSectionRef}>
          <Section
            title="3 — SportAPI Debug"
            subtitle="Fonte secondaria RapidAPI: mapping, probabili/ufficiali lineups, missingPlayers."
          >
            <SportApiDebugPanel initialFixtureRef={sportapiFixtureRef} />
          </Section>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Risultato ultima operazione</h2>
          {lastResult ? (
            <div className="mt-3 space-y-2 text-sm">
              <p className={lastResult.ok ? 'text-emerald-800' : 'text-rose-800'}>{lastResult.message}</p>
              <ul className="list-inside list-disc text-xs text-slate-600">
                <li>
                  Endpoint: <span className="font-mono">{lastResult.endpoint}</span>
                </li>
                <li>HTTP: {String(lastResult.httpStatus)}</li>
                <li>Durata: {lastResult.durationMs} ms</li>
              </ul>
              {lastResult.body !== undefined ? (
                <details className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <summary className="cursor-pointer text-xs font-medium text-slate-700">JSON risposta</summary>
                  <pre className="mt-2 max-h-96 overflow-auto rounded bg-white p-2 text-[11px] text-slate-800">
                    {JSON.stringify(lastResult.body, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-500">Esegui un&apos;azione per vedere endpoint, durata e payload.</p>
          )}
        </div>
    </div>
  )
}
