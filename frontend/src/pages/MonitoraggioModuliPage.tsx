import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  getModuleMonitoringOverview,
  COHORT_FILTER_OPTIONS,
  type CohortFilterValue,
  type ModuleOverviewItem,
} from '../lib/cecchinoModuleMonitoringApi'
import { ModuleMonitoringHero } from '../components/module-monitoring/ModuleMonitoringHero'
import { ModuleOverviewGrid } from '../components/module-monitoring/ModuleOverviewGrid'
import { ModuleSelector } from '../components/module-monitoring/ModuleSelector'
import { ModuleWorkspaceShell } from '../components/module-monitoring/ModuleWorkspaceShell'
import { MonitoringFilterBar } from '../components/module-monitoring/MonitoringFilterBar'
import { MonitoringHistoricalImportPanel } from '../components/module-monitoring/MonitoringHistoricalImportPanel'
import { MonitoringPackQualityCard } from '../components/module-monitoring/MonitoringPackQualityCard'
import { PurchasabilityModulePanel } from '../components/module-monitoring/PurchasabilityModulePanel'
import { BalanceModulePanel } from '../components/module-monitoring/BalanceModulePanel'
import { GoalIntensityModulePanel } from '../components/module-monitoring/GoalIntensityModulePanel'
import { SignalsModulePanel } from '../components/module-monitoring/SignalsModulePanel'
import {
  getMonitoringModule,
  isMonitoringModuleKey,
  MONITORING_MODULES,
  type MonitoringModuleKey,
} from '../components/module-monitoring/moduleMonitoringRegistry'
import { MOTION_MED } from '../components/module-monitoring/moduleMonitoringUi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 90)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

export function MonitoraggioModuliPage() {
  const defaults = defaultRange()
  const [searchParams, setSearchParams] = useSearchParams()
  const moduleParam = searchParams.get('module')
  const viewParam = searchParams.get('view')
  const activeModule: MonitoringModuleKey = isMonitoringModuleKey(moduleParam)
    ? moduleParam
    : 'purchasability'
  const moduleDef = getMonitoringModule(activeModule)
  const activeView =
    moduleDef.views.some((v) => v.id === viewParam) && viewParam
      ? viewParam
      : moduleDef.defaultView

  const [dateFrom, setDateFrom] = useState(
    searchParams.get('date_from') || defaults.date_from,
  )
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || defaults.date_to)
  const [competitionId, setCompetitionId] = useState(
    searchParams.get('competition_id') || '',
  )
  const [loading, setLoading] = useState(false)
  const [overviewItems, setOverviewItems] = useState<ModuleOverviewItem[]>([])
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [cohortFilter, setCohortFilter] = useState<CohortFilterValue>(
    (searchParams.get('cohort') as CohortFilterValue) || 'all',
  )

  const syncUrl = useCallback(
    (next: { module?: MonitoringModuleKey; view?: string }) => {
      const p = new URLSearchParams(searchParams)
      p.set('module', next.module || activeModule)
      p.set('view', next.view || activeView)
      if (dateFrom) p.set('date_from', dateFrom)
      if (dateTo) p.set('date_to', dateTo)
      if (competitionId) p.set('competition_id', competitionId)
      else p.delete('competition_id')
      setSearchParams(p, { replace: false })
    },
    [searchParams, setSearchParams, activeModule, activeView, dateFrom, dateTo, competitionId],
  )

  const loadOverview = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getModuleMonitoringOverview({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ? Number(competitionId) : undefined,
      })
      setOverviewItems(payload.modules || [])
      setGeneratedAt(payload.generated_at || null)
      toast.success('Aggiornamento completato')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Errore overview')
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, competitionId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch overview on mount
    void loadOverview()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!moduleParam || !isMonitoringModuleKey(moduleParam)) {
      syncUrl({ module: 'purchasability', view: 'overview' })
    } else if (!viewParam || !moduleDef.views.some((v) => v.id === viewParam)) {
      syncUrl({ module: activeModule, view: moduleDef.defaultView })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const previewCount = useMemo(
    () =>
      MONITORING_MODULES.filter((m) =>
        m.operationalStatus.toLowerCase().includes('preview'),
      ).length,
    [],
  )

  const currentOverview = overviewItems.find((m) => m.module_key === activeModule)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={MOTION_MED}
      className="space-y-5 pb-8"
    >
      <ModuleMonitoringHero
        modulesCount={MONITORING_MODULES.length}
        previewCount={previewCount}
        lastUpdated={generatedAt}
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId}
        onRefresh={() => void loadOverview()}
        loading={loading}
        moduleStatuses={Object.fromEntries(
          overviewItems.map((m) => [m.module_key, m.status]),
        )}
      />

      <MonitoringFilterBar
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        onCompetitionId={setCompetitionId}
        onRefresh={() => void loadOverview()}
        loading={loading}
      />

      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200/70 bg-white p-3 shadow-sm">
        <label className="text-xs font-medium text-slate-600">
          Coorte
          <select
            value={cohortFilter}
            onChange={(e) => {
              const v = e.target.value as CohortFilterValue
              setCohortFilter(v)
              const p = new URLSearchParams(searchParams)
              if (v === 'all') p.delete('cohort')
              else p.set('cohort', v)
              setSearchParams(p, { replace: true })
            }}
            className="mt-1 block rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800"
          >
            {COHORT_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <p className="max-w-xl text-xs text-slate-500">
          Default analisi: tutte (segmentate). Per readiness/promozione preferire «Prospettica».
          Filtro informativo in overview — le metriche di promozione restano prospettiche.
        </p>
      </div>

      <MonitoringPackQualityCard
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId}
      />

      <MonitoringHistoricalImportPanel
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId}
      />

      <ModuleOverviewGrid
        items={
          overviewItems.length
            ? overviewItems
            : MONITORING_MODULES.map((m) => ({
                module_key: m.key,
                status: m.operationalStatus,
                version: m.versionLabel,
                coverage: null,
                fixtures: null,
                settled: null,
                warnings: ['Raccolta dati non ancora disponibile'],
              }))
        }
        onOpen={(key) => syncUrl({ module: key, view: getMonitoringModule(key).defaultView })}
      />

      <ModuleSelector
        active={activeModule}
        onSelect={(key) => syncUrl({ module: key, view: getMonitoringModule(key).defaultView })}
      />

      <ModuleWorkspaceShell
        module={moduleDef}
        view={activeView}
        onViewChange={(view) => syncUrl({ view })}
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId ? Number(competitionId) : null}
        apiStatus={currentOverview?.status}
      >
        {activeModule === 'purchasability' ? (
          <PurchasabilityModulePanel
            view={activeView}
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId ? Number(competitionId) : null}
            overview={currentOverview}
            cohortFilter={cohortFilter}
          />
        ) : activeModule === 'balance-v5' ? (
          <BalanceModulePanel
            view={activeView}
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId ? Number(competitionId) : null}
            overview={currentOverview}
            cohortFilter={cohortFilter}
          />
        ) : activeModule === 'goal-intensity-v5' ? (
          <GoalIntensityModulePanel
            view={activeView}
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId ? Number(competitionId) : null}
            overview={currentOverview}
            cohortFilter={cohortFilter}
          />
        ) : (
          <SignalsModulePanel
            view={activeView}
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId ? Number(competitionId) : null}
            overview={currentOverview}
            cohortFilter={cohortFilter}
          />
        )}
      </ModuleWorkspaceShell>
    </motion.div>
  )
}
