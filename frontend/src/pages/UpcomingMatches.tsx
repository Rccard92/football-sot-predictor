import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  getNextRoundQuickReport,
  getNextRoundQuickReportForCompetition,
  getUpcomingFixtureDetail,
  getUpcomingFixtureDetailForCompetition,
  resolveModelStatus,
  type ModelLimitations,
  type ModelStatusResponse,
  type UpcomingActiveMatchRow,
  type UpcomingActiveResponse,
} from '../lib/api'
import { CompetitionBadge } from '../components/CompetitionSelector'
import { useCompetition } from '../contexts/CompetitionContext'
import { QuickPlayReportSection } from '../components/upcoming'
import {
  V11_MODEL,
  V20_MODEL,
  filterVersionsForUi,
  formatInputsAvailable,
  formatModelStatusFootnote,
  labelForModelVersion,
  labelForOperatingMode,
  stageBadgeForModel,
  stageDescriptionForModel,
} from '../lib/modelVersions'

const MatchCard = lazy(async () => {
  const m = await import('../components/upcoming/MatchCard')
  return { default: m.MatchCard }
})

function ReportSkeleton() {
  return (
    <div className="space-y-3 rounded-2xl border border-indigo-200/80 bg-white p-4 shadow-sm">
      <div className="h-5 w-48 animate-pulse rounded bg-slate-200" />
      <div className="h-32 animate-pulse rounded-xl bg-slate-100" />
    </div>
  )
}

export function UpcomingMatches() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const season = selectedCompetition?.season ?? DEFAULT_SEASON
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [data, setData] = useState<UpcomingActiveResponse | null>(null)
  const [buildBusy, setBuildBusy] = useState(false)
  const [predBusy, setPredBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const didInitModel = useRef(false)

  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null)
  const [detailMatch, setDetailMatch] = useState<UpcomingActiveMatchRow | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const s =
        (await resolveModelStatus(selectedCompetition, season)) ??
        ({
          status: 'not_initialized',
          season,
          active_model_version: null,
          available_model_versions: [],
          warnings: ['Nessun campionato selezionato.'],
          message: 'Modello non ancora inizializzato',
        } satisfies ModelStatusResponse)
      setStatus(s)
      const recommended = s.recommended_model_version || s.active_model_version || null
      if (!didInitModel.current) {
        if (s.recommended_model_version) setSelectedModel(s.recommended_model_version)
        else if (s.active_model_version) setSelectedModel(s.active_model_version)
        didInitModel.current = true
      }
      const mv = selectedModel || recommended
      const res =
        selectedCompetitionId != null
          ? await getNextRoundQuickReportForCompetition(selectedCompetitionId, {
              limit: 20,
              onlyNextRound: true,
              modelVersion: mv,
            })
          : await getNextRoundQuickReport(season, {
              limit: 20,
              onlyNextRound: true,
              modelVersion: mv,
            })
      setData(res)
    } catch (e) {
      setData(null)
      setStatus(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedModel, season, selectedCompetitionId, selectedCompetition])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('sot_admin_refresh_upcoming')
      if (!raw) return
      const ts = Number(raw)
      if (!Number.isFinite(ts) || Date.now() - ts > 120_000) {
        sessionStorage.removeItem('sot_admin_refresh_upcoming')
        return
      }
      sessionStorage.removeItem('sot_admin_refresh_upcoming')
      void load()
    } catch {
      /* ignore */
    }
  }, [load])

  const loadDetail = useCallback(
    async (fixtureId: number) => {
      setDetailLoading(true)
      setDetailError(null)
      const mv = selectedModel || status?.recommended_model_version || status?.active_model_version
      try {
        const res =
          selectedCompetitionId != null
            ? await getUpcomingFixtureDetailForCompetition(selectedCompetitionId, fixtureId, {
                modelVersion: mv,
              })
            : await getUpcomingFixtureDetail(season, fixtureId, { modelVersion: mv })
        if (res.status === 'error' || !res.match) {
          setDetailError(res.message ?? 'Dettaglio partita non disponibile.')
          setDetailMatch(null)
          return
        }
        setDetailMatch(res.match)
      } catch (e) {
        setDetailError(e instanceof Error ? e.message : String(e))
        setDetailMatch(null)
      } finally {
        setDetailLoading(false)
      }
    },
    [selectedCompetitionId, season, selectedModel, status],
  )

  const openDetail = useCallback(
    async (fixtureId: number) => {
      if (selectedFixtureId === fixtureId && detailMatch) {
        setSelectedFixtureId(null)
        setDetailMatch(null)
        setDetailError(null)
        return
      }
      setSelectedFixtureId(fixtureId)
      setDetailMatch(null)
      await loadDetail(fixtureId)
    },
    [selectedFixtureId, detailMatch, loadDetail],
  )

  const hasPredictions =
    data?.matches?.some(
      (m) =>
        Boolean(m.home_prediction && m.away_prediction) ||
        m.total_expected_sot != null ||
        (m.markets?.[0]?.predicted_value != null),
    ) ?? false

  const activeModel = status?.active_model_version ?? null
  const recommendedModel = status?.recommended_model_version ?? null
  const modelInView = selectedModel ?? null
  const isDifferentFromActive = Boolean(activeModel && modelInView && activeModel !== modelInView)
  const isRecommendedView =
    Boolean(recommendedModel && modelInView && recommendedModel === modelInView)

  const modelStatusFootnote = formatModelStatusFootnote(
    status?.v20_operating_context ?? {
      lineups_probable_only: status?.lineups_probable_only,
      next_round_lineup_coverage_pct: status?.next_round_lineup_coverage_pct,
      lineups_ready: status?.lineups_ready,
      operating_mode: status?.operating_mode,
    },
  )

  const reportInfo = [
    ...(data?.info ?? []),
    ...(data?.warnings ?? []).filter((w) => /disponibili per tutto il turno/i.test(w)),
  ]
  const reportWarnings = (data?.warnings ?? []).filter(
    (w) => !/disponibili per tutto il turno/i.test(w),
  )

  const limitationsResolved: ModelLimitations = data?.model_limitations ?? {
    lineups_considered: false,
    injuries_considered: false,
    odds_automatically_imported: false,
    note:
      'Questa versione baseline usa solo statistiche squadra storiche. Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate.',
  }

  return (
    <div className="space-y-8 pb-8">
      <header className="space-y-3 pt-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Prossima giornata{selectedCompetition ? ` — ${selectedCompetition.name}` : ''}
          </h1>
          <CompetitionBadge />
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Previsioni SOT per le prossime partite. Con <strong>v2.0</strong> vedi anche il confronto rispetto alla base{' '}
            <strong>v1.1</strong>.
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="font-semibold text-slate-900">
              Modello globale:{' '}
              <span className="font-normal text-slate-800">
                {status?.global_model_label ?? labelForModelVersion(V20_MODEL)}
              </span>
              {status?.operating_mode ? (
                <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                  {labelForOperatingMode(status.operating_mode)}
                </span>
              ) : null}
            </p>
            {status?.competition_name ? (
              <p className="text-xs text-slate-600">
                Campionato: <span className="font-medium text-slate-900">{status.competition_name}</span>
              </p>
            ) : null}
            {status?.inputs_available ? (
              <p className="text-xs text-slate-600">
                Input disponibili:{' '}
                <span className="font-medium text-slate-800">{formatInputsAvailable(status.inputs_available)}</span>
              </p>
            ) : null}
            {modelStatusFootnote ? (
              <p className="text-xs text-slate-600">{modelStatusFootnote}</p>
            ) : null}
            <p className="font-semibold text-slate-900">
              Modello attivo:{' '}
              <span className="font-normal text-slate-800">{status?.active_model_version ?? '—'}</span>
              {isRecommendedView && recommendedModel === activeModel ? (
                <span className="ml-2 text-[11px] font-medium text-emerald-700">(raccomandato)</span>
              ) : null}
              {modelInView === V20_MODEL || modelInView === V11_MODEL ? (
                <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-800">
                  Stage: {stageBadgeForModel(modelInView)}
                </span>
              ) : null}
            </p>
            {modelInView === V20_MODEL || modelInView === V11_MODEL ? (
              <p className="text-xs text-slate-600">{stageDescriptionForModel(modelInView)}</p>
            ) : null}
            {status?.stable_model_version && modelInView === V11_MODEL ? (
              <p className="text-xs text-slate-500">
                Modello stabile: {labelForModelVersion(status.stable_model_version)}
              </p>
            ) : null}
            {recommendedModel && recommendedModel !== activeModel ? (
              <p className="text-xs text-slate-600">
                Modello raccomandato: <span className="font-medium text-slate-900">{recommendedModel}</span>
              </p>
            ) : null}
            {isDifferentFromActive ? (
              <p className="text-xs text-slate-600">
                Modello in vista: <span className="font-medium text-slate-900">{modelInView}</span>
              </p>
            ) : null}
            <div className="pt-2">
              <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Seleziona modello
              </label>
              <select
                value={selectedModel ?? status?.recommended_model_version ?? ''}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 shadow-sm"
              >
                {filterVersionsForUi(status?.available_model_versions ?? [])
                  .sort((a, b) => {
                    const rec = status?.recommended_model_version
                    if (a.model_version === rec) return -1
                    if (b.model_version === rec) return 1
                    if (a.model_version === V11_MODEL) return -1
                    if (b.model_version === V11_MODEL) return 1
                    return a.model_version.localeCompare(b.model_version)
                  })
                  .map((v) => (
                    <option key={v.model_version} value={v.model_version}>
                      {labelForModelVersion(v.model_version)}
                      {v.model_version === status?.recommended_model_version ? ' (consigliato)' : ''}
                      {v.is_available_for_upcoming ? '' : ' (no upcoming)'}
                    </option>
                  ))}
              </select>
            </div>
          </div>
          <div className="space-y-2 text-xs text-slate-600">
            {data?.round ? (
              <p>
                Prossimo turno: <span className="font-medium text-slate-900">{data.round}</span>
              </p>
            ) : null}
            {data?.lineup_coverage?.next_round_fixture_count ? (
              <p>
                Coverage formazioni:{' '}
                <span className="font-medium text-slate-900">
                  {data.lineup_coverage.next_round_sportapi_lineups_count ?? 0}/
                  {data.lineup_coverage.next_round_fixture_count} (
                  {data.lineup_coverage.next_round_coverage_pct ?? 0}%)
                </span>
              </p>
            ) : null}
            <p className="text-xs text-slate-500">
              Dettagli tecnici in{' '}
              <Link to="/match-variable-audit" className="font-medium text-slate-700 underline">
                Audit Variabili
              </Link>{' '}
              e in{' '}
              <Link to="/match-analysis-framework" className="font-medium text-slate-700 underline">
                Framework Analisi
              </Link>
              .
            </p>
          </div>
        </div>
      </header>

      {!loading && !error && reportInfo.length ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-sm text-emerald-950 shadow-sm">
          <p className="font-medium">Stato formazioni</p>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm">
            {reportInfo.map((msg, i) => (
              <li key={i}>{msg}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {!loading && !error && reportWarnings.length ? (
        <details className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950 shadow-sm">
          <summary className="cursor-pointer select-none font-medium">Warning modello (tecnico)</summary>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm">
            {reportWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">{error}</div>
      ) : null}

      {loading ? (
        <div className="space-y-4">
          <ReportSkeleton />
        </div>
      ) : !data?.matches.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <p className="text-slate-700">Nessuna partita futura trovata nel calendario.</p>
        </div>
      ) : !hasPredictions ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-6 shadow-sm">
          <p className="font-medium text-amber-950">Genera previsioni per le prossime partite</p>
          <p className="mt-2 text-sm text-amber-900">
            Non ci sono ancora previsioni sui tiri in porta per le partite programmate. Costruisci prima le
            informazioni statistiche sulle partite future, poi genera le previsioni.
          </p>
          <details className="mt-4 rounded-2xl border border-amber-200 bg-white/40">
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-amber-950 marker:hidden [&::-webkit-details-marker]:hidden">
              Strumenti tecnici (build/generate)
            </summary>
            <div className="border-t border-amber-200 px-4 py-4">
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  disabled={buildBusy || predBusy}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
                  onClick={async () => {
                    setBuildBusy(true)
                    setActionMsg(null)
                    try {
                      await buildUpcomingSotFeatures(season)
                      setActionMsg('Dati aggiornati per le partite future.')
                      await load()
                    } catch (e) {
                      setActionMsg(e instanceof Error ? e.message : String(e))
                    } finally {
                      setBuildBusy(false)
                    }
                  }}
                >
                  {buildBusy ? 'Caricamento…' : 'Costruisci dati partite future'}
                </button>
                <button
                  type="button"
                  disabled={buildBusy || predBusy}
                  className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:opacity-50"
                  onClick={async () => {
                    setPredBusy(true)
                    setActionMsg(null)
                    try {
                      await generateUpcomingSotPredictions(season)
                      setActionMsg('Previsioni future generate.')
                      await load()
                    } catch (e) {
                      setActionMsg(e instanceof Error ? e.message : String(e))
                    } finally {
                      setPredBusy(false)
                    }
                  }}
                >
                  {predBusy ? 'Caricamento…' : 'Genera previsioni future'}
                </button>
              </div>
            </div>
          </details>
          {actionMsg ? <p className="mt-3 text-sm text-slate-800">{actionMsg}</p> : null}
        </div>
      ) : (
        <div className="space-y-6">
          <p className="text-sm text-slate-600">
            {data.round ? (
              <>
                <span className="font-medium text-slate-800">{data.round}</span>
                <span className="text-slate-400"> · </span>
              </>
            ) : null}
            {data.matches_count} partite
          </p>
          <QuickPlayReportSection
            matches={data.matches}
            modelVersion={modelInView}
            onRefreshComplete={async () => {
              await load()
              if (selectedFixtureId != null) {
                await loadDetail(selectedFixtureId)
              }
            }}
            onOpenDetail={(id) => void openDetail(id)}
            selectedFixtureId={selectedFixtureId}
          />

          {detailLoading ? (
            <p className="text-sm text-slate-600">Carico dettagli partita…</p>
          ) : null}
          {detailError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
              {detailError}
            </div>
          ) : null}
          {detailMatch && !detailLoading ? (
            <Suspense
              fallback={
                <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" aria-label="Caricamento dettaglio" />
              }
            >
              <MatchCard match={detailMatch} limitations={limitationsResolved} />
            </Suspense>
          ) : null}

          <section className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-600 shadow-sm">
            <p className="font-semibold text-slate-900">Nota modello</p>
            <p className="mt-1">{limitationsResolved.note}</p>
          </section>
        </div>
      )}
    </div>
  )
}
