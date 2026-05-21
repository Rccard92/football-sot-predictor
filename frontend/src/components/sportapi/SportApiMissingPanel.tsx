import type { SportApiDisplayRole, SportApiMissingGrouped, SportApiMissingPlayer } from '../../types/sportapi'
import { RoleBadge } from './RoleBadge'

function fmtDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  try {
    return new Date(iso).toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return iso
  }
}

function MissingEntry({ player }: { player: SportApiMissingPlayer }) {
  const role = (player.display_role || 'C') as SportApiDisplayRole
  const reason = player.description || player.external_type || player.reason || '—'
  const end = fmtDate(player.expected_end_date)

  return (
    <li className="rounded-md border border-slate-100 bg-white px-2 py-1.5 text-xs text-slate-800">
      <div className="flex flex-wrap items-center gap-1.5">
        <RoleBadge role={role} />
        <span className="font-medium">{player.short_name || player.player_name}</span>
        {player.jersey_number != null ? (
          <span className="text-[10px] text-slate-500">#{player.jersey_number}</span>
        ) : null}
      </div>
      <p className="mt-0.5 text-slate-600">{reason}</p>
      {end ? <p className="mt-0.5 text-[10px] text-slate-500">Rientro previsto: {end}</p> : null}
    </li>
  )
}

function MissingCategory({
  title,
  players,
}: {
  title: string
  players: SportApiMissingPlayer[]
}) {
  if (players.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <ul className="mt-1 space-y-1.5">
        {players.map((p) => (
          <MissingEntry key={p.provider_player_id} player={p} />
        ))}
      </ul>
    </div>
  )
}

export function SportApiMissingPanel({ missingPlayers }: { missingPlayers: SportApiMissingGrouped }) {
  const has =
    missingPlayers.injured.length > 0 ||
    missingPlayers.suspended.length > 0 ||
    missingPlayers.other.length > 0

  if (!has) return null

  return (
    <div className="border-t border-slate-100 pt-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Indisponibili</p>
      <MissingCategory title="Infortunati" players={missingPlayers.injured} />
      <MissingCategory title="Squalificati" players={missingPlayers.suspended} />
      <MissingCategory title="Altri indisponibili" players={missingPlayers.other} />
    </div>
  )
}
