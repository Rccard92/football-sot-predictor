export type NavIconName =
  | 'activity'
  | 'file-text'
  | 'calendar'
  | 'target'
  | 'crosshair'
  | 'landmark'
  | 'history'
  | 'bug'
  | 'database'
  | 'bar-chart'
  | 'heart-pulse'
  | 'rotate-ccw'
  | 'flask'
  | 'book-open'
  | 'settings'

export type NavSection = 'cecchino' | 'main' | 'tech'

export type NavItem = {
  to: string
  label: string
  icon: NavIconName
  section: NavSection
}

export const NAV_CECCHINO: NavItem[] = [
  { to: '/cecchino', label: 'Cecchino', icon: 'crosshair', section: 'cecchino' },
  { to: '/cecchino-today', label: 'Cecchino Today', icon: 'calendar', section: 'cecchino' },
  { to: '/monitoraggio-segnali', label: 'Monitoraggio Segnali', icon: 'target', section: 'cecchino' },
  { to: '/monitoraggio-segnali-lab', label: 'Segnali Lab', icon: 'flask', section: 'cecchino' },
  { to: '/segnali-kpi', label: 'Segnali KPI', icon: 'bar-chart', section: 'cecchino' },
  {
    to: '/cecchino/ricerca-credibilita-x',
    label: 'Ricerca Credibilità X',
    icon: 'flask',
    section: 'cecchino',
  },
  {
    to: '/cecchino/ricerca-intensita-goal',
    label: 'Ricerca Intensità Goal',
    icon: 'flask',
    section: 'cecchino',
  },
]

export const NAV_MAIN: NavItem[] = [
  { to: '/match-analysis-framework', label: 'Framework Analisi', icon: 'activity', section: 'main' },
  { to: '/match-variable-audit', label: 'Spiegazione previsione', icon: 'file-text', section: 'main' },
  { to: '/', label: 'Prossima giornata', icon: 'calendar', section: 'main' },
  { to: '/monitoraggio-giocate', label: 'Monitoraggio Giocate', icon: 'target', section: 'main' },
  { to: '/bookmakers', label: 'Bookmakers', icon: 'landmark', section: 'main' },
  { to: '/changelog', label: 'Changelog', icon: 'history', section: 'main' },
]

export const NAV_TECH: NavItem[] = [
  { to: '/model-debug', label: 'Debug Modello', icon: 'bug', section: 'tech' },
  { to: '/api-data-catalog', label: 'Catalogo dati API', icon: 'database', section: 'tech' },
  { to: '/dashboard', label: 'Dashboard modello', icon: 'bar-chart', section: 'tech' },
  { to: '/data-health', label: 'Data Health', icon: 'heart-pulse', section: 'tech' },
  { to: '/backtest', label: 'Backtest', icon: 'rotate-ccw', section: 'tech' },
  { to: '/predictive-simulator', label: 'Simulatore Predittivo', icon: 'flask', section: 'tech' },
  { to: '/model-legend', label: 'Legenda Modello', icon: 'book-open', section: 'tech' },
  { to: '/admin', label: 'Admin', icon: 'settings', section: 'tech' },
]

export const NAV_ALL: NavItem[] = [...NAV_CECCHINO, ...NAV_MAIN, ...NAV_TECH]
