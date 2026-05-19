import { useCallback, useEffect, useState } from 'react'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  adminBootstrapSerieA,
  adminIngestAvailability,
  adminIngestAvailabilityUpcoming,
  getAvailabilityFixtureFlow,
  adminIngestLineups,
  adminIngestPlayerMatchStats,
  buildPlayerSeasonProfiles,
  adminIngestPlayerStats,
  adminIngestStandings,
  adminIngestTeamStats,
  adminRefreshPostMatchday,
  adminRegenerateUpcomingPredictions,
  adminTestInjuriesApi,
  buildPlayerSotProfiles,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  getDataHealth,
  getIngestionRuns,
  getTeamShotStatsSummary,
  getAvailabilityApiRawList,
  getAvailabilityRawCheck,
  getAvailabilitySummary,
  getPlayerMatchDbSummary,
  getModelStatusWithOpts,
  getPlayerSotProfilesSummary,
  getUpcomingActiveWithOpts,
  postGenerateV04OffensiveCoreSotUpcoming,
  postGenerateV10SotUpcoming,
  postGenerateV11SotUpcoming,
  postRefreshUpcomingV04Pipeline,
  runBuildSotFeatures,
  runGenerateSotPredictions,
  runSotBacktest,
  type AdminRequestOpts,
  type ModelStatusResponse,
  type UpcomingActiveResponse,
} from '../lib/api'

import type { AvailabilityApiRawListResponse } from '../types/fixtureAvailability'
import { V04_MODEL, V10_MODEL, V11_MODEL, filterVersionsForUi, labelForModelVersion } from '../lib/modelVersions'

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
    if (typeof o.records_saved === 'number' && o.fixtures_checked != null) {
      const withN = Array.isArray(o.fixtures_with_availability) ? o.fixtures_with_availability.length : 0
      const withoutN = Array.isArray(o.fixtures_without_availability)
        ? o.fixtures_without_availability.length
        : 0
      const errN = Array.isArray(o.errors) ? o.errors.length : 0
      return [
        `Indisponibili prossima giornata: ${String(o.status ?? '—')}`,
        `fixture ${String(o.fixtures_checked ?? '—')}`,
        `API calls ${String(o.api_calls ?? '—')}`,
        `record salvati ${String(o.records_saved ?? '—')}`,
        `con indisponibili ${withN} · senza ${withoutN}`,
        errN ? `errori ${errN}` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    }
    if (typeof o.availability_records_upserted === 'number') {
      const top = Array.isArray(o.top_shooters_flagged) ? o.top_shooters_flagged.length : 0
      const errN = Array.isArray(o.errors) ? o.errors.length : 0
      return [
        `Indisponibili: status ${String(o.status ?? '—')}`,
        `fixture controllate ${String(o.fixtures_checked ?? '—')}`,
        `record upsert ${String(o.availability_records_upserted ?? '—')}`,
        `fixture-level ${String(o.records_fixture_level ?? '—')} · team-level ${String(o.records_team_level ?? '—')}`,
        `API calls ${String(o.api_calls ?? '—')} (fx ${String(o.api_calls_by_fixture ?? '—')} / team ${String(o.api_calls_by_team ?? '—')})`,
        `registry ok ${String(o.players_matched_to_registry ?? '—')}`,
        `registry mancanti ${String(o.players_not_matched_to_registry ?? '—')}`,
        top ? `top shooter segnalati ${top}` : '',
        errN ? `errori ${errN}` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    }
    if (Array.isArray(o.diagnosis) && o.diagnosis.length > 0) {
      const ps = o.player_search as Record<string, unknown> | undefined
      const q = ps?.query ? String(ps.query) : ''
      const apiChecks = o.api_checks as Record<string, { results?: number }> | undefined
      const bf = apiChecks?.by_fixture?.results ?? 0
      const ht = apiChecks?.home_team?.results ?? 0
      const at = apiChecks?.away_team?.results ?? 0
      return [
        `Debug availability${q ? ` (${q})` : ''}`,
        `by_fixture ${bf} · home ${ht} · away ${at}`,
        `diagnosi: ${o.diagnosis.slice(0, 3).join(' | ')}`,
      ].join(' · ')
    }
    if (typeof o.active_records === 'number' && o.season != null) {
      return [
        `Availability summary ${String(o.season)}`,
        `attivi ${String(o.active_records ?? '—')}`,
        `totale ${String(o.total_records ?? '—')}`,
        `con fixture ${String(o.active_with_fixture ?? '—')}`,
        `con registry ${String(o.active_with_registry ?? '—')}`,
      ].join(' · ')
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
    if (typeof o.status === 'string' && o.status === 'success') {
      if (
        o.architecture === 'explicit_terms_from_v04_plus_xg' ||
        o.architecture === 'explicit_terms_from_v04' ||
        o.xg_applied_count != null
      ) {
        return [
          `Formula esplicita v0.4 + xG`,
          `architecture: ${String(o.architecture ?? '')}`,
          `create/update: ${String(o.predictions_created_or_updated ?? '')}`,
          `xg applicati: ${String(o.xg_applied_count ?? '')}`,
          `xg fallback: ${String(o.xg_fallback_count ?? '')}`,
          `base allineata: ${String(o.aligned_base_terms_count ?? '')}`,
          `da revisionare: ${String(o.needs_review ?? '')}`,
        ].join(' · ')
      }
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
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<OpResult | null>(null)
  const [legacyOpen, setLegacyOpen] = useState(false)
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null)
  const [upcomingActive, setUpcomingActive] = useState<UpcomingActiveResponse | null>(null)
  const [cardsError, setCardsError] = useState<string | null>(null)
  const [availDebugFixtureId, setAvailDebugFixtureId] = useState('')
  const [availDebugPlayerSearch, setAvailDebugPlayerSearch] = useState('Rovella')
  const [apiRawList, setApiRawList] = useState<AvailabilityApiRawListResponse | null>(null)
  const [apiRawLoading, setApiRawLoading] = useState(false)
  const [apiRawTeamId, setApiRawTeamId] = useState('')
  const [apiRawFixtureId, setApiRawFixtureId] = useState('')
  const [apiRawDate, setApiRawDate] = useState('')
  const [apiRawPlayerFilter, setApiRawPlayerFilter] = useState('')

  const loadCards = useCallback(async () => {
    setCardsError(null)
    try {
      const s = await getModelStatusWithOpts(SEASON)
      setModelStatus(s)
      const mv = s.recommended_model_version || s.active_model_version || V11_MODEL
      const u = await getUpcomingActiveWithOpts(
        SEASON,
        { limit: 20, onlyNextRound: true, modelVersion: mv },
      )
      setUpcomingActive(u)
    } catch (e) {
      setModelStatus(null)
      setUpcomingActive(null)
      setCardsError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void loadCards()
  }, [loadCards])

  const loadApiRawList = useCallback(async () => {
    setApiRawLoading(true)
    try {
      const teamId = apiRawTeamId.trim() ? parseInt(apiRawTeamId.trim(), 10) : undefined
      const fixtureId = apiRawFixtureId.trim() ? parseInt(apiRawFixtureId.trim(), 10) : undefined
      if (apiRawTeamId.trim() && !Number.isFinite(teamId)) {
        throw new Error('team_id non valido')
      }
      if (apiRawFixtureId.trim() && !Number.isFinite(fixtureId)) {
        throw new Error('fixture_id non valido')
      }
      const data = await getAvailabilityApiRawList(SEASON, {
        teamId: Number.isFinite(teamId) ? teamId : undefined,
        fixtureId: Number.isFinite(fixtureId) ? fixtureId : undefined,
        date: apiRawDate.trim() || undefined,
      })
      setApiRawList(data)
    } catch (e) {
      setApiRawList({
        status: 'error',
        season: SEASON,
        message: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setApiRawLoading(false)
    }
  }, [apiRawTeamId, apiRawFixtureId, apiRawDate])

  const apiRawFilteredRecords = (() => {
    const rows = apiRawList?.records ?? []
    const q = apiRawPlayerFilter.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => (r.player_name ?? '').toLowerCase().includes(q))
  })()

  const runAction = useCallback(
    async (action: AdminAction) => {
      const t0 = performance.now()
      setPendingId(action.id)
      try {
        const data = await action.run()
        const ms = Math.round(performance.now() - t0)
        setLastResult({
          endpoint: action.endpoint,
          httpStatus: 200,
          durationMs: ms,
          ok: true,
          message: pickMessage(data, 'Operazione completata.'),
          body: data,
        })
        if (['refresh-v04-pipeline', 'gen-v04', 'gen-v10', 'gen-v11', 'refresh-cards'].includes(action.id)) {
          void loadCards()
        }
        if (action.id === 'refresh-v04-pipeline' || action.id === 'gen-v04' || action.id === 'gen-v10' || action.id === 'gen-v11') {
          try {
            sessionStorage.setItem('sot_admin_refresh_upcoming', String(Date.now()))
          } catch {
            /* ignore */
          }
        }
      } catch (err) {
        const ms = Math.round(performance.now() - t0)
        if (err instanceof AdminHttpError) {
          setLastResult({
            endpoint: action.endpoint,
            httpStatus: err.status,
            durationMs: ms,
            ok: false,
            message: err.message,
            body: err.body,
          })
        } else {
          setLastResult({
            endpoint: action.endpoint,
            httpStatus: '—',
            durationMs: ms,
            ok: false,
            message: err instanceof Error ? err.message : String(err),
          })
        }
      } finally {
        setPendingId(null)
      }
    },
    [loadCards, modelStatus],
  )

  const section1: AdminAction[] = [
    {
      id: 'bootstrap',
      label: 'Aggiorna calendario e squadre',
      description: 'Bootstrap Serie A (lega, squadre, calendario) da API-Football.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/bootstrap`,
      run: () => adminBootstrapSerieA(SEASON),
    },
    {
      id: 'official-lineups',
      label: 'Aggiorna formazioni ufficiali',
      description:
        'Recupera fixtures/lineups per le partite vicine (48h) o in corso. Non modifica la formula v1.1.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/lineups`,
      run: () => adminIngestLineups(SEASON),
    },
    {
      id: 'player-match-stats',
      label: 'Aggiorna statistiche giocatori',
      description: 'Importa fixtures/players per le partite finite e salva player_match_stats.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/player-match-stats`,
      run: () => adminIngestPlayerMatchStats(SEASON),
    },
    {
      id: 'player-season-profiles',
      label: 'Calcola profili giocatori',
      description: 'Aggrega player_match_stats e aggiorna player_season_profiles.',
      endpoint: `POST /api/admin/features/player-season-profiles/serie-a/${SEASON}/build`,
      run: () => buildPlayerSeasonProfiles(SEASON),
    },
    {
      id: 'team-stats',
      label: 'Aggiorna statistiche squadra partite finite',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/team-stats`,
      run: () => adminIngestTeamStats(SEASON),
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
      id: 'availability-upcoming',
      label: 'Aggiorna indisponibili prossima giornata',
      description:
        'Recupera injuries per ogni partita upcoming tramite injuries?fixture= e salva solo record applicabili alla partita.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/availability-upcoming`,
      run: () => adminIngestAvailabilityUpcoming(SEASON, { daysAhead: 14 }),
    },
    {
      id: 'availability-summary',
      label: 'Verifica availability summary',
      description: 'Conteggi record attivi/inattivi in player_availability per la stagione.',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/availability-summary`,
      run: () => getAvailabilitySummary(SEASON),
    },
    {
      id: 'profiles',
      label: 'Ricalcola profili giocatori',
      endpoint: `POST /api/features/player-sot-profiles/serie-a/${SEASON}/build`,
      run: () => buildPlayerSotProfiles(SEASON),
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
      id: 'gen-v04',
      label: 'Genera previsioni v0.4 prossima giornata',
      description: `Modello: ${V04_MODEL}`,
      endpoint: `POST /api/predictions/sot/serie-a/${SEASON}/generate-v04-offensive-core-sot`,
      run: () => postGenerateV04OffensiveCoreSotUpcoming(SEASON),
    },
    {
      id: 'gen-v11',
      label: 'Genera modello v1.1 SOT',
      description: 'Stage 1: Produzione offensiva composita — solo dati reali (nessun fallback).',
      endpoint: `POST /api/predictions/sot/serie-a/${SEASON}/generate-v11-sot`,
      run: () => postGenerateV11SotUpcoming(SEASON),
    },
    {
      id: 'gen-v10',
      label: 'Genera modello v1.0 SOT',
      description: `Formula esplicita v0.4 + xG. Richiede ${V04_MODEL} già generato. Modello: ${V10_MODEL}.`,
      endpoint: `POST /api/predictions/sot/serie-a/${SEASON}/generate-v10-sot`,
      run: () => postGenerateV10SotUpcoming(SEASON),
    },
    {
      id: 'verify-model',
      label: 'Verifica stato modello',
      endpoint: `GET /api/predictions/sot/serie-a/${SEASON}/model-status`,
      run: async () => {
        const s = await getModelStatusWithOpts(SEASON)
        setModelStatus(s)
        return s
      },
    },
    {
      id: 'verify-upcoming',
      label: 'Verifica prossima giornata attiva',
      endpoint: `GET /api/predictions/sot/serie-a/${SEASON}/upcoming-active`,
      run: async () => {
        const mv = modelStatus?.recommended_model_version || modelStatus?.active_model_version || V11_MODEL
        const u = await getUpcomingActiveWithOpts(SEASON, {
          limit: 20,
          onlyNextRound: true,
          modelVersion: mv,
        })
        setUpcomingActive(u)
        return u
      },
    },
    {
      id: 'refresh-v04-pipeline',
      label: 'Aggiorna prossima giornata completa',
      description:
        'Pipeline: fixture, stats squadra, classifica, giocatori, formazioni, disponibilità (best-effort), profili, previsioni v0.4, stato modello.',
      endpoint: `POST /api/admin/pipeline/serie-a/${SEASON}/refresh-upcoming-v04`,
      run: () => postRefreshUpcomingV04Pipeline(SEASON),
    },
  ]

  const section3: AdminAction[] = [
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
      endpoint: `GET /api/admin/data-health/serie-a/${SEASON}`,
      run: () => getDataHealth(SEASON),
    },
    {
      id: 'team-shot-stats-summary',
      label: 'Verifica copertura statistiche tiri',
      description:
        'Bloccati e Shots off Goal: % copertura colonne fixture_team_stats; campione sintetico in risposta JSON.',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/team-shot-stats-summary`,
      run: () => getTeamShotStatsSummary(SEASON),
    },
    {
      id: 'injuries-test',
      label: 'Prova lettura API infortuni (nessuna scrittura)',
      endpoint: `GET /api/admin/api-football/injuries/test?season=${SEASON}`,
      run: () => adminTestInjuriesApi(SEASON),
    },
    {
      id: 'availability-fixture-flow',
      label: 'Debug flusso indisponibili fixture',
      description:
        'Mostra request injuries?fixture=, risultati API, record DB e audit applicabili per la fixture.',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/availability-fixture-flow`,
      run: () => {
        const fid = parseInt(availDebugFixtureId.trim(), 10)
        if (!Number.isFinite(fid) || fid < 1) {
          return Promise.reject(new Error('Inserisci un fixture_id numerico valido'))
        }
        return getAvailabilityFixtureFlow(SEASON, fid)
      },
    },
    {
      id: 'availability-raw-check',
      label: 'Debug indisponibili fixture',
      description:
        'Confronta injuries API (fixture/team/league) vs DB. Usa fixture_id interno; opzionale player_search (es. Rovella).',
      endpoint: `GET /api/admin/debug/serie-a/${SEASON}/availability-raw-check`,
      run: () => {
        const fid = parseInt(availDebugFixtureId.trim(), 10)
        if (!Number.isFinite(fid) || fid < 1) {
          return Promise.reject(new Error('Inserisci un fixture_id numerico valido'))
        }
        return getAvailabilityRawCheck(SEASON, fid, availDebugPlayerSearch.trim() || undefined)
      },
    },
    {
      id: 'profiles-summary',
      label: 'Riepilogo profili giocatori (GET)',
      endpoint: `GET /api/features/player-sot-profiles/serie-a/${SEASON}/summary`,
      run: () => getPlayerSotProfilesSummary(SEASON),
    },
  ]

  const legacyActions: AdminAction[] = [
    {
      id: 'legacy-post-matchday',
      label: 'Legacy: pipeline post-giornata v0.1 (+ backtest)',
      description: 'Lungo: include feature/predizioni completate v0.1, backtest e upcoming v0.1.',
      endpoint: `POST /api/admin/refresh/serie-a/${SEASON}/post-matchday`,
      run: () => adminRefreshPostMatchday(SEASON),
    },
    {
      id: 'legacy-regen-upcoming',
      label: 'Legacy: rigenera feature + upcoming v0.1',
      endpoint: `POST build-upcoming + generate-upcoming`,
      run: () => adminRegenerateUpcomingPredictions(SEASON),
    },
    {
      id: 'legacy-build-features',
      label: 'Legacy: costruisci feature complete v0.1',
      endpoint: `POST /api/features/sot/serie-a/${SEASON}/build`,
      run: () => runBuildSotFeatures(SEASON),
    },
    {
      id: 'legacy-gen-predictions',
      label: 'Legacy: genera previsioni complete v0.1',
      endpoint: `POST /api/predictions/sot/serie-a/${SEASON}/generate`,
      run: () => runGenerateSotPredictions(SEASON),
    },
    {
      id: 'legacy-backtest',
      label: 'Legacy: esegui backtest',
      endpoint: `POST /api/backtest/sot/serie-a/${SEASON}/run`,
      run: () => runSotBacktest(SEASON),
    },
    {
      id: 'legacy-build-upcoming-feat',
      label: 'Legacy: costruisci feature partite future',
      endpoint: `POST /api/features/sot/serie-a/${SEASON}/build-upcoming`,
      run: () => buildUpcomingSotFeatures(SEASON),
    },
    {
      id: 'legacy-gen-upcoming',
      label: 'Legacy: genera previsioni partite future v0.1',
      endpoint: `POST /api/predictions/sot/serie-a/${SEASON}/generate-upcoming`,
      run: () => generateUpcomingSotPredictions(SEASON),
    },
    {
      id: 'availability-legacy',
      label: 'Legacy: indisponibili league/season (debug)',
      description:
        'NON usare per audit/modello. Chiama injuries?league&season e può popolare record storici team-level.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/availability`,
      run: () => adminIngestAvailability(SEASON),
    },
  ]

  const refreshCardsAction: AdminAction = {
    id: 'refresh-cards',
    label: 'Aggiorna stato modello',
    endpoint: `GET /api/predictions/sot/serie-a/${SEASON}/model-status + upcoming-active`,
    run: async () => {
      await loadCards()
      return { refreshed: true }
    },
  }

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-3xl space-y-6 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold text-slate-900">Admin / Strumenti tecnici</h1>
          <p className="mt-2 text-sm text-slate-600">
            Operazioni su dati Serie A e modello v0.4. Ogni pulsante ha timeout lato client; solo il pulsante cliccato
            mostra «In corso…».
          </p>
          <p className="mt-1 text-xs text-slate-500">Stagione {SEASON}</p>
        </header>

        {cardsError ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
            Card stato: {cardsError}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-2xl border border-indigo-200 bg-white p-4 shadow-sm">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-indigo-800">Stato modello attivo</h2>
            <dl className="mt-2 space-y-1 text-xs text-slate-700">
              <div>
                <dt className="text-slate-500">Raccomandato</dt>
                <dd className="font-mono text-[11px] font-semibold text-indigo-900">
                  {modelStatus?.recommended_model_version ?? '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Attivo</dt>
                <dd className="font-mono text-[11px]">
                  {modelStatus?.active_model_version ?? '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Fixture upcoming (totali)</dt>
                <dd>{modelStatus?.upcoming_fixtures_total ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Versioni in DB</dt>
                <dd className="max-h-24 overflow-y-auto font-mono text-[10px]">
                  {filterVersionsForUi(modelStatus?.available_model_versions ?? [])
                    .map((v) => labelForModelVersion(v.model_version))
                    .join(', ') || '—'}
                </dd>
              </div>
              {(modelStatus?.warnings?.length ?? 0) > 0 ? (
                <div>
                  <dt className="text-amber-700">Warning</dt>
                  <dd className="text-amber-900">{(modelStatus?.warnings ?? []).join(' · ')}</dd>
                </div>
              ) : null}
            </dl>
            <ActionButton action={refreshCardsAction} pendingId={pendingId} onRun={runAction} />
          </div>

          <div className="rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-emerald-900">Prossima giornata attiva</h2>
            <dl className="mt-2 space-y-1 text-xs text-slate-700">
              <div>
                <dt className="text-slate-500">Modello in uso</dt>
                <dd className="font-mono text-[11px]">{upcomingActive?.model_version_used ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Partite / predictions (squadre)</dt>
                <dd>
                  {upcomingActive?.matches_count ?? 0} partite ·{' '}
                  {(upcomingActive?.matches ?? []).reduce((acc, m) => {
                    const h = m.home_prediction ? 1 : 0
                    const a = m.away_prediction ? 1 : 0
                    return acc + h + a
                  }, 0)}{' '}
                  lati con prediction
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Prima / ultima partita</dt>
                <dd className="font-mono text-[10px]">
                  {upcomingActive?.matches?.[0]?.kickoff_at
                    ? String(upcomingActive.matches[0].kickoff_at)
                    : '—'}{' '}
                  →{' '}
                  {upcomingActive?.matches?.length
                    ? String(upcomingActive.matches[upcomingActive.matches.length - 1]!.kickoff_at)
                    : '—'}
                </dd>
              </div>
              {(upcomingActive?.warnings?.length ?? 0) > 0 ? (
                <div>
                  <dt className="text-amber-700">Warning</dt>
                  <dd className="text-amber-900">{(upcomingActive?.warnings ?? []).join(' · ')}</dd>
                </div>
              ) : null}
            </dl>
            <button
              type="button"
              disabled={pendingId !== null}
              className="mt-3 w-full rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-left text-xs font-medium text-emerald-950 hover:bg-emerald-100/80 disabled:opacity-50"
              onClick={() =>
                void runAction({
                  id: 'verify-upcoming-header',
                  label: '',
                  endpoint: `GET …/upcoming-active`,
                  run: async () => {
                    const mv =
                      modelStatus?.recommended_model_version || modelStatus?.active_model_version || V11_MODEL
                    const u = await getUpcomingActiveWithOpts(SEASON, {
                      limit: 20,
                      onlyNextRound: true,
                      modelVersion: mv,
                    })
                    setUpcomingActive(u)
                    return u
                  },
                })
              }
            >
              {pendingId === 'verify-upcoming-header' ? 'In corso…' : 'Verifica prossima giornata'}
            </button>
          </div>
        </div>

        <Section
          title="1 — Aggiornamento dati Serie A"
          subtitle="Ingestion da API-Football dove richiesto."
        >
          <div className="flex flex-col gap-3">
            {section1.map((a) => (
              <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
            ))}
          </div>
        </Section>

        <Section
          title="2 — Modello attivo v0.4"
          subtitle="Flusso consigliato per la dashboard e Prossima giornata."
        >
          <div className="flex flex-col gap-3">
            <div className="rounded-xl border-2 border-indigo-400 bg-indigo-50/80 p-1">
              <ActionButton
                action={section2.find((x) => x.id === 'refresh-v04-pipeline')!}
                pendingId={pendingId}
                onRun={runAction}
              />
            </div>
            {section2
              .filter((x) => x.id !== 'refresh-v04-pipeline')
              .map((a) => (
                <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
              ))}
          </div>
        </Section>

        <Section title="3 — Diagnostica" subtitle="Letture e controlli senza modificare il modello v0.4.">
          <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50/50 p-3">
            <p className="text-xs font-medium text-violet-950">Parametri debug indisponibili fixture</p>
            <label className="mt-2 block text-[11px] text-slate-600">
              fixture_id (interno DB)
              <input
                type="number"
                value={availDebugFixtureId}
                onChange={(e) => setAvailDebugFixtureId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                placeholder="es. 1234"
              />
            </label>
            <label className="mt-2 block text-[11px] text-slate-600">
              player_search (opzionale)
              <input
                type="text"
                value={availDebugPlayerSearch}
                onChange={(e) => setAvailDebugPlayerSearch(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                placeholder="Rovella"
              />
            </label>
          </div>
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50/50 p-3">
            <p className="text-xs font-semibold text-amber-950">Debug avanzato — Indisponibili API raw</p>
            <p className="mt-1 text-[10px] leading-relaxed text-amber-950">
              Questa sezione mostra la risposta grezza dell&apos;API per debug. Può includere record di tutta
              la stagione e NON viene usata per audit partita o modello.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <label className="block text-[11px] text-slate-600">
                team_id (opz.)
                <input
                  type="number"
                  value={apiRawTeamId}
                  onChange={(e) => setApiRawTeamId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                />
              </label>
              <label className="block text-[11px] text-slate-600">
                fixture_id (opz.)
                <input
                  type="number"
                  value={apiRawFixtureId}
                  onChange={(e) => setApiRawFixtureId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                />
              </label>
              <label className="block text-[11px] text-slate-600">
                date (YYYY-MM-DD, opz.)
                <input
                  type="text"
                  value={apiRawDate}
                  onChange={(e) => setApiRawDate(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                  placeholder="2025-05-17"
                />
              </label>
            </div>
            <label className="mt-2 block text-[11px] text-slate-600">
              Cerca giocatore (filtro locale)
              <input
                type="text"
                value={apiRawPlayerFilter}
                onChange={(e) => setApiRawPlayerFilter(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                placeholder="Zaniolo, Rovella"
              />
            </label>
            <button
              type="button"
              disabled={apiRawLoading}
              onClick={() => void loadApiRawList()}
              className="mt-3 rounded-lg bg-amber-700 px-3 py-2 text-xs font-medium text-white hover:bg-amber-800 disabled:opacity-50"
            >
              {apiRawLoading ? 'Caricamento...' : 'Carica tutti gli indisponibili API'}
            </button>
            {apiRawList ? (
              <div className="mt-3 space-y-2 text-[11px] text-slate-700">
                <p>
                  <span className="font-medium">request:</span>{' '}
                  <span className="font-mono">{apiRawList.request ?? '-'}</span>
                </p>
                <p>
                  results: {String(apiRawList.results ?? '-')} | api_league_id:{' '}
                  {String(apiRawList.api_league_id ?? '-')} | league_internal_id:{' '}
                  {String(apiRawList.league_internal_id ?? '-')}
                </p>
                {apiRawList.errors && apiRawList.errors.length > 0 ? (
                  <p className="text-rose-700">errors: {apiRawList.errors.join('; ')}</p>
                ) : null}
                {apiRawList.coverage?.injuries != null ? (
                  <p>coverage.injuries: {String(apiRawList.coverage.injuries)}</p>
                ) : null}
                {apiRawList.message ? <p className="text-rose-700">{apiRawList.message}</p> : null}
                <div className="max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white">
                  <table className="w-full text-left text-[10px]">
                    <thead className="sticky top-0 bg-slate-100">
                      <tr>
                        <th className="px-2 py-1">Data</th>
                        <th className="px-2 py-1">Fx API</th>
                        <th className="px-2 py-1">Squadra</th>
                        <th className="px-2 py-1">Giocatore</th>
                        <th className="px-2 py-1">Tipo</th>
                        <th className="px-2 py-1">Motivo</th>
                        <th className="px-2 py-1">Fonte</th>
                        <th className="px-2 py-1">Pl API</th>
                        <th className="px-2 py-1">Tm API</th>
                      </tr>
                    </thead>
                    <tbody>
                      {apiRawFilteredRecords.length === 0 ? (
                        <tr>
                          <td colSpan={9} className="px-2 py-2 text-slate-500">
                            Nessun record
                          </td>
                        </tr>
                      ) : (
                        apiRawFilteredRecords.map((r, i) => (
                          <tr key={i} className="border-t border-slate-100">
                            <td className="px-2 py-1 whitespace-nowrap">{r.fixture_date ?? '-'}</td>
                            <td className="px-2 py-1">{r.fixture_api_id ?? '-'}</td>
                            <td className="px-2 py-1">{r.team_name ?? '-'}</td>
                            <td className="px-2 py-1">{r.player_name ?? '-'}</td>
                            <td className="px-2 py-1">{r.type ?? r.parsed_type ?? '-'}</td>
                            <td className="px-2 py-1">{r.reason ?? '-'}</td>
                            <td className="px-2 py-1">{r.source ?? '-'}</td>
                            <td className="px-2 py-1">{r.player_api_id ?? '-'}</td>
                            <td className="px-2 py-1">{r.team_api_id ?? '-'}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="text-slate-500">
                  Righe in tabella: {apiRawFilteredRecords.length}
                  {apiRawPlayerFilter.trim() ? ` (filtrate da ${apiRawList.records?.length ?? 0})` : ''}
                </p>
              </div>
            ) : null}
          </div>
          <div className="flex flex-col gap-3">
            {section3.map((a) => (
              <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
            ))}
          </div>
        </Section>

        <div className="rounded-2xl border border-slate-300 bg-slate-50 p-4">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left text-sm font-semibold text-slate-800"
            onClick={() => setLegacyOpen((o) => !o)}
          >
            <span>4 — Legacy / storico (v0.1 e strumenti non usati nel flusso principale)</span>
            <span className="text-slate-500">{legacyOpen ? '▾' : '▸'}</span>
          </button>
          {legacyOpen ? (
            <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-4">
              {legacyActions.map((a) => (
                <ActionButton key={a.id} action={a} pendingId={pendingId} onRun={runAction} />
              ))}
            </div>
          ) : null}
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
    </div>
  )
}
