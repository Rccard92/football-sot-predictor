import type { SportApiLineupPlayer } from '../../types/sportapi'
import { resolveTacticalLines, tacticalRowLabel } from '../../utils/sportapiFormation'
import { RoleBadge } from './RoleBadge'

function PlayerChip({ player }: { player: SportApiLineupPlayer }) {
  const name = player.short_name || player.player_name
  const role = player.display_role || 'C'
  return (
    <div className="flex max-w-[8.5rem] flex-col items-center gap-0.5 px-1">
      <div className="flex items-center gap-1">
        <RoleBadge role={role} />
        {player.jersey_number != null ? (
          <span className="text-[10px] tabular-nums text-slate-500">#{player.jersey_number}</span>
        ) : null}
      </div>
      <span className="w-full truncate text-center text-[11px] font-medium text-slate-900" title={name}>
        {name}
      </span>
    </div>
  )
}

export function SportApiTacticalFormation({
  formation,
  starters,
  tacticalLinesFromApi,
}: {
  formation?: string | null
  starters: SportApiLineupPlayer[]
  tacticalLinesFromApi?: SportApiLineupPlayer[][] | null
}) {
  const lines = resolveTacticalLines(formation, starters, tacticalLinesFromApi)

  if (!lines.length) {
    return <p className="text-xs text-slate-500">Nessun titolare salvato.</p>
  }

  return (
    <div className="space-y-2">
      {lines.map((row, ri) => {
        const label = tacticalRowLabel(formation, ri, lines.length)
        return (
          <div key={ri} className="rounded-lg border border-slate-100 bg-gradient-to-b from-slate-50/90 to-white px-2 py-2">
            {label ? (
              <p className="mb-1.5 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                {label}
              </p>
            ) : null}
            <div className="flex flex-wrap items-end justify-center gap-x-3 gap-y-2">
              {row.map((p) => (
                <PlayerChip key={p.provider_player_id} player={p} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
