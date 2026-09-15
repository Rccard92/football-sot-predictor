import type { LivePatternSignal } from '../../lib/cecchinoLiveApi'

export type PatternGroupView = { key: string; first: LivePatternSignal; patterns: LivePatternSignal[] }

/** Stesso mercato, linea e direzione = un solo segnale (come nell'osservazione live). */
export function groupPatternSignals(patterns: LivePatternSignal[]): PatternGroupView[] {
  const map = new Map<string, PatternGroupView>()
  for (const p of patterns) {
    const key = `${p.target_type}|${p.target_key}|${p.threshold ?? ''}|${p.direction ?? 1}`
    const g = map.get(key)
    if (g) g.patterns.push(p)
    else map.set(key, { key, first: p, patterns: [p] })
  }
  return [...map.values()].sort(
    (a, b) => Number(a.first.target_type !== 'market') - Number(b.first.target_type !== 'market') || b.patterns.length - a.patterns.length,
  )
}

/** Pattern di riferimento del gruppo: quello con più partite nello storico. */
export function referencePattern(g: PatternGroupView): LivePatternSignal {
  return g.patterns.reduce((best, x) => (x.total_n > best.total_n ? x : best), g.first)
}

/** Quota minima per essere in profitto con la percentuale di riuscita storica. */
export function breakEvenQuota(winRatePct: number | null | undefined): number | null {
  return winRatePct != null && winRatePct > 0 ? 100 / winRatePct : null
}

const RESULT_SETS: Record<string, string[]> = {
  HOME: ['1'], DRAW: ['X'], AWAY: ['2'], ONE_X: ['1', 'X'], X_TWO: ['X', '2'], ONE_TWO: ['1', '2'],
}

function line(key: string): number | null {
  const m = /^(OVER|UNDER)_(\d+)_(\d+)$/.exec(key)
  return m ? Number(`${m[2]}.${m[3]}`) : null
}

/** Due mercati che non possono vincere insieme (es. 1 e 2, Over 2.5 e Under 2.5). */
export function marketsConflict(a: string, b: string): boolean {
  if (a === b) return false
  const pt = (k: string) => k.endsWith('_PT')
  const base = (k: string) => k.replace(/_PT$/, '')
  if (RESULT_SETS[base(a)] && RESULT_SETS[base(b)]) {
    if (pt(a) !== pt(b)) return false
    const sb = RESULT_SETS[base(b)]
    return !RESULT_SETS[base(a)].some((r) => sb.includes(r))
  }
  const la = line(a)
  const lb = line(b)
  if (la == null || lb == null) return false
  const over = a.startsWith('OVER') ? la : b.startsWith('OVER') ? lb : null
  const under = a.startsWith('UNDER') ? la : b.startsWith('UNDER') ? lb : null
  return over != null && under != null && under <= over
}

export type PatternRelation = 'confirmed' | 'conflict' | null

/** Relazione di un mercato con i mercati indicati dai pattern accesi. */
export function patternRelation(marketKey: string, patternMarkets: string[]): PatternRelation {
  if (patternMarkets.includes(marketKey)) return 'confirmed'
  if (patternMarkets.some((k) => marketsConflict(marketKey, k))) return 'conflict'
  return null
}

/** Mercati con quota indicati dai pattern accesi. */
export function patternMarketKeys(patterns: LivePatternSignal[] | undefined): string[] {
  return [...new Set((patterns ?? []).filter((p) => p.target_type === 'market').map((p) => p.target_key))]
}
