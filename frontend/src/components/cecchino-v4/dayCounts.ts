import type { V4FixturesResponse } from '../../lib/cecchinoV4Api'
import { noPlayReasonLabel } from './constants'

export type V4DayCounts = { fixtures: number; plays: number; abstained: number; reasons: string }

/** Conteggi della giornata: partite, giocate, astensioni (con i motivi per il suggerimento). */
export function dayCounts(data: V4FixturesResponse): V4DayCounts {
  const fixtures = data.items.length
  const plays = data.items.filter((f) => f.best_play != null).length
  const entries = Object.entries(data.abstentions ?? {}).filter(([, n]) => n > 0)
  const fromServer = entries.reduce((s, [, n]) => s + n, 0)
  const abstained = fromServer > 0 ? fromServer : Math.max(0, fixtures - plays)
  const reasons = entries
    .map(([reason, n]) => [noPlayReasonLabel(reason), n] as const)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, n]) => `${label} ${n}`)
    .join(', ')
  return { fixtures, plays, abstained, reasons }
}
