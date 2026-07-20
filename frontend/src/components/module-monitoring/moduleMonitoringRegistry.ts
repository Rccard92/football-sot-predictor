import type { NavIconName } from '../../config/navItems'

export type MonitoringModuleKey =
  | 'purchasability'
  | 'balance-v5'
  | 'goal-intensity-v5'
  | 'signals'

export type MonitoringViewDef = {
  id: string
  label: string
}

export type MonitoringModuleDef = {
  key: MonitoringModuleKey
  label: string
  shortLabel: string
  description: string
  operationalStatus: string
  versionLabel: string
  accent: 'purchasability' | 'balance' | 'goal' | 'signals'
  icon: NavIconName
  defaultView: string
  views: MonitoringViewDef[]
  exportCapabilities: string[]
}

export const MONITORING_MODULES: MonitoringModuleDef[] = [
  {
    key: 'purchasability',
    label: 'Acquistabilità',
    shortLabel: 'Acquistabilità',
    description:
      'Validazione prospettica e laboratori di ricerca sull’indice di Acquistabilità.',
    operationalStatus: 'Preview monitorata',
    versionLabel: 'candidate_2 · features_v1_1',
    accent: 'purchasability',
    icon: 'activity',
    defaultView: 'overview',
    views: [
      { id: 'overview', label: 'Overview' },
      { id: 'validation', label: 'Validazione' },
      { id: 'audit', label: 'Audit' },
      { id: 'statistical-research', label: 'Ricerca statistica' },
      { id: 'residual-reliability', label: 'Affidabilità residuale' },
      { id: 'exports', label: 'Export' },
    ],
    exportCapabilities: ['analysis-pack', 'rows-csv', 'summary-json'],
  },
  {
    key: 'balance-v5',
    label: 'Equilibrio vs Squilibrio v5',
    shortLabel: 'Balance v5',
    description:
      'Monitoraggio descrittivo dei pilastri F36, Dominanza, Credibilità X e Gap.',
    operationalStatus: 'Ufficiale monitorato',
    versionLabel: 'cecchino_balance_v5_v2',
    accent: 'balance',
    icon: 'target',
    defaultView: 'overview',
    views: [
      { id: 'overview', label: 'Overview' },
      { id: 'empirical-dataset', label: 'Dataset empirico' },
      { id: 'geometry-f36', label: 'Geometria F36' },
      { id: 'dominance', label: 'Dominanza' },
      { id: 'draw-credibility', label: 'Credibilità X' },
      { id: 'gap-coherence', label: 'Gap' },
      { id: 'data-health', label: 'Data health' },
      { id: 'exports', label: 'Export' },
    ],
    exportCapabilities: ['analysis-pack', 'summary-json'],
  },
  {
    key: 'goal-intensity-v5',
    label: 'Intensità Goal Avanzata v5',
    shortLabel: 'Goal Intensity',
    description:
      'Preview research: candidati, calibrazione e campione prospettico.',
    operationalStatus: 'Preview research',
    versionLabel: 'goal_intensity_v5_preview',
    accent: 'goal',
    icon: 'flask',
    defaultView: 'overview',
    views: [
      { id: 'overview', label: 'Overview' },
      { id: 'candidates', label: 'Candidati' },
      { id: 'prospective-results', label: 'Risultati prospettici' },
      { id: 'calibration', label: 'Calibrazione' },
      { id: 'data-health', label: 'Data health' },
      { id: 'research', label: 'Ricerca' },
      { id: 'exports', label: 'Export' },
    ],
    exportCapabilities: ['analysis-pack', 'summary-json'],
  },
  {
    key: 'signals',
    label: 'Segnali Cecchino',
    shortLabel: 'Segnali',
    description: 'Performance modelli, trend e laboratorio segnali.',
    operationalStatus: 'Operativo',
    versionLabel: 'signals_lab',
    accent: 'signals',
    icon: 'bar-chart',
    defaultView: 'overview',
    views: [
      { id: 'overview', label: 'Overview' },
      { id: 'performance', label: 'Performance' },
      { id: 'models', label: 'Modelli' },
      { id: 'trends', label: 'Trend' },
      { id: 'lab', label: 'Lab' },
      { id: 'exports', label: 'Export' },
    ],
    exportCapabilities: ['analysis-pack', 'rows-csv', 'summary-json'],
  },
]

export function getMonitoringModule(key: string | null | undefined): MonitoringModuleDef {
  return (
    MONITORING_MODULES.find((m) => m.key === key) || MONITORING_MODULES[0]
  )
}

export function isMonitoringModuleKey(v: string | null): v is MonitoringModuleKey {
  return MONITORING_MODULES.some((m) => m.key === v)
}
