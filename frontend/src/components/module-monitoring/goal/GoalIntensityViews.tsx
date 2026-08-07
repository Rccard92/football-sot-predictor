/**
 * Goal Intensity v5 — Viste workspace Module Monitoring
 */

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import type {
  GoalIntensityV5Benchmark,
  GoalIntensityV5Calibration,
  GoalIntensityV5Candidates,
  GoalIntensityV5DataHealth,
  GoalIntensityV5Dimensions,
  GoalIntensityV5ExportStatus,
  GoalIntensityV5Filters,
  GoalIntensityV5Overview,
  GoalIntensityV5Phase2C,
  GoalIntensityV5ProspectiveResults,
  GoalIntensityV5Readiness,
  GoalIntensityV5Stability,
} from '../../../lib/cecchinoGoalIntensityV5Api'
import {
  PHASE_2C_FREEZE_CONFIRM,
  downloadGoalIntensityV5AnalysisPack,
  downloadGoalIntensityV5ReadinessDossier,
  freezeGoalIntensityV5Phase2CBundle,
  getGoalIntensityV5Benchmark,
  getGoalIntensityV5Calibration,
  getGoalIntensityV5Candidates,
  getGoalIntensityV5DataHealth,
  getGoalIntensityV5Dimensions,
  getGoalIntensityV5ExportStatus,
  getGoalIntensityV5Overview,
  getGoalIntensityV5Phase2CCandidates,
  getGoalIntensityV5ProspectiveResults,
  getGoalIntensityV5Readiness,
  getGoalIntensityV5Stability,
} from '../../../lib/cecchinoGoalIntensityV5Api'
import { MonitoringMetricCard } from '../MonitoringMetricCard'
import { fmtPct } from '../moduleMonitoringUi'
import {
  BENCHMARK_MODEL_LABELS,
  BENCHMARK_MODEL_ORDER,
  PHASE_2C_ACTIVE_CANDIDATES,
  PHASE_2C_ARCHIVED_CANDIDATES,
  PHASE_2C_HOLDOUT_MODELS,
  coverageCount,
  evidenceLabelIt,
  phase2cFreezeDisabled,
  progressDerived,
  resolveCompleted,
  resolveMinimum,
  resolvePending,
  resolveSnapshots,
} from './goalIntensityProgress'

type ViewProps = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-32 w-full rounded-xl bg-slate-100" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="h-24 rounded-xl bg-slate-100" />
        <div className="h-24 rounded-xl bg-slate-100" />
        <div className="h-24 rounded-xl bg-slate-100" />
        <div className="h-24 rounded-xl bg-slate-100" />
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center">
      <p className="text-sm text-slate-600">{message}</p>
    </div>
  )
}

export function GoalIntensityOverviewView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Overview(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento overview Goal Intensity v5')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  const covGlobal = (data.coverage_global || {}) as Record<string, unknown>
  const covPeriod = (data.coverage_in_period || {}) as Record<string, unknown>
  const coverageLegacy = (data.coverage || {}) as Record<string, unknown>
  const globalSnapshots =
    coverageCount(covGlobal, 'snapshots') ??
    (coverageLegacy.snapshots_global as number | undefined) ??
    (data.global_snapshots as number | undefined)
  const globalCompleted =
    coverageCount(covGlobal, 'completed') ??
    (coverageLegacy.completed_global as number | undefined)
  const globalPending =
    coverageCount(covGlobal, 'pending') ??
    (coverageLegacy.pending_global as number | undefined)
  const periodSnapshots =
    coverageCount(covPeriod, 'snapshots') ??
    (coverageLegacy.snapshots_in_period as number | undefined) ??
    (data.snapshots_in_period as number | undefined)
  const periodCompleted = coverageCount(covPeriod, 'completed')
  const periodPending =
    coverageCount(covPeriod, 'pending') ??
    (coverageLegacy.pending_in_period as number | undefined)
  const minimumSample =
    (coverageLegacy.minimum_prospective_matches as number | undefined) ??
    (data.minimum_sample as number | undefined) ??
    200
  const isOfficial =
    data.operational_status === 'official_support' ||
    Boolean((data as { post_cutover_qc_only?: boolean }).post_cutover_qc_only) ||
    Boolean((data as { no_gate_on_200?: boolean }).no_gate_on_200)
  const operationalFallback = isOfficial ? 'Supporto ufficiale' : 'Preview monitorata'
  const signalsFallback = isOfficial ? 'Non collegato ai Segnali' : 'Bloccata'
  const decisionFallback = isOfficial
    ? 'Modulo di supporto attivo'
    : 'Continua monitoraggio'

  return (
    <div className="space-y-4" data-testid="gi-monitoring-overview">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Intensità Goal v5</h3>
        <p className="mt-1 text-xs text-slate-600">
          {isOfficial
            ? 'Supporto ufficiale post-cutover. Snapshot solo bundle ufficiale. Signals non collegati.'
            : 'Copertura globale e di periodo tenute separate. Signals sempre bloccati.'}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard
          label="Stato operativo"
          value={String(data.operational_status_label_it || data.operational_status || operationalFallback)}
        />
        <MonitoringMetricCard
          label="Maturità scientifica"
          value={String(
            data.scientific_maturity_label_it ||
              (data as { scientific_evidence_label_it?: string }).scientific_evidence_label_it ||
              data.scientific_maturity ||
              '—',
          )}
        />
        <MonitoringMetricCard
          label="Prossimo passaggio"
          value={String(
            data.recommended_next_step_label_it ||
              data.recommended_next_step ||
              '—',
          )}
        />
        <MonitoringMetricCard
          label="Integrazione Signals"
          value={String(data.signals_integration_status_label_it || data.signals_integration_status || signalsFallback)}
        />
      </div>

      {isOfficial ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <MonitoringMetricCard
            label="Ruolo"
            value={String(
              (data as { role_label_it?: string }).role_label_it ||
                (data as { role?: string }).role ||
                'Supporto contestuale mercati goal',
            )}
          />
          <MonitoringMetricCard
            label="Evidenza"
            value={String(
              (data as { scientific_evidence_label_it?: string }).scientific_evidence_label_it ||
                data.scientific_maturity_label_it ||
                'Validazione esterna completata',
            )}
          />
          <MonitoringMetricCard
            label="Raccolta"
            value={String(
              (data as { collection_note_it?: string }).collection_note_it ||
                'Snapshot post-cutover',
            )}
          />
        </div>
      ) : null}

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {isOfficial ? 'Snapshot post-cutover (globali)' : 'Copertura globale'}
        </h4>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard label="Snapshot globali" value={globalSnapshots == null ? '—' : String(globalSnapshots)} />
          <MonitoringMetricCard label="Completed globali" value={globalCompleted == null ? '—' : String(globalCompleted)} />
          <MonitoringMetricCard label="Pending globali" value={globalPending == null ? '—' : String(globalPending)} />
          {isOfficial ? (
            <MonitoringMetricCard label="Quality monitoring" value="Post-cutover QC" />
          ) : (
            <MonitoringMetricCard label="Campione minimo" value={String(minimumSample)} />
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Copertura nel periodo</h4>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <MonitoringMetricCard label="Snapshot nel periodo" value={periodSnapshots == null ? '—' : String(periodSnapshots)} />
          <MonitoringMetricCard label="Completed nel periodo" value={periodCompleted == null ? '—' : String(periodCompleted)} />
          <MonitoringMetricCard label="Pending nel periodo" value={periodPending == null ? '—' : String(periodPending)} />
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        Decisione automatica:{' '}
        {String(data.current_decision_label_it || data.current_decision || decisionFallback)}
      </div>

      {(Boolean(covGlobal?.first_snapshot) || Boolean(covGlobal?.last_snapshot)) && (
        <p className="text-xs text-slate-500">
          Copertura globale: {String(covGlobal?.first_snapshot || '—')} →{' '}
          {String(covGlobal?.last_snapshot || '—')}
          {covPeriod?.last_snapshot != null && (
            <> · Periodo fino a {String(covPeriod.last_snapshot)}</>
          )}
        </p>
      )}

      {data.warnings && data.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <ul className="list-disc pl-4 space-y-1">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function GoalIntensityDimensionsView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Dimensions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Dimensions(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento dimensioni Goal Intensity v5')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  type DimRow = {
    key?: string
    label?: string
    components?: Array<{ key?: string; label?: string; description?: string }>
  }

  const rawDims = data.dimensions
  let dimList: DimRow[] = []
  if (Array.isArray(rawDims)) {
    dimList = rawDims as DimRow[]
  } else if (Array.isArray(data.dimensions_list)) {
    dimList = data.dimensions_list
  } else if (rawDims && typeof rawDims === 'object') {
    dimList = Object.values(
      rawDims as Record<
        string,
        {
          key?: string
          label?: string
          label_it?: string
          metrics?: Array<{
            key?: string
            label?: string
            n?: number
            missing?: number
            mean?: number | null
            median?: number | null
          }>
        }
      >,
    ).map((d) => ({
      key: d.key,
      label: d.label || d.label_it,
      components: (d.metrics || []).map((m) => ({
        key: m.key,
        label: m.label,
        description:
          m.n != null
            ? `n=${m.n} missing=${m.missing ?? 0} mean=${m.mean ?? '—'} median=${m.median ?? '—'}`
            : undefined,
      })),
    }))
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Quattro dimensioni distinte</h3>
        <p className="mt-1 text-xs text-slate-600">
          Produzione offensiva, Solidità difensiva, Ritmo partita, Stabilità offensiva.
          {data.snapshot_count != null && (
            <> · Snapshot nel periodo: {String(data.snapshot_count)}</>
          )}
        </p>
      </div>

      {dimList.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {dimList.map((dim, idx) => (
            <div key={dim.key || idx} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <h4 className="text-sm font-semibold text-slate-800">{dim.label}</h4>
              {dim.components && dim.components.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {dim.components.map((comp, cidx) => (
                    <li key={comp.key || cidx} className="flex items-start gap-2">
                      <span className="text-slate-400">•</span>
                      <div>
                        <span className="font-medium text-slate-800">{comp.label}</span>
                        {comp.description && <p className="mt-0.5 text-slate-500">{comp.description}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState message="Nessuna dimensione disponibile" />
      )}
    </div>
  )
}

export function GoalIntensityCandidatesView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Candidates | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Candidates(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento candidati Goal Intensity v5')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  const completedN = data.completed_n as number | undefined
  const pendingN = data.pending_n as number | undefined
  const totalSnaps = data.total_snapshots as number | undefined

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Candidati Goal Intensity v5</h3>
        <p className="mt-1 text-xs text-slate-600">
          Primary, Challenger, Benchmark, Diagnostico — confronto candidati per selezione finale.
        </p>
        {(completedN != null || pendingN != null) && (
          <p className="mt-2 text-xs text-slate-500">
            Completed: {completedN ?? 0} · Pending: {pendingN ?? 0}
            {totalSnaps != null && ` · Totale snapshot: ${totalSnaps}`}
          </p>
        )}
      </div>

      {data.candidates && data.candidates.length > 0 ? (
        <div className="space-y-3">
          {data.candidates.map((cand, idx) => (
            <div
              key={(cand.id || cand.candidate_id || idx) as string}
              className={`rounded-xl border px-4 py-3 ${
                cand.role === 'Primary'
                  ? 'border-violet-200 bg-violet-50'
                  : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-slate-800">
                    {(cand.id || cand.candidate_id) as string}
                  </h4>
                  <p className="text-xs text-slate-600">{cand.role}</p>
                </div>
                {cand.active != null && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      cand.active
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {cand.active ? 'Attivo' : 'Inattivo'}
                  </span>
                )}
              </div>
              {cand.description && <p className="mt-2 text-xs text-slate-600">{cand.description}</p>}
              {cand.formula && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-slate-700">Formula</summary>
                  <pre className="mt-1 text-xs text-slate-600 whitespace-pre-wrap">{cand.formula}</pre>
                </details>
              )}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState message="Nessun candidato disponibile" />
      )}
    </div>
  )
}

export function GoalIntensityProspectiveResultsView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5ProspectiveResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5ProspectiveResults(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento risultati prospettici')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Risultati prospettici</h3>
        <p className="mt-1 text-xs text-slate-600">
          Progressione raccolta snapshot e completamento risultati per calibrazione candidati.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard
          label="Snapshot totali"
          value={data.snapshots_count == null ? '—' : String(data.snapshots_count)}
        />
        <MonitoringMetricCard
          label="Completati"
          value={data.completed_count == null ? '—' : String(data.completed_count)}
        />
        <MonitoringMetricCard
          label="Pending"
          value={data.pending_count == null ? '—' : String(data.pending_count)}
        />
        <MonitoringMetricCard
          label="Completamento"
          value={data.completed_progress == null ? '—' : fmtPct(data.completed_progress)}
        />
      </div>
    </div>
  )
}

export function GoalIntensityCalibrationView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Calibration | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Calibration(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento calibrazione')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Calibrazione</h3>
        <p className="mt-1 text-xs text-slate-600">
          Stato calibrazione candidati e qualità stime probabilistiche.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard
          label="Stato calibrazione"
          value={data.calibration_status || '—'}
        />
        <MonitoringMetricCard
          label="Candidati calibrati"
          value={data.candidates_calibrated == null ? '—' : String(data.candidates_calibrated)}
        />
        <MonitoringMetricCard
          label="Campione"
          value={data.sample_size == null ? '—' : String(data.sample_size)}
        />
        <MonitoringMetricCard
          label="Qualità"
          value={data.calibration_quality || '—'}
        />
      </div>
    </div>
  )
}

export function GoalIntensityStabilityView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Stability | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Stability(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento stabilità')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Stabilità</h3>
        <p className="mt-1 text-xs text-slate-600">
          Stabilità temporale e consistenza cross-fold dei candidati.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MonitoringMetricCard
          label="Stato stabilità"
          value={data.stability_status || '—'}
        />
        <MonitoringMetricCard
          label="Consistenza temporale"
          value={data.temporal_consistency == null ? '—' : fmtPct(data.temporal_consistency)}
        />
        <MonitoringMetricCard
          label="Consistenza cross-fold"
          value={data.cross_fold_consistency == null ? '—' : fmtPct(data.cross_fold_consistency)}
        />
      </div>
    </div>
  )
}

type ReadinessGate = {
  key?: string
  label_it?: string
  label?: string
  status?: string
  value?: unknown
  threshold?: unknown
}

function readinessGateList(data: GoalIntensityV5Readiness): ReadinessGate[] {
  const tech = (data.technical_gates as { gates?: ReadinessGate[] } | undefined)?.gates || []
  const prosp = (data.prospective_gates as { gates?: ReadinessGate[] } | undefined)?.gates || []
  const flat = (data.readiness_gates as ReadinessGate[] | undefined) || []
  return [...tech, ...prosp, ...flat]
}

export function GoalIntensityReadinessView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Readiness | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Readiness(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento readiness')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  const handleDownloadDossier = async () => {
    setDownloading(true)
    try {
      await downloadGoalIntensityV5ReadinessDossier({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId,
        source_cohort: cohortFilter,
      })
      toast.success('Download dossier avviato')
    } catch (err) {
      toast.error(`Download dossier non riuscito: ${String(err)}`)
    } finally {
      setDownloading(false)
    }
  }

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  const gates = readinessGateList(data)
  const progressRaw = (data.prospective_progress || {}) as Record<string, unknown>
  const normalized = (data.monitoring_normalized || {}) as Record<string, unknown>
  const completed = resolveCompleted(progressRaw, normalized)
  const pending = resolvePending(progressRaw, normalized)
  const snapshots = resolveSnapshots(progressRaw, normalized)
  const minimum = resolveMinimum(progressRaw, normalized, 200)
  const derived = progressDerived(completed, minimum)
  const progressPct =
    typeof progressRaw.progress_pct === 'number' ? progressRaw.progress_pct : derived.progress_pct
  const remaining =
    typeof progressRaw.remaining === 'number' ? progressRaw.remaining : derived.remaining
  const excess = typeof progressRaw.excess === 'number' ? progressRaw.excess : derived.excess
  const minimumReached =
    typeof progressRaw.minimum_reached === 'boolean'
      ? progressRaw.minimum_reached
      : derived.minimum_reached
  const benchmark = (data.phase_2b_benchmark || {}) as Record<string, unknown>

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Readiness</h3>
        <p className="mt-1 text-xs text-slate-600">
          Stato operativo, maturità scientifica e gate di monitoraggio. Signals sempre bloccati.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard label="Completed" value={String(completed)} />
        <MonitoringMetricCard label="Pending" value={String(pending)} />
        <MonitoringMetricCard label="Minimo prospettico" value={String(minimum)} />
        <MonitoringMetricCard label="Totale snapshot" value={String(snapshots)} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard label="% sul minimo" value={`${progressPct.toFixed(1)}%`} />
        <MonitoringMetricCard
          label="Eccedenza vs minimo"
          value={excess > 0 ? String(excess) : '0'}
        />
        <MonitoringMetricCard
          label="Residue al minimo"
          value={remaining > 0 ? String(remaining) : '0'}
        />
        <MonitoringMetricCard
          label="Campione minimo"
          value={minimumReached ? 'Superato' : 'Non raggiunto'}
        />
      </div>

      {minimumReached && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          Badge: Campione minimo superato
          {remaining === 0 ? ' · Non mancano partite per il minimo' : null}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleDownloadDossier}
          disabled={downloading}
          className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloading ? 'Download in corso…' : 'Scarica dossier readiness'}
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard
          label="Stato operativo"
          value={String(data.operational_status_label_it || data.operational_status || 'Supporto ufficiale')}
        />
        <MonitoringMetricCard
          label="Maturità scientifica"
          value={String(data.scientific_maturity_label_it || data.scientific_maturity || '—')}
        />
        <MonitoringMetricCard
          label="Prossimo passaggio"
          value={String(
            data.recommended_next_step_label_it ||
              data.recommended_next_step ||
              '—',
          )}
        />
        <MonitoringMetricCard
          label="Integrazione Signals"
          value={String(data.signals_integration_status_label_it || data.signals_integration_status || 'Non collegato ai Segnali')}
        />
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        Decisione automatica:{' '}
        {String(data.current_decision_label_it || data.current_decision || 'Modulo di supporto attivo')}
      </div>

      {benchmark &&
        Object.keys(benchmark).length > 0 &&
        String(benchmark.status || '') !== 'not_applicable_official_support' && (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <h4 className="text-sm font-semibold text-slate-800">Sintesi benchmark Phase 2B</h4>
          <p className="mt-1 text-xs text-slate-600">
            Status: {String(benchmark.status || '—')} · Paired:{' '}
            {String(benchmark.paired_complete_n ?? '—')} · Coverage:{' '}
            {benchmark.paired_coverage_pct != null
              ? `${String(benchmark.paired_coverage_pct)}%`
              : '—'}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Next step: {String(benchmark.recommended_next_step || data.recommended_next_step || '—')}
          </p>
        </div>
      )}

      {gates.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <h4 className="text-sm font-semibold text-slate-800">Gate di readiness</h4>
          <ul className="mt-3 space-y-2">
            {gates.map((gate, idx) => (
              <li
                key={gate.key || idx}
                className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {gate.label_it || gate.label || gate.key || 'Gate'}
                  </p>
                  {gate.value != null && (
                    <p className="text-xs text-slate-600">
                      Valore: {String(gate.value)}
                      {gate.threshold != null && ` / Soglia: ${String(gate.threshold)}`}
                    </p>
                  )}
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    gate.status === 'pass'
                      ? 'bg-emerald-100 text-emerald-800'
                      : gate.status === 'fail'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {gate.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function GoalIntensityBenchmarkView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Benchmark | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [qualityOpen, setQualityOpen] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5Benchmark(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento benchmark V4–V5')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data || data.status !== 'ok') {
    return <EmptyState message="Benchmark non disponibile" />
  }

  const cohort = (data.cohort || {}) as Record<string, unknown>
  const cont = data.continuous_total_goals?.metrics_by_model || {}
  const ge2 = data.goals_ge_2?.metrics_by_model || {}
  const ge3 = data.goals_ge_3?.metrics_by_model || {}
  const comparisons = (data.continuous_total_goals?.comparisons || []).filter(
    (c) => c.metric === 'mae',
  )
  const missing = (cohort.missing_by_reason || {}) as Record<string, number>
  const quality = (data.quality_checks || {}) as Record<string, unknown>
  const interp = (data.scientific_interpretation || {}) as Record<string, unknown>
  const btts = (data.btts || {}) as Record<string, unknown>

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Benchmark V4 vs V5</h3>
        <p className="mt-1 text-xs text-slate-600">
          Confronto paired prospettico sulla stessa coorte completed. Non è un consiglio di scommessa.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <MonitoringMetricCard label="V5 completed" value={String(cohort.completed_v5_total ?? '—')} />
        <MonitoringMetricCard label="V4 disponibili" value={String(cohort.v4_available ?? '—')} />
        <MonitoringMetricCard label="Paired completi" value={String(cohort.paired_complete_n ?? '—')} />
        <MonitoringMetricCard
          label="Coverage paired"
          value={cohort.paired_coverage_pct != null ? `${String(cohort.paired_coverage_pct)}%` : '—'}
        />
        <MonitoringMetricCard label="Esclusi" value={String(cohort.excluded_n ?? '—')} />
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Modello</th>
              <th className="px-3 py-2 font-medium">n paired</th>
              <th className="px-3 py-2 font-medium">MAE</th>
              <th className="px-3 py-2 font-medium">RMSE</th>
              <th className="px-3 py-2 font-medium">Bias</th>
              <th className="px-3 py-2 font-medium">Pearson</th>
              <th className="px-3 py-2 font-medium">Spearman</th>
              <th className="px-3 py-2 font-medium">Brier Over 1.5</th>
              <th className="px-3 py-2 font-medium">Brier Over 2.5</th>
            </tr>
          </thead>
          <tbody>
            {BENCHMARK_MODEL_ORDER.map((mid) => {
              const m = cont[mid] || {}
              const g2 = ge2[mid] || {}
              const g3 = ge3[mid] || {}
              return (
                <tr key={mid} className="border-b border-slate-100">
                  <td className="px-3 py-2 font-medium text-slate-800">
                    {BENCHMARK_MODEL_LABELS[mid] || mid}
                  </td>
                  <td className="px-3 py-2">{String(m.n ?? '—')}</td>
                  <td className="px-3 py-2">{m.mae != null ? String(m.mae) : '—'}</td>
                  <td className="px-3 py-2">{m.rmse != null ? String(m.rmse) : '—'}</td>
                  <td className="px-3 py-2">{m.mean_error != null ? String(m.mean_error) : '—'}</td>
                  <td className="px-3 py-2">{m.pearson != null ? String(m.pearson) : '—'}</td>
                  <td className="px-3 py-2">{m.spearman != null ? String(m.spearman) : '—'}</td>
                  <td className="px-3 py-2">{g2.brier != null ? String(g2.brier) : '—'}</td>
                  <td className="px-3 py-2">{g3.brier != null ? String(g3.brier) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h4 className="text-sm font-semibold text-slate-800">Evidenza pairwise (MAE)</h4>
        <ul className="mt-3 space-y-2">
          {comparisons.map((c, idx) => {
            const ci = (c.ci || {}) as Record<string, unknown>
            return (
              <li key={idx} className="rounded-lg border border-slate-100 px-3 py-2 text-xs text-slate-700">
                <span className="font-medium">
                  {BENCHMARK_MODEL_LABELS[String(c.left_id)] || String(c.left_id)} vs{' '}
                  {BENCHMARK_MODEL_LABELS[String(c.right_id)] || String(c.right_id)}
                </span>
                {' · '}delta={c.delta != null ? String(c.delta) : '—'}
                {' · '}CI=[{String(ci.ci_lower ?? '—')}, {String(ci.ci_upper ?? '—')}]
                {' · '}
                {evidenceLabelIt(
                  c.evidence_level as string | undefined,
                  c.preferred_side as string | undefined,
                )}
                {' · '}evidenza={String(c.evidence_level || '—')}
              </li>
            )
          })}
        </ul>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        Interpretazione: {String(interp.summary_it || interp.status || '—')}
        <br />
        BTTS V4: {String(btts.v4_status || 'not_comparable')} (
        {String(btts.v4_reason || 'v4_total_lambda_has_no_team_split_btts_probability')})
      </div>

      <div className="rounded-xl border border-slate-200 bg-white">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800"
          onClick={() => setQualityOpen((v) => !v)}
        >
          Qualità benchmark
          <span className="text-xs font-normal text-slate-500">{qualityOpen ? 'Nascondi' : 'Mostra'}</span>
        </button>
        {qualityOpen && (
          <div className="space-y-2 border-t border-slate-100 px-4 py-3 text-xs text-slate-700">
            <p>Bundle: {String(data.v5_bundle_version || '—')}</p>
            <p>Definition hash: {String(data.definition_hash || '—')}</p>
            <p>V4 version: {String(data.v4_version || '—')}</p>
            <p>Benchmark version: {String(data.version || '—')}</p>
            <p>Snapshot completed: {String(cohort.completed_v5_total ?? '—')}</p>
            <p>Paired: {String(cohort.paired_complete_n ?? '—')}</p>
            <p>Esclusi: {String(cohort.excluded_n ?? '—')}</p>
            <p>Target leakage check: {String(quality.target_leakage_check || '—')}</p>
            <p>Snapshot pre-kickoff check: {String(quality.snapshot_pre_kickoff_check || '—')}</p>
            <p>External API calls: {String(quality.external_api_calls ?? 0)}</p>
            <p>Historical run used: {String(quality.historical_run_used ?? false)}</p>
            <div>
              <p className="font-medium">Missing by reason</p>
              <ul className="mt-1 list-disc pl-4">
                {Object.keys(missing).length === 0 && <li>Nessuna esclusione registrata</li>}
                {Object.entries(missing).map(([reason, count]) => (
                  <li key={reason}>
                    {reason}: {count}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function GoalIntensityDataHealthView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5DataHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5DataHealth(
          {
            date_from: dateFrom,
            date_to: dateTo,
            competition_id: competitionId,
            source_cohort: cohortFilter,
          },
          { signal: controller.signal },
        )
        setData(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento data health')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />
  if (!data) return <EmptyState message="Dati non disponibili" />

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Data Health</h3>
        <p className="mt-1 text-xs text-slate-600">
          Qualità dati, coverage e completezza snapshot prospettici.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MonitoringMetricCard
          label="Stato qualità dati"
          value={data.data_quality_status || '—'}
        />
        <MonitoringMetricCard
          label="Coverage"
          value={data.coverage == null ? '—' : fmtPct(data.coverage)}
        />
        <MonitoringMetricCard
          label="Completeness"
          value={data.completeness == null ? '—' : fmtPct(data.completeness)}
        />
      </div>
    </div>
  )
}

export function GoalIntensityExportView({ dateFrom, dateTo, competitionId, cohortFilter }: ViewProps) {
  const [exportStatus, setExportStatus] = useState<GoalIntensityV5ExportStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const filters: GoalIntensityV5Filters = {
    date_from: dateFrom,
    date_to: dateTo,
    competition_id: competitionId,
    source_cohort: cohortFilter,
  }

  useEffect(() => {
    const controller = new AbortController()
    const requestFilters: GoalIntensityV5Filters = {
      date_from: dateFrom,
      date_to: dateTo,
      competition_id: competitionId,
      source_cohort: cohortFilter,
    }
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5ExportStatus(requestFilters, {
          signal: controller.signal,
        })
        setExportStatus(res)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(String(err))
        toast.error('Errore caricamento stato export')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadGoalIntensityV5AnalysisPack(filters)
      toast.success('Download avviato')
    } catch (err) {
      toast.error(`Errore download: ${String(err)}`)
    } finally {
      setDownloading(false)
    }
  }

  if (loading) return <LoadingSkeleton />
  if (error) return <EmptyState message={`Errore: ${error}`} />

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Export Goal Intensity v5</h3>
        <p className="mt-1 text-xs text-slate-600">
          Scarica analysis pack con snapshot, calibrazione e report candidati.
        </p>
      </div>

      {exportStatus && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Stato export"
            value={exportStatus.completeness || exportStatus.export_completeness_status || '—'}
          />
          <MonitoringMetricCard
            label="Righe disponibili"
            value={exportStatus.rows == null ? '—' : String(exportStatus.rows)}
          />
          <MonitoringMetricCard
            label="File disponibili"
            value={
              exportStatus.files_available == null
                ? '—'
                : `${exportStatus.files_available.length} / ${exportStatus.files_expected?.length || '?'}`
            }
          />
          <MonitoringMetricCard
            label="Dimensione stimata"
            value={
              exportStatus.estimated_size_bytes == null
                ? '—'
                : formatSize(exportStatus.estimated_size_bytes)
            }
          />
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading || exportStatus?.completeness === 'blocked'}
          className="w-full rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {downloading ? 'Download in corso...' : 'Scarica Analysis Pack'}
        </button>

        {exportStatus?.blocking_reasons && exportStatus.blocking_reasons.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <p className="font-medium">Motivi blocco:</p>
            <ul className="mt-1 list-disc pl-4">
              {exportStatus.blocking_reasons.map((reason, idx) => (
                <li key={idx}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

export function GoalIntensityPhase2CView({ dateFrom, dateTo, competitionId }: ViewProps) {
  const [data, setData] = useState<GoalIntensityV5Phase2C | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'idle' | 'analyze' | 'freeze'>('idle')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [archivedOpen, setArchivedOpen] = useState(false)

  const load = async () => {
    setBusy('analyze')
    setLoading(true)
    setError(null)
    try {
      const res = await getGoalIntensityV5Phase2CCandidates({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId,
      })
      setData(res)
      toast.success('Analisi varianti Phase 2C completata')
    } catch (err) {
      setError(String(err))
      toast.error('Errore analisi varianti Phase 2C')
    } finally {
      setBusy('idle')
      setLoading(false)
    }
  }

  const runFreeze = async () => {
    if (phase2cFreezeDisabled(data)) return
    setBusy('freeze')
    try {
      const res = await freezeGoalIntensityV5Phase2CBundle({
        dry_run: false,
        confirm: PHASE_2C_FREEZE_CONFIRM,
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId,
      })
      setData(res)
      setConfirmOpen(false)
      toast.success('Bundle benchmark congelato (non operativo)')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Freeze fallito')
    } finally {
      setBusy('idle')
    }
  }

  const cohort = (data?.cohort || {}) as Record<string, unknown>
  const splits = (data?.splits || {}) as Record<string, Record<string, unknown>>
  const parent = (data?.parent_bundle || {}) as Record<string, unknown>
  const giF = (data?.gi_f_selection || {}) as Record<string, unknown>
  const weights = (giF.weights || {}) as Record<string, number>
  const holdout = (data?.holdout_metrics || {}) as Record<string, Record<string, unknown>>
  const archived = (data?.archived_candidates || {}) as Record<string, Record<string, unknown>>
  const checks = (data?.checks || {}) as Record<string, unknown>
  const freezeDisabled = phase2cFreezeDisabled(data) || busy !== 'idle'

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Varianti Phase 2C</h3>
        <p className="mt-1 text-xs text-slate-600">
          Sviluppo candidati per benchmark esterno. Bundle non operativo: nessuna attivazione live,
          Signals bloccati.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy !== 'idle'}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:bg-slate-300"
        >
          {busy === 'analyze' ? 'Analisi…' : 'Analizza varianti'}
        </button>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={freezeDisabled || !data}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="phase2c-freeze-button"
        >
          {data?.existing_candidate_bundle ? 'Bundle congelato' : 'Congela bundle benchmark'}
        </button>
      </div>

      {data?.existing_candidate_bundle ? (
        <div
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-950"
          data-testid="phase2c-frozen-banner"
        >
          <p className="font-medium">Bundle congelato</p>
          <p className="mt-1">
            ID:{' '}
            <span className="font-mono">
              {String(
                (data.existing_candidate_bundle as Record<string, unknown>).id ??
                  (data.existing_candidate_bundle as Record<string, unknown>).bundle_id ??
                  '—',
              )}
            </span>
          </p>
          <p className="mt-1">
            Definition hash:{' '}
            <span className="font-mono break-all">
              {String(
                (data.existing_candidate_bundle as Record<string, unknown>).definition_hash ??
                  (data.existing_candidate_bundle as Record<string, unknown>)
                    .candidate_definition_hash ??
                  '—',
              )}
            </span>
          </p>
          <p className="mt-1 text-emerald-800">
            Freeze ripetuti dalla UI disabilitati. Il backend resta idempotente.
          </p>
        </div>
      ) : null}

      {confirmOpen && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">
          <p className="font-medium">Conferma freeze</p>
          <p className="mt-1">
            Token richiesto: <code className="font-mono">{PHASE_2C_FREEZE_CONFIRM}</code>
          </p>
          <p className="mt-1">
            Il parent v1.1 resta attivo. Il nuovo bundle resta non operativo (`is_active=false`).
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void runFreeze()}
              disabled={busy !== 'idle'}
              className="rounded-lg bg-amber-700 px-3 py-1.5 text-white"
            >
              {busy === 'freeze' ? 'Congelamento…' : 'Conferma freeze'}
            </button>
            <button
              type="button"
              onClick={() => setConfirmOpen(false)}
              className="rounded-lg border border-amber-300 px-3 py-1.5"
            >
              Annulla
            </button>
          </div>
        </div>
      )}

      {loading && <LoadingSkeleton />}
      {error && <EmptyState message={`Errore: ${error}`} />}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MonitoringMetricCard label="Parent bundle" value={String(parent.version ?? '—')} />
            <MonitoringMetricCard
              label="Target bundle"
              value={String(data.target_bundle_version ?? '—')}
            />
            <MonitoringMetricCard
              label="Parent attivo"
              value={parent.remains_active ? 'sì' : 'no'}
            />
            <MonitoringMetricCard label="Live / Signals" value="no / blocked" />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-700">
            <p>
              Intended use: <strong>historical_external_benchmark_only</strong> — bundle non
              operativo.
            </p>
            <p className="mt-1">
              Stato freeze: {data.existing_candidate_bundle ? 'congelato' : 'non congelato'} ·
              freeze_allowed={String(data.freeze_allowed)} · holdout_access=
              {String(checks.holdout_access_count ?? '—')}
            </p>
            {(data.blocking_reasons || []).length > 0 && (
              <ul className="mt-2 list-disc pl-4 text-amber-800">
                {(data.blocking_reasons || []).map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <MonitoringMetricCard label="Paired total" value={String(cohort.paired_total ?? '—')} />
            <MonitoringMetricCard
              label="Duplicates removed"
              value={String(cohort.duplicates_removed ?? '—')}
            />
            <MonitoringMetricCard label="Train" value={String(splits.train?.n ?? '—')} />
            <MonitoringMetricCard label="Validation" value={String(splits.validation?.n ?? '—')} />
            <MonitoringMetricCard label="Holdout" value={String(splits.holdout?.n ?? '—')} />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs">
            <h4 className="text-sm font-semibold text-slate-800">Quattro candidati V5</h4>
            <ul className="mt-2 space-y-1 text-slate-700">
              {PHASE_2C_ACTIVE_CANDIDATES.map((id) => (
                <li key={id}>
                  <span className="font-medium">{BENCHMARK_MODEL_LABELS[id] || id}</span> —{' '}
                  {id}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <button
              type="button"
              className="text-sm font-semibold text-slate-800"
              onClick={() => setArchivedOpen((v) => !v)}
            >
              Candidati archiviati {archivedOpen ? '▾' : '▸'}
            </button>
            {archivedOpen && (
              <ul className="mt-2 space-y-2 text-xs text-slate-700">
                {PHASE_2C_ARCHIVED_CANDIDATES.map((id) => {
                  const row = archived[id] || {}
                  return (
                    <li key={id} className="rounded border border-slate-100 px-3 py-2">
                      <p className="font-medium">{BENCHMARK_MODEL_LABELS[id] || id}</p>
                      <p>status: {String(row.status ?? '—')}</p>
                      <p>motivo: {String(row.reason ?? '—')}</p>
                      <p>
                        evidenza: {String(row.evidence_level ?? '—')} · delta=
                        {String(row.delta ?? '—')}
                      </p>
                      <p>non selezionati per il benchmark attivo</p>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs">
            <h4 className="text-sm font-semibold text-slate-800">GI_F — pesi regolarizzati</h4>
            <p className="mt-1 text-slate-600">
              selected alpha: {String(giF.selected_alpha ?? '—')}
            </p>
            <table className="mt-2 min-w-full text-left">
              <thead>
                <tr className="text-slate-500">
                  <th className="py-1 pr-3">Pillar</th>
                  <th className="py-1">Peso</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(weights).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-100">
                    <td className="py-1 pr-3">{k}</td>
                    <td className="py-1">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Modello</th>
                  <th className="px-3 py-2">MAE</th>
                  <th className="px-3 py-2">RMSE</th>
                  <th className="px-3 py-2">Bias</th>
                  <th className="px-3 py-2">Pearson</th>
                  <th className="px-3 py-2">Spearman</th>
                  <th className="px-3 py-2">Brier Over 1.5</th>
                  <th className="px-3 py-2">Brier Over 2.5</th>
                  <th className="px-3 py-2">Brier BTTS</th>
                </tr>
              </thead>
              <tbody>
                {PHASE_2C_HOLDOUT_MODELS.map((mid) => {
                  const m = holdout[mid] || {}
                  const cont = (m.continuous || {}) as Record<string, unknown>
                  const g2 = (m.goals_ge_2 || {}) as Record<string, unknown>
                  const g3 = (m.goals_ge_3 || {}) as Record<string, unknown>
                  const bt = (m.btts || {}) as Record<string, unknown>
                  return (
                    <tr key={mid} className="border-b border-slate-100">
                      <td className="px-3 py-2 font-medium">
                        {BENCHMARK_MODEL_LABELS[mid] || mid}
                      </td>
                      <td className="px-3 py-2">{cont.mae != null ? String(cont.mae) : '—'}</td>
                      <td className="px-3 py-2">{cont.rmse != null ? String(cont.rmse) : '—'}</td>
                      <td className="px-3 py-2">{cont.bias != null ? String(cont.bias) : '—'}</td>
                      <td className="px-3 py-2">
                        {cont.pearson != null ? String(cont.pearson) : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {cont.spearman != null ? String(cont.spearman) : '—'}
                      </td>
                      <td className="px-3 py-2">{g2.brier != null ? String(g2.brier) : '—'}</td>
                      <td className="px-3 py-2">{g3.brier != null ? String(g3.brier) : '—'}</td>
                      <td className="px-3 py-2">
                        {bt.status === 'not_comparable'
                          ? 'n/d'
                          : bt.brier != null
                            ? String(bt.brier)
                            : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <h4 className="text-sm font-semibold text-slate-800">Evidenza pairwise holdout</h4>
            <ul className="mt-2 space-y-2 text-xs text-slate-700">
              {(data.holdout_pairwise || [])
                .filter((c) => c.metric === 'mae')
                .map((c, idx) => {
                  const ci = (c.ci || {}) as Record<string, unknown>
                  return (
                    <li key={idx} className="rounded border border-slate-100 px-3 py-2">
                      {BENCHMARK_MODEL_LABELS[String(c.left_id)] || String(c.left_id)} vs{' '}
                      {BENCHMARK_MODEL_LABELS[String(c.right_id)] || String(c.right_id)} · delta=
                      {String(c.delta ?? '—')} · CI [{String(ci.ci_lower ?? '—')},{' '}
                      {String(ci.ci_upper ?? '—')}] ·{' '}
                      {evidenceLabelIt(
                        c.evidence_level as string,
                        c.preferred_side as string,
                      )}
                    </li>
                  )
                })}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
