import { useMemo } from 'react'
import type { LineupImpactSideSimulation, SportApiPlayerMatchRow } from '../../types/lineupImpact'
import type { PlayerDbProfileRow } from '../../types/playerDbProfiles'
import type { SportApiLineupPlayer, SportApiTeamLineupSide } from '../../types/sportapi'
import { computeLineupOverallXi, profilesToApiIdMap } from '../../utils/lineupOverallXi'
import { buildStarterFieldRows } from '../../utils/starterFieldForce'
import { buildTacticalLayout } from '../../utils/sportapiFormation'
import { SportApiMissingPanel } from './SportApiMissingPanel'
import { SportApiOverallXiCard } from './SportApiOverallXiCard'
import { SportApiStartersForceTable } from './SportApiStartersForceTable'
import { SportApiTacticalFormation } from './SportApiTacticalFormation'
import { RoleBadge } from './RoleBadge'
import type { SportApiDisplayRole } from '../../types/sportapi'

function countMissing(mp: SportApiTeamLineupSide['missing_players']): number {
  return (mp.injured?.length ?? 0) + (mp.suspended?.length ?? 0) + (mp.other?.length ?? 0)
}

function BenchPlayerLine({ player }: { player: SportApiLineupPlayer }) {
  const name = player.short_name || player.player_name
  const role = (player.display_role || 'C') as SportApiDisplayRole
  return (
    <li className="flex items-center gap-1.5 text-xs text-slate-800">
      <RoleBadge role={role} />
      <span className="font-medium">{name}</span>
      {player.jersey_number != null ? (
        <span className="text-[10px] text-slate-500">#{player.jersey_number}</span>
      ) : null}
    </li>
  )
}

export function SportApiLineupSide({
  side,
  lineupSide,
  matching,
  profiles,
  meta,
  lineupConfidenceLabel,
}: {
  side: SportApiTeamLineupSide
  lineupSide?: LineupImpactSideSimulation
  matching?: SportApiPlayerMatchRow[]
  profiles?: PlayerDbProfileRow[]
  meta: {
    confirmed?: boolean | null
    confidenceScore?: number | null
    fetchedAt?: string | null
    profilesMissing?: boolean
  }
  lineupConfidenceLabel?: string | null
}) {
  const profilesMap = useMemo(() => profilesToApiIdMap(profiles), [profiles])

  const tacticalLayout = useMemo(
    () => buildTacticalLayout(side.formation, side.starters),
    [side.formation, side.starters],
  )

  const overallXi = useMemo(
    () =>
      computeLineupOverallXi(side.starters, side.formation, lineupSide, matching, profilesMap, {
        confirmed: meta.confirmed ?? side.confirmed,
        confidenceScore: meta.confidenceScore,
        fetchedAt: meta.fetchedAt,
        profilesMissing: meta.profilesMissing,
        rosterSyncHint: lineupSide?.roster_sync_hint,
        lineupConfidenceLabel,
        missingPlayersCount: countMissing(side.missing_players),
      }),
    [side, lineupSide, matching, profilesMap, meta, lineupConfidenceLabel],
  )

  const forceRows = useMemo(
    () => buildStarterFieldRows(side.formation, side.starters, lineupSide, matching, profilesMap),
    [side.formation, side.starters, lineupSide, matching, profilesMap],
  )

  const statusLabel =
    meta.confirmed === true || side.confirmed === true
      ? 'Ufficiali'
      : meta.confirmed === false || side.confirmed === false
        ? 'Probabili'
        : null

  return (
    <div className="flex h-full flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="border-b border-slate-100 pb-2">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        <p className="mt-0.5 text-xs text-slate-600">
          Modulo <span className="font-mono font-medium">{side.formation || '—'}</span>
          {statusLabel ? (
            <span className="ml-2 rounded border border-slate-200 bg-slate-50 px-1.5 py-px text-[10px] text-slate-600">
              {statusLabel}
            </span>
          ) : null}
        </p>
      </div>

      <SportApiOverallXiCard breakdown={overallXi} />

      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Formazione tattica</p>
        <SportApiTacticalFormation layout={tacticalLayout} />
      </div>

      <SportApiStartersForceTable rows={forceRows} />

      <SportApiMissingPanel missingPlayers={side.missing_players} />

      {side.substitutes.length > 0 ? (
        <details className="rounded-lg border border-slate-100">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-800 hover:bg-slate-50">
            Panchina ({side.substitutes.length})
          </summary>
          <ul className="space-y-1 border-t border-slate-100 px-3 py-2">
            {side.substitutes.map((p) => (
              <BenchPlayerLine key={p.provider_player_id} player={p} />
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}
