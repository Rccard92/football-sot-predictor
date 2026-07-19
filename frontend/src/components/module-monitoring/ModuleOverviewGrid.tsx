import { motion } from 'framer-motion'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  getMonitoringModule,
  type MonitoringModuleKey,
} from './moduleMonitoringRegistry'
import { MonitoringAccentBadge, MonitoringStatusBadge } from './MonitoringStatusBadge'
import { MonitoringProgressRing } from './MonitoringProgressRing'
import {
  ACCENT_CLASSES,
  CARD_BASE,
  MOTION_MED,
  coverageDisplay,
  monitoringStatusLabel,
} from './moduleMonitoringUi'

type Props = {
  items: ModuleOverviewItem[]
  onOpen: (key: MonitoringModuleKey) => void
}

export function ModuleOverviewGrid({ items, onOpen }: Props) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item, idx) => {
        const def = getMonitoringModule(item.module_key)
        const accent = ACCENT_CLASSES[def.accent]
        const cov = coverageDisplay(item.coverage, item.coverage != null)
        const statusLabel = item.status
          ? monitoringStatusLabel(item.status)
          : def.operationalStatus
        return (
          <motion.article
            key={item.module_key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...MOTION_MED, delay: idx * 0.04 }}
            className={`${CARD_BASE} ${accent.softBg} flex flex-col p-4`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-slate-900">{def.label}</h3>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <MonitoringAccentBadge
                    label={statusLabel}
                    accent={def.accent}
                    ariaLabel={item.status || undefined}
                  />
                  <MonitoringStatusBadge label={cov.text} tone={cov.tone} />
                </div>
              </div>
              <MonitoringProgressRing
                value={item.coverage ?? null}
                color={accent.chartPrimary}
                size={52}
              />
            </div>
            <dl className="mt-3 space-y-1 text-sm text-slate-700">
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Versione</dt>
                <dd className="truncate font-medium">{item.version || def.versionLabel}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Fixture</dt>
                <dd className="tabular-nums font-medium">
                  {item.fixtures == null ? '—' : item.fixtures}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Settled</dt>
                <dd className="tabular-nums font-medium">
                  {item.settled == null ? '—' : item.settled}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Checkpoint</dt>
                <dd className="truncate text-right text-xs">
                  {item.next_review_at || 'Raccolta dati non ancora disponibile'}
                </dd>
              </div>
            </dl>
            {(item.warnings || []).length > 0 ? (
              <p className="mt-2 text-xs text-amber-700">{item.warnings![0]}</p>
            ) : null}
            <button
              type="button"
              onClick={() => onOpen(def.key)}
              className={`mt-auto pt-3 text-left text-sm font-semibold ${accent.text}`}
            >
              Apri monitoraggio →
            </button>
          </motion.article>
        )
      })}
    </div>
  )
}
