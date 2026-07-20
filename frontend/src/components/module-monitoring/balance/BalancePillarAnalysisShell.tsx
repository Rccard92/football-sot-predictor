import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import LabEChartsCore from '../../cecchino-lab/LabEChartsCore'
import {
  getBalanceEmpiricalAnalysis,
  type BalanceAnalysisPayload,
} from '../../../lib/cecchinoModuleMonitoringApi'
import {
  BalanceAnalysisFilters,
} from './BalanceAnalysisFilters'
import {
  EMPTY_BALANCE_FILTERS,
  type BalanceAnalysisFiltersState,
} from './balanceAnalysisFilterTypes'
import { BalanceEvidenceBadge } from './BalanceEvidenceBadge'
import { BalanceMetricCard } from './BalanceMetricCard'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

type Props = {
  pillar:
    | 'overview'
    | 'f36'
    | 'dominance'
    | 'draw-credibility'
    | 'gap'
    | 'stability'
    | 'data-health'
    | 'dependency'
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
  title: string
  roleLabel?: string
  extra?: ReactNode
}

export function BalancePillarAnalysisShell({
  pillar,
  dateFrom,
  dateTo,
  competitionId,
  cohortFilter = 'all',
  title,
  roleLabel,
  extra,
}: Props) {
  const [filters, setFilters] = useState<BalanceAnalysisFiltersState>(EMPTY_BALANCE_FILTERS)
  const [data, setData] = useState<BalanceAnalysisPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  function updateFilters(next: BalanceAnalysisFiltersState) {
    setLoading(true)
    setFilters(next)
  }

  useEffect(() => {
    const ac = new AbortController()
    void getBalanceEmpiricalAnalysis(pillar, {
      date_from: dateFrom,
      date_to: dateTo,
      competition_id: competitionId ?? undefined,
      source_cohort: cohortFilter,
      country_name: filters.countryName || undefined,
      f36_class: filters.f36Class || undefined,
      dominance_class: filters.dominanceClass || undefined,
      dominance_selection: filters.dominanceSelection || undefined,
      draw_credibility_class: filters.drawCredibilityClass || undefined,
      gap_class: filters.gapClass || undefined,
    }, ac.signal)
      .then((payload) => {
        if (!ac.signal.aborted) {
          setData(payload)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ac.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Errore caricamento')
          setLoading(false)
        }
      })
    return () => ac.abort()
  }, [pillar, dateFrom, dateTo, competitionId, cohortFilter, filters])

  const evidence = (data?.evidence as Record<string, unknown> | undefined) || undefined
  const sample = (data?.sample as Record<string, unknown> | undefined) || undefined
  const byClass = (data?.by_class as Array<Record<string, unknown>>) || []

  const chartOption =
    byClass.length > 0
      ? {
          tooltip: { trigger: 'axis' as const },
          legend: { data: ['HOME %', 'DRAW %', 'AWAY %'] },
          grid: { left: 40, right: 16, top: 40, bottom: 48 },
          xAxis: {
            type: 'category' as const,
            data: byClass.map((r) => String(r.label_it || r.class)),
            axisLabel: { rotate: 20, fontSize: 10 },
          },
          yAxis: { type: 'value' as const, max: 100 },
          series: [
            {
              name: 'HOME %',
              type: 'bar' as const,
              stack: 'out',
              data: byClass.map((r) => (r.home_rate as { rate_pct?: number })?.rate_pct ?? 0),
              itemStyle: { color: '#6366f1' },
            },
            {
              name: 'DRAW %',
              type: 'bar' as const,
              stack: 'out',
              data: byClass.map((r) => (r.draw_rate as { rate_pct?: number })?.rate_pct ?? 0),
              itemStyle: { color: '#94a3b8' },
            },
            {
              name: 'AWAY %',
              type: 'bar' as const,
              stack: 'out',
              data: byClass.map((r) => (r.away_rate as { rate_pct?: number })?.rate_pct ?? 0),
              itemStyle: { color: '#7c3aed' },
            },
          ],
        }
      : null

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-violet-100 bg-gradient-to-r from-violet-50/80 to-indigo-50/50 p-4">
        <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        {roleLabel ? <p className="mt-1 text-sm text-slate-600">{roleLabel}</p> : null}
        <div className="mt-3">
          <BalanceEvidenceBadge
            status={String(evidence?.status || data?.status || '')}
            scope={String(evidence?.evidence_scope || data?.evidence_scope || '')}
          />
        </div>
      </div>

      <BalanceAnalysisFilters value={filters} onChange={updateFilters} />

      {loading ? (
        <div className="animate-pulse space-y-3">
          <div className="h-20 rounded-2xl bg-slate-100" />
          <div className="h-64 rounded-2xl bg-slate-100" />
        </div>
      ) : error ? (
        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : !data ? (
        <p className="text-sm text-slate-500">Nessun dato.</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <BalanceMetricCard
              label="Fixture settled"
              value={String(sample?.settled ?? '—')}
            />
            <BalanceMetricCard
              label="Righe totali"
              value={String(sample?.rows_total ?? '—')}
            />
            <BalanceMetricCard
              label="Pending"
              value={String(sample?.pending ?? '—')}
              hint="Esclusi dalle metriche prestazionali"
            />
            <BalanceMetricCard
              label="Prospettiche"
              value={String(sample?.prospective_persisted ?? '—')}
            />
          </div>

          {chartOption ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Esiti per classe (stacked %)
              </p>
              <LabEChartsCore
                echarts={echarts}
                option={chartOption}
                style={{ height: 280 }}
                notMerge
                lazyUpdate
              />
            </div>
          ) : null}

          {typeof data.reading === 'string' ? (
            <p className="rounded-2xl border border-indigo-100 bg-indigo-50/50 px-3 py-2 text-sm text-indigo-950">
              {data.reading}
            </p>
          ) : null}

          {typeof data.banner === 'string' ? (
            <p className="rounded-2xl border border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-amber-950">
              {data.banner}
            </p>
          ) : null}

          {extra}
        </>
      )}
    </div>
  )
}
