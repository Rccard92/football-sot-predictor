import { AnimatePresence, motion } from 'framer-motion'
import type { MonitoringModuleDef } from './moduleMonitoringRegistry'
import { MonitoringAccentBadge } from './MonitoringStatusBadge'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import { ModuleViewTabs } from './ModuleViewTabs'
import {
  ACCENT_CLASSES,
  CARD_BASE,
  MOTION_MED,
  monitoringStatusLabel,
} from './moduleMonitoringUi'
import type { MonitoringModuleKeyApi } from '../../lib/cecchinoModuleMonitoringApi'

type Props = {
  module: MonitoringModuleDef
  view: string
  onViewChange: (viewId: string) => void
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  apiStatus?: string | null
  children: React.ReactNode
}

export function ModuleWorkspaceShell({
  module,
  view,
  onViewChange,
  dateFrom,
  dateTo,
  competitionId,
  apiStatus,
  children,
}: Props) {
  const accent = ACCENT_CLASSES[module.accent]
  const statusLabel = apiStatus
    ? monitoringStatusLabel(apiStatus)
    : module.operationalStatus
  return (
    <section className={`${CARD_BASE} overflow-hidden`}>
      <header className={`border-b border-slate-100 px-4 py-4 sm:px-5 ${accent.softBg}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">{module.label}</h2>
              <MonitoringAccentBadge
                label={statusLabel}
                accent={module.accent}
                ariaLabel={apiStatus || undefined}
              />
            </div>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">{module.description}</p>
            <p className="mt-1 text-xs text-slate-500">Fallback versione: {module.versionLabel}</p>
          </div>
          <MonitoringExportMenu
            moduleKey={module.key as MonitoringModuleKeyApi}
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId}
          />
        </div>
        <div className="mt-3">
          <ModuleViewTabs views={module.views} active={view} onSelect={onViewChange} />
        </div>
      </header>
      <AnimatePresence mode="wait">
        <motion.div
          key={`${module.key}:${view}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={MOTION_MED}
          className="p-4 sm:p-5"
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </section>
  )
}
