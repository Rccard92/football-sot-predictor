import { useCallback, useEffect, useState } from 'react'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  adminBootstrapSerieA,
  adminIngestAvailability,
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
      id: 'availability',
      label: 'Aggiorna disponibilità / infortuni',
      description: 'Import prudente assenze; richiede API configurata.',
      endpoint: `POST /api/admin/ingest/serie-a/${SEASON}/availability`,
      run: () => adminIngestAvailability(SEASON),
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
