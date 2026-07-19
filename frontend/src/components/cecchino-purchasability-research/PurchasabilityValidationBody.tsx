import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import LabEChartsCore from '../cecchino-lab/LabEChartsCore'
import type {
  PurchasabilityValidationFilters,
  PurchasabilityValidationHealth,
  PurchasabilityValidationJobStatus,
  PurchasabilityValidationReadiness,
  PurchasabilityValidationSummary,
} from '../../lib/cecchinoPurchasabilityValidationApi'
import { buildPurchasabilityValidationExportUrl } from '../../lib/cecchinoPurchasabilityValidationApi'
import { MonitoringChartCard } from '../module-monitoring/MonitoringChartCard'
import { MonitoringEmptyState } from '../module-monitoring/MonitoringEmptyState'
import { MonitoringGateCard } from '../module-monitoring/MonitoringGateCard'
import { MonitoringMetricCard } from '../module-monitoring/MonitoringMetricCard'
import { MonitoringAccentBadge, MonitoringStatusBadge } from '../module-monitoring/MonitoringStatusBadge'
import {
  ACCENT_CLASSES,
  MOTION_FAST,
  coverageDisplay,
  fmtNum,
  fmtPct,
  readinessLabelIt,
} from '../module-monitoring/moduleMonitoringUi'

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
])

type Props = {
  health: PurchasabilityValidationHealth | null
  summary: PurchasabilityValidationSummary | null
  readiness: PurchasabilityValidationReadiness | null
  loading: boolean
  error: string | null
  job: PurchasabilityValidationJobStatus | null
  dateFrom: string
  dateTo: string
  marketKey: string
  bootstrapIterations: number
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onMarketKey: (v: string) => void
  onBootstrap: (v: number) => void
  onRefresh: () => void
  onStartJob: () => void
  filters: () => PurchasabilityValidationFilters
}

function gateState(
  pass: boolean | undefined,
  insufficient?: boolean,
): 'superato' | 'in_raccolta' | 'bloccante' | 'non_valutabile' {
  if (insufficient) return 'in_raccolta'
  if (pass === true) return 'superato'
  if (pass === false) return 'bloccante'
  return 'non_valutabile'
}

export function PurchasabilityValidationBody({
  health,
  summary,
  readiness,
  loading,
  error,
  job,
  dateFrom,
  dateTo,
  marketKey,
  bootstrapIterations,
  onDateFrom,
  onDateTo,
  onMarketKey,
  onBootstrap,
  onRefresh,
  onStartJob,
  filters,
}: Props) {
  const accent = ACCENT_CLASSES.purchasability
  const metrics = (summary?.metrics || {}) as Record<string, number | null>
  const span = (summary?.temporal_span || {}) as Record<string, unknown>
  const readinessStatus = readiness?.status || 'collecting_data'
  const jobRunning = job?.status === 'queued' || job?.status === 'running'
  const cov = coverageDisplay(
    health?.snapshot_persistence_coverage ?? null,
    (health?.fixtures_with_kpi_panel ?? 0) > 0,
  )
  const settled = metrics.settled ?? health?.result_settled_count ?? null
  const empty =
    !loading &&
    (settled == null || settled === 0) &&
    (health?.fixtures_with_verified_pre_match_preview ?? 0) === 0

  useEffect(() => {
    if (error) toast.error(error)
  }, [error])

  useEffect(() => {
    if (job?.status === 'completed') toast.success('Aggiornamento bootstrap completato')
    if (job?.status === 'failed') toast.error(job.error_message || 'Job fallito')
  }, [job?.status, job?.error_message])

  const bandOption = useMemo(() => {
    const rows = summary?.by_score_band || []
    if (!rows.length) return null
    return {
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: Array<{ dataIndex: number }>) => {
          const i = params[0]?.dataIndex ?? 0
          const r = rows[i] || {}
          return [
            String(r.score_band ?? ''),
            `Righe: ${r.rows ?? '—'}`,
            `Fixture: ${r.fixtures ?? '—'}`,
            `WR: ${fmtPct(r.win_rate as number | null)}`,
            `ROI: ${fmtNum(r.roi_pct as number | null)}%`,
          ].join('<br/>')
        },
      },
      grid: { left: 40, right: 16, top: 24, bottom: 36 },
      xAxis: {
        type: 'category' as const,
        data: rows.map((r) => String(r.score_band ?? '')),
      },
      yAxis: { type: 'value' as const, name: 'righe' },
      series: [
        {
          type: 'bar' as const,
          data: rows.map((r, idx) => ({
            value: Number(r.rows || 0),
            itemStyle: {
              color:
                String(r.score_band) === 'ZERO'
                  ? '#94a3b8'
                  : idx < 2
                    ? '#67e8f9'
                    : idx < 4
                      ? '#22d3ee'
                      : '#0891b2',
              borderRadius: [6, 6, 0, 0],
            },
          })),
        },
      ],
    }
  }, [summary?.by_score_band])

  const roiBandOption = useMemo(() => {
    const rows = summary?.by_score_band || []
    if (!rows.length || !rows.some((r) => r.rows)) return null
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { top: 0 },
      grid: { left: 48, right: 16, top: 36, bottom: 36 },
      xAxis: {
        type: 'category' as const,
        data: rows.map((r) => String(r.score_band ?? '')),
      },
      yAxis: { type: 'value' as const },
      series: [
        {
          name: 'ROI %',
          type: 'bar' as const,
          data: rows.map((r) => r.roi_pct ?? null),
          itemStyle: { color: accent.chartPrimary, borderRadius: [4, 4, 0, 0] },
        },
        {
          name: 'Margine',
          type: 'line' as const,
          data: rows.map((r) => r.realized_margin ?? null),
          itemStyle: { color: accent.chartSecondary },
          markLine: { data: [{ yAxis: 0, lineStyle: { color: '#94a3b8' } }] },
        },
      ],
    }
  }, [summary?.by_score_band, accent.chartPrimary, accent.chartSecondary])

  const phaseOption = useMemo(() => {
    const p1 = summary?.phase1_comparison as
      | {
          delta_point?: number | null
          candidate_spearman?: { point?: number | null }
          phase1_spearman?: { point?: number | null }
        }
      | undefined
    if (!p1) return null
    const cand = p1.candidate_spearman?.point
    const base = p1.phase1_spearman?.point
    if (cand == null && base == null && p1.delta_point == null) return null
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      xAxis: {
        type: 'category' as const,
        data: ['Candidate ρ', 'Phase 1 ρ', 'Δ'],
      },
      yAxis: { type: 'value' as const },
      series: [
        {
          type: 'bar' as const,
          data: [cand ?? 0, base ?? 0, p1.delta_point ?? 0],
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#22d3ee' },
              { offset: 1, color: '#6366f1' },
            ]),
            borderRadius: [6, 6, 0, 0],
          },
        },
      ],
    }
  }, [summary?.phase1_comparison])

  const foldOption = useMemo(() => {
    const folds = summary?.temporal_folds || []
    if (!folds.length) return null
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { top: 0 },
      grid: { left: 48, right: 16, top: 36, bottom: 36 },
      xAxis: {
        type: 'category' as const,
        data: folds.map((f) => String(f.test_month ?? f.fold ?? '')),
      },
      yAxis: { type: 'value' as const },
      series: [
        {
          name: 'Candidate',
          type: 'line' as const,
          data: folds.map((f) => f.candidate_spearman ?? null),
          itemStyle: { color: accent.chartPrimary },
        },
        {
          name: 'Phase 1',
          type: 'line' as const,
          data: folds.map((f) => f.phase1_spearman ?? null),
          itemStyle: { color: accent.chartSecondary },
        },
      ],
    }
  }, [summary?.temporal_folds, accent.chartPrimary, accent.chartSecondary])

  const familyOption = useMemo(() => {
    const rows = summary?.by_market_family || []
    if (!rows.length) return null
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 110, right: 24, top: 16, bottom: 24 },
      xAxis: { type: 'value' as const },
      yAxis: {
        type: 'category' as const,
        data: rows.map((r) => String(r.market_family ?? '')),
      },
      series: [
        {
          type: 'bar' as const,
          data: rows.map((r) => r.realized_margin ?? 0),
          itemStyle: { color: accent.chartPrimary, borderRadius: [0, 4, 4, 0] },
        },
      ],
    }
  }, [summary?.by_market_family, accent.chartPrimary])

  const dataGates = readiness?.data_gates || {}
  const perfGates = readiness?.performance_gates || {}

  return (
    <div className="space-y-5">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={MOTION_FAST}
        className={`rounded-2xl border border-slate-200/70 ${accent.softBg} p-4 shadow-sm`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">Acquistabilità</h2>
              <MonitoringAccentBadge label="Preview monitorata" accent="purchasability" />
              <MonitoringStatusBadge
                label={readinessLabelIt(readinessStatus)}
                tone={
                  readinessStatus === 'eligible_for_manual_promotion'
                    ? 'success'
                    : readinessStatus === 'data_quality_blocked'
                      ? 'blocked'
                      : 'collecting'
                }
              />
            </div>
            <p className="mt-1 text-sm text-slate-600">
              Candidate {String(summary?.candidate_version || readiness?.candidate_version || '—')} ·
              Policy {String(summary?.policy_version || readiness?.policy_version || '—')}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Prima revisione teorica:{' '}
              {String(
                readiness?.prima_data_teorica_promozione ||
                  span.prima_data_teorica_promozione ||
                  '—',
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700"
              href={buildPurchasabilityValidationExportUrl(filters())}
            >
              CSV righe
            </a>
            <button
              type="button"
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm"
              onClick={() => {
                toast.message('Aggiornamento…')
                onRefresh()
              }}
              disabled={loading}
            >
              Aggiorna
            </button>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
              onClick={() => {
                toast.message('Job avviato…')
                onStartJob()
              }}
              disabled={loading || jobRunning}
            >
              Job bootstrap
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-3">
          <label className="text-xs text-slate-600">
            Da
            <input
              type="date"
              className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={dateFrom}
              onChange={(e) => onDateFrom(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600">
            A
            <input
              type="date"
              className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={dateTo}
              onChange={(e) => onDateTo(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600">
            Market
            <input
              className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={marketKey}
              placeholder="opzionale"
              onChange={(e) => onMarketKey(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600">
            Bootstrap
            <input
              type="number"
              className="mt-1 block w-24 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={bootstrapIterations}
              min={10}
              max={2000}
              onChange={(e) => onBootstrap(Number(e.target.value) || 200)}
            />
          </label>
        </div>
        {jobRunning ? (
          <p className="mt-2 text-sm text-slate-500">
            Job {job?.status}: {job?.progress_message || job?.current_stage || '…'}
          </p>
        ) : null}
      </motion.header>

      {empty ? (
        <MonitoringEmptyState
          title="Monitoraggio attivo, coorte ancora vuota"
          reason="Il monitoraggio è attivo, ma non sono ancora presenti snapshot prospettici settled nel periodo selezionato."
          nextAction="Verifica migrazione evaluations, scan pre-match e update risultati. Nessun dato fittizio viene mostrato."
          onRefresh={onRefresh}
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MonitoringMetricCard label="Copertura snapshot" value={cov.text} hint="verified / panel" />
            <MonitoringMetricCard
              label="Fixture concluse"
              value={String(metrics.fixtures ?? '—')}
              hint="fixture distinte settled"
            />
            <MonitoringMetricCard
              label="Righe valutate"
              value={String(settled ?? '—')}
              hint="won + lost"
            />
            <MonitoringMetricCard
              label="Giorni osservati"
              value={String(span.span_days ?? '—')}
              hint="span temporale settled"
            />
            <MonitoringMetricCard label="ROI" value={`${fmtNum(metrics.roi_pct)}%`} hint="stake 1" />
            <MonitoringMetricCard
              label="Margine realizzato"
              value={fmtNum(metrics.realized_margin)}
              hint="WR − break-even"
            />
            <MonitoringMetricCard
              label="Score medio"
              value={fmtNum(metrics.average_score, 1)}
              hint="indice 0–100"
            />
            <MonitoringMetricCard
              label="Quota score zero"
              value={fmtPct(metrics.zero_score_share)}
              hint="Phase1 senza edge"
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <MonitoringChartCard title="Distribuzione score band" subtitle="ZERO separato">
              {bandOption ? (
                <LabEChartsCore echarts={echarts} option={bandOption} style={{ height: 260 }} notMerge lazyUpdate />
              ) : (
                <p className="text-sm text-slate-500">Dati band non disponibili</p>
              )}
            </MonitoringChartCard>
            <MonitoringChartCard title="ROI e margine per band">
              {roiBandOption ? (
                <LabEChartsCore echarts={echarts} option={roiBandOption} style={{ height: 260 }} notMerge lazyUpdate />
              ) : (
                <p className="text-sm text-slate-500">Grafico nascosto: dati assenti</p>
              )}
            </MonitoringChartCard>
            <MonitoringChartCard title="Candidate vs Phase 1" subtitle="metriche paired">
              {phaseOption ? (
                <LabEChartsCore echarts={echarts} option={phaseOption} style={{ height: 260 }} notMerge lazyUpdate />
              ) : (
                <p className="text-sm text-slate-500">Confronto non ancora calcolabile</p>
              )}
            </MonitoringChartCard>
            <MonitoringChartCard title="Fold temporali">
              {foldOption ? (
                <LabEChartsCore echarts={echarts} option={foldOption} style={{ height: 260 }} notMerge lazyUpdate />
              ) : (
                <p className="text-sm text-slate-500">Nessun fold nel periodo</p>
              )}
            </MonitoringChartCard>
            <MonitoringChartCard title="Market family" subtitle="margine realizzato" className="lg:col-span-2">
              {familyOption ? (
                <LabEChartsCore echarts={echarts} option={familyOption} style={{ height: 260 }} notMerge lazyUpdate />
              ) : (
                <p className="text-sm text-slate-500">Famiglie non disponibili</p>
              )}
            </MonitoringChartCard>
          </div>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">Gate — integrità e campione</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <MonitoringGateCard
                title="Copertura persistenza snapshot"
                valueLabel={cov.text}
                thresholdLabel="95%"
                progress={health?.snapshot_persistence_coverage ?? null}
                state={gateState(dataGates.persistence_coverage?.pass as boolean | undefined)}
                explanation="Snapshot verified pre-match sulle fixture con KPI panel."
              />
              <MonitoringGateCard
                title="Duplicati current"
                valueLabel={String(health?.duplicate_validation_rows ?? '—')}
                thresholdLabel="0"
                progress={
                  health?.duplicate_validation_rows === 0
                    ? 1
                    : health?.duplicate_validation_rows == null
                      ? null
                      : 0
                }
                state={gateState(dataGates.no_duplicate_current?.pass as boolean | undefined)}
              />
              <MonitoringGateCard
                title="Giorni temporali"
                valueLabel={String(span.span_days ?? '—')}
                thresholdLabel="90"
                progress={
                  typeof span.span_days === 'number' ? Math.min(1, span.span_days / 90) : null
                }
                state={gateState(dataGates.min_temporal_days?.pass as boolean | undefined)}
              />
              <MonitoringGateCard
                title="Fixture settled"
                valueLabel={String(metrics.fixtures ?? '—')}
                thresholdLabel="300"
                progress={
                  typeof metrics.fixtures === 'number'
                    ? Math.min(1, metrics.fixtures / 300)
                    : null
                }
                state={gateState(dataGates.min_distinct_fixtures?.pass as boolean | undefined)}
              />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">Gate — prestazioni</h3>
            <div className="grid gap-3 md:grid-cols-3">
              {(
                [
                  ['test_a_residual_order', 'Ordine residuale (Spearman)'],
                  ['test_b_top_bottom', 'Separazione top/bottom'],
                  ['test_c_phase2_incremental', 'Valore incrementale Phase 2'],
                ] as const
              ).map(([key, label]) => {
                const g = (perfGates[key] || {}) as Record<string, unknown>
                return (
                  <MonitoringGateCard
                    key={key}
                    title={label}
                    valueLabel={
                      g.estimate != null
                        ? fmtNum(g.estimate as number)
                        : g.residual_spread != null
                          ? fmtNum(g.residual_spread as number)
                          : g.delta != null
                            ? fmtNum(g.delta as number)
                            : '—'
                    }
                    thresholdLabel="CI low > 0"
                    progress={g.pass === true ? 1 : g.insufficient ? null : 0.2}
                    state={gateState(g.pass as boolean | undefined, g.insufficient as boolean | undefined)}
                    explanation="Non valutabile in rosso finché i dati non bastano."
                  />
                )
              })}
            </div>
            {readiness?.recommended_next_step ? (
              <p className="text-sm text-slate-600">{readiness.recommended_next_step}</p>
            ) : null}
          </section>
        </>
      )}
    </div>
  )
}
