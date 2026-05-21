import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getFixturePlayerProfiles } from '../../lib/api'
import { useSportApiLineupRefresh } from '../../hooks/useSportApiLineupRefresh'
import { V11_MODEL, V20_MODEL } from '../../lib/modelVersions'
import {
  formatSportApiFetchedAt,
  freshnessBadgeClass,
  getSportApiFreshnessBadge,
} from '../../utils/sportApiLineupMeta'
import type { LineupImpactSimulationPayload } from '../../types/lineupImpact'
import type { PlayerDbProfileRow } from '../../types/playerDbProfiles'
import type { SportApiLineupsAuditPayload, SportApiLineupsStoredResponse } from '../../types/sportapi'
import { SportApiLineupSide } from './SportApiLineupSide'

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
  fixtureId,
  kickoffAt,
  activeModelVersion,
  lineupImpact,
  onDataRefresh,
  regenerateV20AfterFetch = false,
}: {
  data: SportApiLineupsAuditPayload | null | undefined
  compact?: boolean
  apiFixtureId?: number | null
  fixtureId?: number | null
  kickoffAt?: string | null
  activeModelVersion?: string | null
  lineupImpact?: LineupImpactSimulationPayload | null
  onDataRefresh?: () => void | Promise<void>
  regenerateV20AfterFetch?: boolean
}) {
  const confirmed = data?.confirmed
  const available = data?.available === true

  const [homeProfiles, setHomeProfiles] = useState<PlayerDbProfileRow[]>([])
  const [awayProfiles, setAwayProfiles] = useState<PlayerDbProfileRow[]>([])
  const [profilesLoading, setProfilesLoading] = useState(false)

  useEffect(() => {
    if (!available || !fixtureId) {
      setHomeProfiles([])
      setAwayProfiles([])
      return
    }
    let cancelled = false
    const load = async () => {
      setProfilesLoading(true)
      try {
        const res = await getFixturePlayerProfiles(fixtureId, { limit: 'all' })
        if (cancelled || res.status !== 'success') return
        setHomeProfiles(res.home?.players ?? [])
        setAwayProfiles(res.away?.players ?? [])
      } catch {
        if (!cancelled) {
          setHomeProfiles([])
          setAwayProfiles([])
        }
      } finally {
        if (!cancelled) setProfilesLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [available, fixtureId])

  const modelBadge = (() => {
    if (!available) return null
    if (activeModelVersion === V20_MODEL) {
      return (
        <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-900">
          Dati usati dal modello v2.0
        </span>
      )
    }
    if (activeModelVersion === V11_MODEL) {
      return (
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
          Dati disponibili, non usati da v1.1
        </span>
      )
    }
    return (
      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
        Dati disponibili per analisi pre-match
      </span>
    )
  })()

  const refresh = useSportApiLineupRefresh({
    fixtureId,
    regenerateV20: regenerateV20AfterFetch,
    onDataRefresh,
  })

  const formattedFetchedAt = formatSportApiFetchedAt(data?.fetched_at)
  const freshness = getSportApiFreshnessBadge(data?.fetched_at, kickoffAt)

  const matching = lineupImpact?.sportapi_player_matching
  const meta = {
    confirmed,
    confidenceScore: data?.confidence_score,
    fetchedAt: data?.fetched_at,
    profilesMissing: lineupImpact?.profiles_missing,
  }

  return (
    <section
      className={`overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm ${compact ? '' : ''}`}
    >
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">
            SportAPI — Formazioni e indisponibili
          </h2>
          {modelBadge}
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
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {formattedFetchedAt ? (
            <span className="text-[11px] text-slate-600">
              Ultimo aggiornamento: <span className="font-medium text-slate-800">{formattedFetchedAt}</span>
            </span>
          ) : (
            <span className="text-[11px] text-slate-500">Nessun aggiornamento SportAPI registrato</span>
          )}
          {freshness ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${freshnessBadgeClass(freshness.level)}`}
            >
              {freshness.label}
            </span>
          ) : null}
          {fixtureId != null && onDataRefresh ? (
            <button
              type="button"
              disabled={refresh.busy || !available}
              onClick={() => void refresh.runRefresh()}
              className="rounded-md border border-violet-300 bg-white px-2 py-1 text-[10px] font-medium text-violet-900 hover:bg-violet-50 disabled:opacity-50"
            >
              {refresh.buttonLabel}
            </button>
          ) : null}
        </div>
        {fixtureId != null && onDataRefresh ? (
          <p className="mt-1 text-[10px] text-slate-500">Consuma 1 chiamata SportAPI</p>
        ) : null}
        {refresh.successMessage ? (
          <p className="mt-1 text-[10px] text-emerald-800">{refresh.successMessage}</p>
        ) : null}
        {refresh.error ? <p className="mt-1 text-[10px] text-rose-700">{refresh.error}</p> : null}
        {data?.fetched_at && (data.provider_event_id != null || profilesLoading) ? (
          <p className="mt-0.5 text-[10px] text-slate-500">
            {data.provider_event_id != null ? `event_id ${data.provider_event_id}` : ''}
            {profilesLoading ? ' · profili in caricamento…' : ''}
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
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:items-start">
            <SportApiLineupSide
              side={data.home}
              lineupSide={lineupImpact?.home}
              matching={matching}
              profiles={homeProfiles}
              meta={meta}
            />
            <SportApiLineupSide
              side={data.away}
              lineupSide={lineupImpact?.away}
              matching={matching}
              profiles={awayProfiles}
              meta={meta}
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
