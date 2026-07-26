/** Tema locale Cecchino Lab — isolato dal tema globale app. */

export const labCssVars = {
  '--lab-bg': '#0b1624',
  '--lab-bg-elevated': '#122033',
  '--lab-surface': '#15263a',
  '--lab-surface-2': '#1a2f47',
  '--lab-border': 'rgba(120, 190, 220, 0.14)',
  '--lab-cyan': '#2ee6ff',
  '--lab-cyan-dim': 'rgba(46, 230, 255, 0.15)',
  '--lab-ok': '#3dd68c',
  '--lab-warn': '#f0b429',
  '--lab-err': '#f07178',
  '--lab-text': '#e8f1f8',
  '--lab-muted': '#8aa0b5',
} as const

export function qualityLabel(status: string): string {
  switch (status) {
    case 'complete':
      return 'Completo'
    case 'complete_with_warnings':
      return 'Completo con warning'
    case 'partial':
      return 'Parziale'
    case 'error':
      return 'Errore'
    case 'poor':
      return 'Scarso'
    default:
      return status || '—'
  }
}
