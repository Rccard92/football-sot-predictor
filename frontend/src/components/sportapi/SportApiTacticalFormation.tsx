import type { TacticalLayoutResult } from '../../utils/sportapiFormation'
import type { SportApiDisplayRole } from '../../types/sportapi'
import { roleLabel } from '../../utils/sportapiRoles'
import { RoleBadge } from './RoleBadge'

function PlayerChip({
  name,
  jerseyNumber,
  tacticalRole,
  apiRole,
}: {
  name: string
  jerseyNumber?: number | null
  tacticalRole: SportApiDisplayRole
  apiRole?: SportApiDisplayRole
}) {
  const apiHint =
    apiRole && apiRole !== tacticalRole
      ? `Ruolo API: ${roleLabel(apiRole)}`
      : undefined

  return (
    <div className="flex max-w-[8.5rem] flex-col items-center gap-0.5 px-1">
      <div className="flex items-center gap-1" title={apiHint}>
        <RoleBadge role={tacticalRole} />
        {jerseyNumber != null ? (
          <span className="text-[10px] tabular-nums text-slate-500">#{jerseyNumber}</span>
        ) : null}
      </div>
      <span className="w-full truncate text-center text-[11px] font-medium text-slate-900" title={name}>
        {name}
      </span>
    </div>
  )
}

export function SportApiTacticalFormation({ layout }: { layout: TacticalLayoutResult }) {
  if (!layout.lines.length) {
    return <p className="text-xs text-slate-500">Nessun titolare salvato.</p>
  }

  return (
    <div className="space-y-2">
      {layout.warning ? (
        <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-900">
          {layout.warning}
        </p>
      ) : null}
      {layout.lines.map((row, ri) => (
        <div
          key={ri}
          className="rounded-lg border border-slate-100 bg-gradient-to-b from-slate-50/90 to-white px-2 py-2"
        >
          <p className="mb-1.5 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            {row.label}
          </p>
          <div className="flex flex-wrap items-end justify-center gap-x-3 gap-y-2">
            {row.players.map((p) => (
              <PlayerChip
                key={p.provider_player_id}
                name={p.short_name || p.player_name}
                jerseyNumber={p.jersey_number}
                tacticalRole={p.tactical_role}
                apiRole={p.api_role}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
