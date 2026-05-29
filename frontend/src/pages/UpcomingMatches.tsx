import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getModelStatusForCompetition,
  getNextRoundQuickReportForCompetition,
  getUpcomingFixtureDetailForCompetition,
  type ModelLimitations,
  type ModelStatusResponse,
  type UpcomingActiveMatchRow,
  type UpcomingActiveResponse,
} from '../lib/api'
import { ContextBanner } from '../components/ContextBanner'
import { useCompetition } from '../contexts/CompetitionContext'
import { useModelSelection } from '../contexts/ModelSelectionContext'
import { QuickPlayReportSection } from '../components/upcoming'
import {
  filterVersionsForUi,
  formatInputsAvailable,
  formatModelStatusFootnote,
  isV21EngineNotReadyRow,
  isV21ManifestInvalidRow,
  labelForModelVersion,
  labelForOperatingMode,
  stageBadgeForModel,
  stageDescriptionForModel,
  V21_MODEL,
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
  const { selectedModelVersion, selectedModelLabel } = useModelSelection()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [data, setData] = useState<UpcomingActiveResponse | null>(null)

  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null)
  const [detailMatch, setDetailMatch] = useState<UpcomingActiveMatchRow | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const missingPrediction =
    data?.status === 'missing_prediction' || (data?.matches_count === 0 && data?.model_version_used != null)

  const load = useCallback(async () => {
    if (selectedCompetitionId == null) {
      setLoading(false)
      setData(null)
      setStatus(null)
      setError('Seleziona un campionato per visualizzare la prossima giornata.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const s = await getModelStatusForCompetition(selectedCompetitionId)
      setStatus(s)
      const res = await getNextRoundQuickReportForCompetition(selectedCompetitionId, {
        limit: 20,
        onlyNextRound: true,
        modelVersion: selectedModelVersion,
      })
      setData(res)
    } catch (e) {
      setData(null)
      setStatus(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId, selectedModelVersion])

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
      if (selectedCompetitionId == null) return
      setDetailLoading(true)
      setDetailError(null)
      try {
        const res = await getUpcomingFixtureDetailForCompetition(selectedCompetitionId, fixtureId, {
          modelVersion: selectedModelVersion,
        })
        if (res.status === 'missing_prediction') {
          setDetailError(
            res.message ??
              `Prediction ${labelForModelVersion(selectedModelVersion)} non disponibile per questa partita.`,
          )
          setDetailMatch(null)
          return
        }
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
    [selectedCompetitionId, selectedModelVersion],
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
    !missingPrediction &&
    (data?.matches?.some(
      (m) =>
        Boolean(m.home_prediction && m.away_prediction) ||
        m.total_expected_sot != null ||
        (m.markets?.[0]?.predicted_value != null),
    ) ??
      false)

  const modelInView = selectedModelVersion

  const modelStatusFootnote = formatModelStatusFootnote(
    status?.v20_operating_context ?? {
      lineups_probable_only: status?.lineups_probable_only,
      next_round_lineup_coverage_pct: status?.next_round_lineup_coverage_pct,
      lineups_ready: status?.lineups_ready,
      operating_mode: status?.operating_mode,
    },
  )

  const v21EngineNotReady = useMemo(() => {
    const rows = status?.available_model_versions ?? []
    const row = rows.find((r) => r.model_version === modelInView)
    return modelInView === V21_MODEL && row != null && isV21EngineNotReadyRow(row)
  }, [modelInView, status?.available_model_versions])

  const v21ManifestInvalid = useMemo(() => {
    const rows = status?.available_model_versions ?? []
    const row = rows.find((r) => r.model_version === modelInView)
    return modelInView === V21_MODEL && row != null && isV21ManifestInvalidRow(row)
  }, [modelInView, status?.available_model_versions])

  const reportInfo = [
    ...(data?.info ?? []),
    ...(data?.warnings ?? []).filter((w) => /disponibili per tutto il turno/i.test(w)),
  ]
  const reportWarnings = (data?.warnings ?? []).filter(
    (w) => !/disponibili per tutto il turno/i.test(w),
  )

  const auditListUrl =
    selectedCompetitionId != null
      ? `/match-variable-audit?competition_id=${selectedCompetitionId}&model_version=${encodeURIComponent(selectedModelVersion)}`
      : '/match-variable-audit'

  const limitationsResolved: ModelLimitations = data?.model_limitations ?? {
    lineups_considered: false,
    injuries_considered: false,
    odds_automatically_imported: false,
    note:
      'Questa versione baseline usa solo statistiche squadra storiche. Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate.',
  }

  const selectedModelStatusRow = status?.available_model_versions?.find(
    (r) => r.model_version === selectedModelVersion,
  )

  return (
    <div className="space-y-8 pb-8">
      <header className="space-y-3 pt-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Prossima giornata{selectedCompetition ? ` — ${selectedCompetition.name}` : ''}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Previsioni SOT per le prossime partite del modello selezionato. Nessun fallback automatico ad altre
            versioni.
          </p>
        </div>

        <ContextBanner
          extra={
            <>
              {data?.round ? (
                <p>
                  Prossimo turno: <span className="font-medium text-slate-900">{data.round}</span>
                </p>
              ) : null}
              <p>
                Prediction trovate:{' '}
                <span className="font-medium text-slate-900">{data?.matches_count ?? 0}</span>
                {selectedModelStatusRow?.next_round_predictions_count != null ? (
                  <span className="text-slate-500">
                    {' '}
                    (next round DB: {selectedModelStatusRow.next_round_predictions_count})
                  </span>
                ) : null}
              </p>
              {status?.operating_mode ? (
                <p>
                  Modalità v2.0:{' '}
                  <span className="font-medium">{labelForOperatingMode(status.operating_mode)}</span>
                </p>
              ) : null}
              {modelStatusFootnote ? <p>{modelStatusFootnote}</p> : null}
            </>
          }
        />

        <div className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm">
          <p className="font-semibold text-slate-900">
            Modello in uso: <span className="font-normal">{selectedModelLabel}</span>
            <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-800">
              Stage: {stageBadgeForModel(modelInView)}
              {modelInView === V21_MODEL ? ' · Sperimentale' : ''}
            </span>
          </p>
          <p className="mt-1 text-slate-600">{stageDescriptionForModel(modelInView)}</p>
          {status?.inputs_available ? (
            <p className="mt-1 text-slate-600">
              Input disponibili: {formatInputsAvailable(status.inputs_available)}
            </p>
          ) : null}
          {v21ManifestInvalid ? (
            <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-950">
              Manifest v2.1 non valido: il modello sperimentale è temporaneamente disabilitato.
            </p>
          ) : null}
          {v21EngineNotReady && !v21ManifestInvalid ? (
            <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              Engine v2.1 non pronto per questo campionato.
            </p>
          ) : null}
          <p className="mt-2 text-xs text-slate-500">
            Versioni in DB:{' '}
            {filterVersionsForUi(status?.available_model_versions ?? [])
              .map((v) => labelForModelVersion(v.model_version))
              .join(', ') || '—'}
          </p>
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
      ) : missingPrediction ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-6 shadow-sm">
          <p className="font-medium text-amber-950">
            Prediction non ancora generate per questo modello.
          </p>
          <p className="mt-2 text-sm text-amber-900">
            Vai in Admin e rigenera Prossima giornata per{' '}
            <strong>{selectedModelLabel}</strong>
            {selectedCompetition ? ` (${selectedCompetition.name})` : ''}.
          </p>
          <p className="mt-2 text-xs text-amber-800">
            {data?.message ?? 'Nessuna prediction per il model_version selezionato.'}
          </p>
        </div>
      ) : !data?.matches?.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <p className="text-slate-700">Nessuna partita futura trovata nel calendario.</p>
        </div>
      ) : !hasPredictions ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-6 shadow-sm">
          <p className="font-medium text-amber-950">Prediction incomplete per il modello selezionato</p>
          <p className="mt-2 text-sm text-amber-900">
            Ci sono partite nel turno ma mancano prediction per {selectedModelLabel}. Rigenera da Admin.
          </p>
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
            {data.matches_count} partite · modello {selectedModelLabel}
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

          {detailLoading ? <p className="text-sm text-slate-600">Carico dettagli partita…</p> : null}
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
            <p className="mt-2">
              <Link to={auditListUrl} className="font-medium text-slate-700 underline">
                Audit variabili
              </Link>
            </p>
          </section>
        </div>
      )}
    </div>
  )
}
