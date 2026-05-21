import type { SportApiDisplayRole, SportApiLineupPlayer } from '../types/sportapi'

const ROLE_ORDER: Record<SportApiDisplayRole, number> = { P: 0, D: 1, C: 2, A: 3 }

export type TacticalLayoutPlayer = SportApiLineupPlayer & {
  tactical_role: SportApiDisplayRole
  api_role?: SportApiDisplayRole
}

export type TacticalLayoutLine = {
  label: string
  tactical_role: SportApiDisplayRole
  players: TacticalLayoutPlayer[]
}

export type TacticalLayoutResult = {
  lines: TacticalLayoutLine[]
  estimated: boolean
  warning?: string
  playerLineIndex: Map<number, number>
  playerTacticalRole: Map<number, SportApiDisplayRole>
}

export function parseFormationCounts(formation: string | null | undefined): number[] {
  if (!formation) return []
  const matches = formation.match(/\d+/g)
  if (!matches) return []
  return matches.map((x) => parseInt(x, 10)).filter((n) => !Number.isNaN(n) && n > 0)
}

/** Ordine SportAPI: preserva original_index o posizione in lista salvata. */
export function sortStartersByOriginalIndex(starters: SportApiLineupPlayer[]): SportApiLineupPlayer[] {
  return [...starters]
    .map((p, i) => ({
      ...p,
      original_index: p.original_index ?? i,
    }))
    .sort((a, b) => (a.original_index ?? 0) - (b.original_index ?? 0))
}

function rowLabelForOutfieldIndex(i: number, totalOutfieldRows: number): string {
  if (i === 0) return 'Difesa'
  if (i === totalOutfieldRows - 1) return 'Attacco'
  if (totalOutfieldRows >= 4 && i === totalOutfieldRows - 2) return 'Trequartista'
  if (totalOutfieldRows >= 4 && i === 1) return 'Mediana'
  return 'Centrocampo'
}

function tacticalRoleForOutfieldRow(i: number, totalOutfieldRows: number): SportApiDisplayRole {
  if (i === 0) return 'D'
  if (i === totalOutfieldRows - 1) return 'A'
  return 'C'
}

function withTacticalMeta(
  p: SportApiLineupPlayer,
  tacticalRole: SportApiDisplayRole,
): TacticalLayoutPlayer {
  return {
    ...p,
    tactical_role: tacticalRole,
    api_role: (p.display_role || 'C') as SportApiDisplayRole,
  }
}

function buildIndexMaps(lines: TacticalLayoutLine[]): {
  playerLineIndex: Map<number, number>
  playerTacticalRole: Map<number, SportApiDisplayRole>
} {
  const playerLineIndex = new Map<number, number>()
  const playerTacticalRole = new Map<number, SportApiDisplayRole>()
  lines.forEach((line, li) => {
    for (const p of line.players) {
      playerLineIndex.set(p.provider_player_id, li)
      playerTacticalRole.set(p.provider_player_id, p.tactical_role)
    }
  })
  return { playerLineIndex, playerTacticalRole }
}

/** Assegnazione sequenziale: GK + blocchi del modulo nell’ordine originale SportAPI. */
export function buildTacticalLayoutByFormation(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
): TacticalLayoutResult {
  const ordered = sortStartersByOriginalIndex(starters)
  if (!ordered.length) {
    return { lines: [], estimated: false, playerLineIndex: new Map(), playerTacticalRole: new Map() }
  }

  const counts = parseFormationCounts(formation)
  const outfieldSum = counts.reduce((a, b) => a + b, 0)
  const canUseSequential =
    counts.length > 0 && ordered.length === 11 && outfieldSum === 10

  if (canUseSequential) {
    const lines: TacticalLayoutLine[] = []
    let idx = 0
    const gk = ordered[idx++]
    lines.push({
      label: 'Portiere',
      tactical_role: 'P',
      players: [withTacticalMeta(gk, 'P')],
    })

    counts.forEach((n, i) => {
      const chunk = ordered.slice(idx, idx + n)
      idx += n
      const role = tacticalRoleForOutfieldRow(i, counts.length)
      lines.push({
        label: rowLabelForOutfieldIndex(i, counts.length),
        tactical_role: role,
        players: chunk.map((p) => withTacticalMeta(p, role)),
      })
    })

    const maps = buildIndexMaps(lines)
    return {
      lines,
      estimated: false,
      ...maps,
    }
  }

  return buildTacticalLayoutRoleFallback(ordered)
}

/** Fallback: P → D → C → A per ruolo API, ordine originale dentro ogni gruppo. */
function buildTacticalLayoutRoleFallback(ordered: SportApiLineupPlayer[]): TacticalLayoutResult {
  const warning = 'Disposizione tattica stimata: dati modulo incompleti.'

  const gkCand =
    ordered.find((p) => (p.display_role || 'C') === 'P') ?? ordered[0]
  const rest = ordered.filter((p) => p.provider_player_id !== gkCand.provider_player_id)

  const byRole: Record<SportApiDisplayRole, SportApiLineupPlayer[]> = {
    P: [],
    D: [],
    C: [],
    A: [],
  }
  for (const p of rest) {
    const r = (p.display_role || 'C') as SportApiDisplayRole
    if (r in byRole && r !== 'P') byRole[r].push(p)
  }

  const lines: TacticalLayoutLine[] = [
    {
      label: 'Portiere',
      tactical_role: 'P',
      players: [withTacticalMeta(gkCand, 'P')],
    },
  ]

  if (byRole.D.length) {
    lines.push({
      label: 'Difesa',
      tactical_role: 'D',
      players: byRole.D.map((p) => withTacticalMeta(p, 'D')),
    })
  }
  if (byRole.C.length) {
    lines.push({
      label: 'Centrocampo',
      tactical_role: 'C',
      players: byRole.C.map((p) => withTacticalMeta(p, 'C')),
    })
  }
  if (byRole.A.length) {
    lines.push({
      label: 'Attacco',
      tactical_role: 'A',
      players: byRole.A.map((p) => withTacticalMeta(p, 'A')),
    })
  }

  const remainder = rest.filter(
    (p) =>
      !lines.some((ln) => ln.players.some((x) => x.provider_player_id === p.provider_player_id)),
  )
  if (remainder.length) {
    lines.push({
      label: 'Altri',
      tactical_role: 'C',
      players: remainder.map((p) => withTacticalMeta(p, (p.display_role || 'C') as SportApiDisplayRole)),
    })
  }

  const maps = buildIndexMaps(lines)
  return {
    lines,
    estimated: true,
    warning,
    ...maps,
  }
}

/**
 * Layout tattico Audit: modulo + original_index (ignora tactical_lines backend basate su ruolo API).
 */
export function buildTacticalLayout(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
): TacticalLayoutResult {
  return buildTacticalLayoutByFormation(formation, starters)
}

export function tacticalLineIndexForLayout(
  layout: TacticalLayoutResult,
  providerPlayerId: number,
): number {
  return layout.playerLineIndex.get(providerPlayerId) ?? 99
}

export function tacticalRoleForPlayer(
  layout: TacticalLayoutResult,
  providerPlayerId: number,
): SportApiDisplayRole {
  return layout.playerTacticalRole.get(providerPlayerId) ?? 'C'
}

export function roleSortKey(role: SportApiDisplayRole | string | undefined): number {
  const r = (role || 'C') as SportApiDisplayRole
  return ROLE_ORDER[r] ?? 2
}
