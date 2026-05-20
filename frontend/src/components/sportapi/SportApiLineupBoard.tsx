import type {
  SportApiDisplayRole,
  SportApiLineupPlayer,
  SportApiMissingGrouped,
  SportApiMissingPlayer,
} from '../../types/sportapi'
import { RoleBadge } from './RoleBadge'

function PlayerLine({ player }: { player: SportApiLineupPlayer | SportApiMissingPlayer }) {
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

function MissingEntry({ player }: { player: SportApiMissingPlayer }) {
  const role = (player.display_role || 'C') as SportApiDisplayRole
  const detail = player.description || player.external_type || player.reason || '—'
  return (
    <li className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-xs text-slate-800">
      <RoleBadge role={role} />
      <span className="font-medium">{player.player_name}</span>
      <span className="text-slate-500">— {detail}</span>
    </li>
  )
}

function MissingSection({
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
      <ul className="mt-1 space-y-1">
        {players.map((p) => (
          <MissingEntry key={p.provider_player_id} player={p} />
        ))}
      </ul>
    </div>
  )
}

export function SportApiLineupBoard({
  teamName,
  formation,
  confirmed,
  starters,
  substitutes,
  missingPlayers,
  tacticalLines,
  compact = false,
}: {
  teamName: string
  formation?: string | null
  confirmed?: boolean | null
  starters: SportApiLineupPlayer[]
  substitutes: SportApiLineupPlayer[]
  missingPlayers: SportApiMissingGrouped
  tacticalLines?: SportApiLineupPlayer[][]
  compact?: boolean
}) {
  const lines =
    tacticalLines && tacticalLines.length > 0
      ? tacticalLines
      : starters.length > 0
        ? [starters]
        : []

  const statusLabel =
    confirmed === true
      ? 'Ufficiali'
      : confirmed === false
        ? 'Probabili'
        : null

  return (
    <div
      className={`flex h-full flex-col rounded-xl border border-slate-200 bg-white ${compact ? 'p-3' : 'p-4'}`}
    >
      <div className="border-b border-slate-100 pb-2">
        <h3 className="text-sm font-semibold text-slate-900">{teamName}</h3>
        <p className="mt-0.5 text-xs text-slate-600">
          Modulo <span className="font-mono font-medium">{formation || '—'}</span>
          {statusLabel ? (
            <span className="ml-2 rounded border border-slate-200 bg-slate-50 px-1.5 py-px text-[10px] text-slate-600">
              {statusLabel}
            </span>
          ) : null}
        </p>
      </div>

      <div className="mt-3 flex-1 space-y-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Titolari</p>
          {lines.length === 0 ? (
            <p className="mt-1 text-xs text-slate-500">Nessun titolare salvato.</p>
          ) : (
            <div className="mt-2 space-y-2">
              {lines.map((row, ri) => (
                <div
                  key={ri}
                  className="flex flex-wrap justify-center gap-x-3 gap-y-1 rounded-lg bg-slate-50/80 px-2 py-2"
                >
                  {row.map((p) => (
                    <div key={p.provider_player_id} className="min-w-0">
                      <PlayerLine player={p} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {substitutes.length > 0 ? (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Panchina</p>
            <ul className="mt-1 space-y-1">
              {substitutes.map((p) => (
                <PlayerLine key={p.provider_player_id} player={p} />
              ))}
            </ul>
          </div>
        ) : null}

        {(missingPlayers.injured.length > 0 ||
          missingPlayers.suspended.length > 0 ||
          missingPlayers.other.length > 0) && (
          <div className="border-t border-slate-100 pt-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Indisponibili</p>
            <MissingSection title="Squalificati" players={missingPlayers.suspended} />
            <MissingSection title="Infortunati" players={missingPlayers.injured} />
            <MissingSection title="Altri indisponibili" players={missingPlayers.other} />
          </div>
        )}
      </div>
    </div>
  )
}
