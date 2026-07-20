import { HERO_BASE } from './moduleMonitoringUi'
import { MonitoringGlobalExportMenu } from './MonitoringGlobalExportMenu'

type Props = {
  modulesCount: number
  previewCount: number
  lastUpdated: string | null
  dateFrom: string
  dateTo: string
  competitionId: string
  onRefresh: () => void
  loading?: boolean
  moduleStatuses?: Record<string, string | null | undefined>
  sourceCohort?: string
}

export function ModuleMonitoringHero({
  modulesCount,
  previewCount,
  lastUpdated,
  dateFrom,
  dateTo,
  competitionId,
  onRefresh,
  loading,
  moduleStatuses,
  sourceCohort = 'all',
}: Props) {
  const competitionLabel = competitionId ? competitionId : 'tutte'
  return (
    <section className={`${HERO_BASE} relative overflow-hidden px-5 py-6 sm:px-7`}>
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-cyan-200/30 blur-3xl"
        aria-hidden
      />
      <div className="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-cyan-700/80">
            Cecchino · Workspace analitico
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            Monitoraggio Moduli Cecchino
          </h1>
          <p className="mt-2 text-sm text-slate-600 sm:text-base">
            Controlla qualità dei dati, stabilità, risultati e stato di validazione dei moduli
            analitici Cecchino.
          </p>
          <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-700">
            <div>
              <dt className="inline text-slate-500">Moduli </dt>
              <dd className="inline font-semibold tabular-nums">{modulesCount}</dd>
            </div>
            <div>
              <dt className="inline text-slate-500">Preview </dt>
              <dd className="inline font-semibold tabular-nums">{previewCount}</dd>
            </div>
            <div>
              <dt className="inline text-slate-500">Range </dt>
              <dd className="inline font-medium">
                {dateFrom} → {dateTo}
              </dd>
            </div>
            <div>
              <dt className="inline text-slate-500">Competition </dt>
              <dd className="inline font-medium">{competitionLabel}</dd>
            </div>
            <div>
              <dt className="inline text-slate-500">Aggiornato </dt>
              <dd className="inline font-medium">{lastUpdated || '—'}</dd>
            </div>
          </dl>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={onRefresh}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            Aggiorna
          </button>
          <MonitoringGlobalExportMenu
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId ? Number(competitionId) : null}
            moduleStatuses={moduleStatuses}
            sourceCohort={sourceCohort}
          />
        </div>
      </div>
    </section>
  )
}
