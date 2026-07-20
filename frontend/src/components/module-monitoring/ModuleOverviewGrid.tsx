import { motion } from 'framer-motion'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  getMonitoringModule,
  type MonitoringModuleKey,
} from './moduleMonitoringRegistry'
import { MonitoringAccentBadge } from './MonitoringStatusBadge'
import { ModuleCardSections } from './ModuleCardSections'
import {
  ACCENT_CLASSES,
  CARD_BASE,
  MOTION_MED,
  monitoringStatusLabel,
} from './moduleMonitoringUi'

type Props = {
  items: ModuleOverviewItem[]
  onOpen: (key: MonitoringModuleKey) => void
}

function moduleMetrics(item: ModuleOverviewItem): { label: string; value: string }[] {
  switch (item.module_key) {
    case 'purchasability':
      return [
        {
          label: 'Fixture prospettive',
          value: item.prospective_fixtures == null ? '—' : String(item.prospective_fixtures),
        },
        {
          label: 'Fixture storiche',
          value: item.historical_fixtures == null ? '—' : String(item.historical_fixtures),
        },
        {
          label: 'Righe valutate',
          value: item.evaluated_rows == null ? '—' : String(item.evaluated_rows),
        },
        {
          label: 'Escluse data quality',
          value:
            item.data_quality_excluded_rows == null
              ? '—'
              : String(item.data_quality_excluded_rows),
        },
      ]
    case 'balance-v5':
      return [
        {
          label: 'Copertura descrittiva',
          value: item.coverage_descriptive_ratio || '—',
        },
        {
          label: 'Timestamp verificati',
          value: item.timestamp_verified_ratio || '—',
        },
        {
          label: 'Snapshot prospettici',
          value:
            item.prospective_snapshots == null
              ? item.prospective_persisted == null
                ? '—'
                : String(item.prospective_persisted)
              : String(item.prospective_snapshots),
        },
        {
          label: 'Fixture settled',
          value: item.settled == null ? '—' : String(item.settled),
        },
      ]
    case 'goal-intensity-v5':
      return [
        {
          label: 'Snapshot globali',
          value: item.global_snapshots == null ? '—' : String(item.global_snapshots),
        },
        {
          label: 'Snapshot nel periodo',
          value: item.snapshots_in_period == null ? '—' : String(item.snapshots_in_period),
        },
        {
          label: 'Completed',
          value:
            item.completed_snapshots == null ? '—' : String(item.completed_snapshots),
        },
        {
          label: 'Pending',
          value: item.pending_snapshots == null ? '—' : String(item.pending_snapshots),
        },
      ]
    case 'signals':
      return [
        {
          label: 'Fixture con segnali correnti',
          value:
            item.fixtures_with_current_signals == null
              ? item.fixtures == null
                ? '—'
                : String(item.fixtures)
              : String(item.fixtures_with_current_signals),
        },
        {
          label: 'Attivazioni correnti',
          value:
            item.current_activations == null ? '—' : String(item.current_activations),
        },
        {
          label: 'Correnti valutate',
          value:
            item.current_activations_evaluated == null
              ? '—'
              : String(item.current_activations_evaluated),
        },
        {
          label: 'Post-kickoff escluse',
          value:
            item.post_kickoff_excluded_count == null
              ? item.unusable_count == null
                ? '—'
                : String(item.unusable_count)
              : String(item.post_kickoff_excluded_count),
        },
      ]
    default:
      return [
        { label: 'Fixture', value: item.fixtures == null ? '—' : String(item.fixtures) },
        { label: 'Settled', value: item.settled == null ? '—' : String(item.settled) },
      ]
  }
}

export function ModuleOverviewGrid({ items, onOpen }: Props) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item, idx) => {
        const def = getMonitoringModule(item.module_key)
        const accent = ACCENT_CLASSES[def.accent]
        const statusLabel = item.status
          ? monitoringStatusLabel(item.status)
          : def.operationalStatus
        const metrics = moduleMetrics(item)
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
                </div>
              </div>
            </div>
            <div className="mt-3">
              <ModuleCardSections item={item} compact />
            </div>
            <dl className="mt-3 space-y-1 text-sm text-slate-700">
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Versione</dt>
                <dd className="truncate font-medium">{item.version || def.versionLabel}</dd>
              </div>
              {metrics.map((m) => (
                <div key={m.label} className="flex justify-between gap-2">
                  <dt className="text-slate-500">{m.label}</dt>
                  <dd className="tabular-nums font-medium">{m.value}</dd>
                </div>
              ))}
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
