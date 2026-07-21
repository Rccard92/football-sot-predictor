/**
 * Goal Intensity v5 — Viste workspace Module Monitoring
 */

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import type {
  GoalIntensityV5Calibration,
  GoalIntensityV5Candidates,
  GoalIntensityV5DataHealth,
  GoalIntensityV5Dimensions,
  GoalIntensityV5ExportStatus,
  GoalIntensityV5Filters,
  GoalIntensityV5Overview,
  GoalIntensityV5ProspectiveResults,
  GoalIntensityV5Readiness,
  GoalIntensityV5Stability,
} from '../../../lib/cecchinoGoalIntensityV5Api'
import {
  downloadGoalIntensityV5AnalysisPack,
  downloadGoalIntensityV5ReadinessDossier,
  getGoalIntensityV5Calibration,
  getGoalIntensityV5Candidates,
  getGoalIntensityV5DataHealth,
  getGoalIntensityV5Dimensions,
  getGoalIntensityV5ExportStatus,
  getGoalIntensityV5Overview,
  getGoalIntensityV5ProspectiveResults,
  getGoalIntensityV5Readiness,
  getGoalIntensityV5Stability,
} from '../../../lib/cecchinoGoalIntensityV5Api'
import { MonitoringMetricCard } from '../MonitoringMetricCard'
import { fmtPct } from '../moduleMonitoringUi'

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

  const covGlobal = (data.coverage_global || data.coverage) as Record<string, unknown> | undefined
  const covPeriod = (data.coverage_in_period || data.coverage) as Record<string, unknown> | undefined
  const globalSnapshots =
    (covGlobal?.snapshots as number | undefined) ??
    (data.global_snapshots as number | undefined) ??
    (data.coverage as { snapshots_global?: number } | undefined)?.snapshots_global
  const periodSnapshots =
    (covPeriod?.snapshots as number | undefined) ??
    (data.snapshots_in_period as number | undefined) ??
    (data.prospective_snapshots as number | undefined)
  const completedSnapshots =
    (covGlobal?.completed as number | undefined) ??
    (data.completed_snapshots as number | undefined) ??
    (data.coverage as { completed?: number } | undefined)?.completed
  const pendingSnapshots =
    (covGlobal?.pending as number | undefined) ??
    (data.pending_snapshots as number | undefined) ??
    (data.coverage as { pending?: number } | undefined)?.pending
  const minimumSample =
    (data.minimum_sample as number | undefined) ??
    (data.coverage as { minimum_prospective_matches?: number } | undefined)?.minimum_prospective_matches ??
    200

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Goal Intensity v5 Overview</h3>
        <p className="mt-1 text-xs text-slate-600">
          Snapshot prospettici per analisi candidati su quattro dimensioni distinte.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard label="Versione" value={data.version || 'goal_intensity_v5'} />
        <MonitoringMetricCard
          label="Snapshot globali"
          value={globalSnapshots == null ? '—' : String(globalSnapshots)}
        />
        <MonitoringMetricCard
          label="Snapshot nel periodo"
          value={periodSnapshots == null ? '—' : String(periodSnapshots)}
        />
        <MonitoringMetricCard
          label="Completed"
          value={completedSnapshots == null ? '—' : String(completedSnapshots)}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitoringMetricCard
          label="Pending"
          value={pendingSnapshots == null ? '—' : String(pendingSnapshots)}
        />
        <MonitoringMetricCard
          label="Progressione raccolta"
          value={data.snapshot_collection_progress == null ? '—' : fmtPct(data.snapshot_collection_progress)}
        />
        <MonitoringMetricCard
          label="Risultati completati"
          value={data.completed_results_progress == null ? '—' : fmtPct(data.completed_results_progress)}
        />
        <MonitoringMetricCard
          label="Campione minimo"
          value={String(minimumSample)}
        />
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

      {(data.first_effective_date || data.last_effective_date) && (
        <p className="text-xs text-slate-500">
          Date effettive: {data.first_effective_date || '—'} → {data.last_effective_date || '—'}
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
  const progress = (data.prospective_progress || data.monitoring_normalized) as
    | Record<string, unknown>
    | undefined

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Readiness</h3>
        <p className="mt-1 text-xs text-slate-600">
          Stato operativo, maturità scientifica e gate di monitoraggio. Signals sempre bloccati.
        </p>
      </div>

      {progress && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Completed"
            value={String(progress.completed_n ?? progress.completed_snapshots ?? 0)}
          />
          <MonitoringMetricCard
            label="Pending"
            value={String(progress.pending_n ?? progress.pending_snapshots ?? 0)}
          />
          <MonitoringMetricCard
            label="Minimo prospettico"
            value={String(progress.minimum_prospective_matches ?? 200)}
          />
          <MonitoringMetricCard
            label="Totale snapshot"
            value={String(progress.total_snapshots ?? 0)}
          />
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
          value={String(data.operational_status_label_it || data.operational_status || 'Preview monitorata')}
        />
        <MonitoringMetricCard
          label="Maturità scientifica"
          value={String(data.scientific_maturity_label_it || data.scientific_maturity || '—')}
        />
        <MonitoringMetricCard
          label="Integrazione Signals"
          value={String(data.signals_integration_status_label_it || data.signals_integration_status || 'Bloccata')}
        />
        <MonitoringMetricCard
          label="Decisione"
          value={String(data.current_decision_label_it || data.current_decision || 'Continua monitoraggio')}
        />
      </div>

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
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getGoalIntensityV5ExportStatus(filters, { signal: controller.signal })
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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
