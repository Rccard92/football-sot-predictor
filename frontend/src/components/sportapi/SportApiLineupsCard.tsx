import { Link } from 'react-router-dom'
import type { SportApiLineupsAuditPayload, SportApiLineupsStoredResponse } from '../../types/sportapi'
import { SportApiLineupBoard } from './SportApiLineupBoard'

const EMPTY_MISSING = { injured: [], suspended: [], other: [] }

function emptySide(name: string) {
  return {
    team_name: name,
    formation: null,
    confirmed: null,
    starters: [],
    substitutes: [],
    tactical_lines: [],
    missing_players: EMPTY_MISSING,
  }
}

export function SportApiLineupsCard({
  data,
  compact = false,
  apiFixtureId,
}: {
  data: SportApiLineupsAuditPayload | null | undefined
  compact?: boolean
  /** Link Admin pre-fill quando dati assenti */
  apiFixtureId?: number | null
}) {
  const confirmed = data?.confirmed
  const available = data?.available === true

  return (
    <section
      className={`overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm ${compact ? '' : ''}`}
    >
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">
            SportAPI — Formazioni e indisponibili
          </h2>
          <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-900">
            Dati non usati nel modello
          </span>
          {available && confirmed === true ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
              Formazioni ufficiali
            </span>
          ) : null}
          {available && confirmed === false ? (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-950">
              Formazioni probabili
            </span>
          ) : null}
        </div>
        {data?.fetched_at ? (
          <p className="mt-1 text-[11px] text-slate-600">
            Ultimo import: {data.fetched_at}
            {data.provider_event_id != null ? ` · event_id ${data.provider_event_id}` : ''}
            {data.confidence_score != null ? ` · mapping ${data.confidence_score}` : ''}
          </p>
        ) : null}
      </div>

      <div className={compact ? 'p-3' : 'p-4'}>
        {!available ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/50 px-3 py-4 text-xs text-slate-600">
            <p>Nessun dato SportAPI importato per questa partita.</p>
            <p className="mt-1">
              Import manuale da Admin → SportAPI Debug (mapping + «Importa lineups»).
            </p>
            {apiFixtureId ? (
              <p className="mt-2">
                <Link
                  to={`/admin?sportapi_fixture=${apiFixtureId}`}
                  className="font-medium text-slate-800 underline"
                >
                  Apri SportAPI Debug
                </Link>
              </p>
            ) : null}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:items-stretch">
            <SportApiLineupBoard
              teamName={data.home.team_name}
              formation={data.home.formation}
              confirmed={confirmed}
              starters={data.home.starters}
              substitutes={data.home.substitutes}
              missingPlayers={data.home.missing_players}
              tacticalLines={data.home.tactical_lines}
              compact={compact}
            />
            <SportApiLineupBoard
              teamName={data.away.team_name}
              formation={data.away.formation}
              confirmed={confirmed}
              starters={data.away.starters}
              substitutes={data.away.substitutes}
              missingPlayers={data.away.missing_players}
              tacticalLines={data.away.tactical_lines}
              compact={compact}
            />
          </div>
        )}
      </div>
    </section>
  )
}

/** Adatta risposta admin lineups (può mancare campi se DB vuoto). */
export function sportApiLineupsFromStored(
  stored: SportApiLineupsStoredResponse | SportApiLineupsAuditPayload | null | undefined,
  homeName: string,
  awayName: string,
): SportApiLineupsAuditPayload {
  if (!stored) {
    return {
      available: false,
      home: emptySide(homeName),
      away: emptySide(awayName),
    }
  }
  const home = stored.home ?? emptySide(homeName)
  const away = stored.away ?? emptySide(awayName)
  return {
    available: stored.available ?? false,
    provider_event_id: stored.provider_event_id,
    confidence_score: stored.confidence_score,
    confirmed: stored.confirmed,
    fetched_at: stored.fetched_at,
    home: {
      ...home,
      team_name: home.team_name || homeName,
      missing_players: home.missing_players ?? EMPTY_MISSING,
      starters: home.starters ?? [],
      substitutes: home.substitutes ?? [],
    },
    away: {
      ...away,
      team_name: away.team_name || awayName,
      missing_players: away.missing_players ?? EMPTY_MISSING,
      starters: away.starters ?? [],
      substitutes: away.substitutes ?? [],
    },
  }
}
