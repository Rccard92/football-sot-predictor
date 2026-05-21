import type { SportApiDisplayRole, SportApiLineupPlayer } from '../types/sportapi'

const ROLE_ORDER: Record<SportApiDisplayRole, number> = { P: 0, D: 1, C: 2, A: 3 }

function extractSortKey(player: SportApiLineupPlayer): number {
  const oi = player.original_index ?? 999
  return oi
}

function sortByRoleAndIndex(players: SportApiLineupPlayer[], role: SportApiDisplayRole): SportApiLineupPlayer[] {
  return players
    .filter((p) => (p.display_role || 'C') === role)
    .sort((a, b) => extractSortKey(a) - extractSortKey(b))
}

function splitPool(pool: SportApiLineupPlayer[], n: number): [SportApiLineupPlayer[], SportApiLineupPlayer[]] {
  if (n <= 0) return [[], [...pool]]
  return [pool.slice(0, n), pool.slice(n)]
}

export function parseFormationCounts(formation: string | null | undefined): number[] {
  if (!formation) return []
  const matches = formation.match(/\d+/g)
  if (!matches) return []
  return matches.map((x) => parseInt(x, 10)).filter((n) => !Number.isNaN(n))
}

/** Stesso algoritmo di build_tactical_lines (backend sportapi_lineup_present.py). */
export function buildTacticalLinesFromFormation(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
): SportApiLineupPlayer[][] {
  if (!starters.length) return []

  const byRole: Record<SportApiDisplayRole, SportApiLineupPlayer[]> = {
    P: sortByRoleAndIndex(starters, 'P'),
    D: sortByRoleAndIndex(starters, 'D'),
    C: sortByRoleAndIndex(starters, 'C'),
    A: sortByRoleAndIndex(starters, 'A'),
  }

  const lines: SportApiLineupPlayer[][] = []
  if (byRole.P.length) lines.push(byRole.P.slice(0, 1))

  const counts = parseFormationCounts(formation)
  let dPool = [...byRole.D]
  let cPool = [...byRole.C]
  let aPool = [...byRole.A]

  if (counts.length) {
    counts.forEach((n, i) => {
      if (i === 0) {
        const [chunk, rest] = splitPool(dPool, n)
        dPool = rest
        if (chunk.length) lines.push(chunk)
      } else if (i === counts.length - 1) {
        const [chunk, rest] = splitPool(aPool, n)
        aPool = rest
        if (chunk.length) lines.push(chunk)
      } else {
        const [chunk, rest] = splitPool(cPool, n)
        cPool = rest
        if (chunk.length) lines.push(chunk)
      }
    })
    const remainder = [...dPool, ...cPool, ...aPool]
    if (remainder.length) lines.push(remainder)
  } else {
    for (const role of ['D', 'C', 'A'] as SportApiDisplayRole[]) {
      if (byRole[role].length) lines.push(byRole[role])
    }
  }

  return lines
}

export function resolveTacticalLines(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
  tacticalLinesFromApi?: SportApiLineupPlayer[][] | null,
): SportApiLineupPlayer[][] {
  if (tacticalLinesFromApi && tacticalLinesFromApi.length > 0) {
    return tacticalLinesFromApi
  }
  return buildTacticalLinesFromFormation(formation, starters)
}

/** Indice riga tattica per un giocatore (per ordinamento tabella). */
export function tacticalLineIndexForPlayer(
  lines: SportApiLineupPlayer[][],
  providerPlayerId: number,
): number {
  const idx = lines.findIndex((row) => row.some((p) => p.provider_player_id === providerPlayerId))
  return idx >= 0 ? idx : 99
}

export function tacticalRowLabel(
  formation: string | null | undefined,
  rowIndex: number,
  rowCount: number,
): string | null {
  if (rowCount <= 0) return null
  if (rowIndex === 0) return 'Portiere'

  const counts = parseFormationCounts(formation)
  const isLast = rowIndex === rowCount - 1
  const isSecondLast = rowIndex === rowCount - 2

  if (counts.length >= 4 && isSecondLast && !isLast) return 'Trequartista'
  if (isLast) return 'Attacco'
  if (rowIndex === 1 || (counts.length && rowIndex === 1)) return 'Difesa'
  if (isSecondLast && rowCount > 3) return 'Centrocampo alto'
  return 'Centrocampo'
}

export function roleSortKey(role: SportApiDisplayRole | string | undefined): number {
  const r = (role || 'C') as SportApiDisplayRole
  return ROLE_ORDER[r] ?? 2
}
