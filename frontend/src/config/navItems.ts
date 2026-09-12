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
  { to: '/bet-builder', label: 'Bet Builder', icon: 'target', section: 'cecchino' },
  { to: '/cecchino-lab', label: 'Cecchino Lab', icon: 'database', section: 'cecchino' },
  { to: '/pattern-insights', label: 'Pattern Insights', icon: 'flask', section: 'cecchino' },
  { to: '/monitoraggio-moduli', label: 'Monitoraggio Moduli', icon: 'activity', section: 'cecchino' },
  { to: '/monitoraggio-segno-1', label: 'Monitoraggio Segno 1', icon: 'target', section: 'cecchino' },
  { to: '/monitoraggio-segnali', label: 'Monitoraggio Segnali', icon: 'target', section: 'cecchino' },
  { to: '/segnali-kpi', label: 'Segnali KPI', icon: 'bar-chart', section: 'cecchino' },
]

export const NAV_MAIN: NavItem[] = [
  { to: '/bookmakers', label: 'Bookmakers', icon: 'landmark', section: 'main' },
  { to: '/changelog', label: 'Changelog', icon: 'history', section: 'main' },
]

export const NAV_TECH: NavItem[] = [
  { to: '/data-health', label: 'Data Health', icon: 'heart-pulse', section: 'tech' },
  { to: '/admin', label: 'Admin', icon: 'settings', section: 'tech' },
]

export const NAV_ALL: NavItem[] = [...NAV_CECCHINO, ...NAV_MAIN, ...NAV_TECH]
