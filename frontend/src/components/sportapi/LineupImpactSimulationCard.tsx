import { useCallback, useState } from 'react'
import { fetchSportApiLineups, syncSportApiFixtureSquads } from '../../lib/api'
import type {
  LineupImpactDefensivePlayer,
  LineupImpactExcludedPlayer,
  LineupImpactSimulationPayload,
  LineupImpactSideSimulation,
  LineupImpactTopPlayer,
  PlayerLineupStatus,
} from '../../types/lineupImpact'
import { SportApiPlayerMatchingPanel } from './SportApiPlayerMatchingPanel'

function statusLabelIT(status: PlayerLineupStatus): string {
  switch (status) {
    case 'STARTER':
      return 'Titolare'
    case 'BENCH':
      return 'Panchina'
    case 'MISSING':
      return 'Indisponibile'
    case 'OUT_OF_LINEUP':
      return 'Fuori lista'
    case 'UNMAPPED':
      return 'Non mappato'
    default:
      return status
  }
}

function statusBadgeClass(status: PlayerLineupStatus): string {
  switch (status) {
    case 'STARTER':
      return 'border-emerald-200 bg-emerald-50 text-emerald-900'
    case 'BENCH':
      return 'border-amber-200 bg-amber-50 text-amber-950'
    case 'MISSING':
      return 'border-rose-200 bg-rose-50 text-rose-900'
    case 'OUT_OF_LINEUP':
      return 'border-orange-200 bg-orange-50 text-orange-950'
    case 'UNMAPPED':
      return 'border-slate-200 bg-slate-100 text-slate-700'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-800'
  }
}

function confidenceBadgeClass(label: string | undefined): string {
  switch (label) {
    case 'alta':
      return 'border-emerald-200 bg-emerald-50 text-emerald-900'
    case 'media':
      return 'border-amber-200 bg-amber-50 text-amber-950'
    case 'bassa':
      return 'border-rose-200 bg-rose-50 text-rose-900'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-700'
  }
}

function rosterHintLabel(hint: string | undefined): string {
  if (hint === 'missing') return 'Rosa API-Sports non sincronizzata'
  if (hint === 'stale') return 'Rosa API-Sports obsoleta/vuota'
  return 'Rosa API-Sports aggiornata'
}

function TopPlayerRow({ player, index }: { player: LineupImpactTopPlayer; index: number }) {
  const share = player.team_sot_share_pct
  return (
    <li className="flex flex-wrap items-start gap-2 border-b border-slate-100 py-2 last:border-0">
      <span className="w-5 shrink-0 font-mono text-xs text-slate-400">{index + 1}.</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-900">{player.player_name}</span>
          {share != null ? (
            <span className="font-mono text-[11px] text-slate-600">{share.toFixed(1)}%</span>
          ) : null}
          <span
            className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${statusBadgeClass(player.status)}`}
          >
            {statusLabelIT(player.status)}
          </span>
        </div>
        {player.status_note ? (
          <p className="mt-0.5 text-[10px] text-slate-500">{player.status_note}</p>
        ) : null}
        {player.replacement_player_name && (player.replacement_credit ?? 0) > 0 ? (
          <p className="mt-0.5 text-[10px] text-indigo-700">
            Compensazione: {player.replacement_player_name} (−
            {((player.replacement_credit ?? 0) * 100).toFixed(1)}% share)
          </p>
        ) : null}
      </div>
    </li>
  )
}

function DefensivePlayerRow({ player }: { player: LineupImpactDefensivePlayer }) {
  const imp = (player.defensive_importance ?? 0) * 100
  return (
    <li className="border-b border-slate-100 py-1.5 text-xs last:border-0">
      <span className="font-medium text-slate-900">{player.player_name}</span>
      {imp > 0 ? (
        <span className="ml-2 font-mono text-[10px] text-slate-600">
          imp. {imp.toFixed(0)}%
        </span>
      ) : null}
      {player.status ? (
        <span
          className={`ml-2 rounded border px-1 py-0.5 text-[10px] ${statusBadgeClass(player.status)}`}
        >
          {statusLabelIT(player.status)}
        </span>
      ) : null}
      {(player.net_defensive_loss ?? 0) > 0 ? (
        <p className="mt-0.5 text-[10px] text-orange-800">
          Perdita difensiva netta: {((player.net_defensive_loss ?? 0) * 100).toFixed(1)}%
          {player.replacement_player_name
            ? ` — compensata da ${player.replacement_player_name}`
            : ''}
        </p>
      ) : null}
    </li>
  )
}

function ExcludedRow({ player }: { player: LineupImpactExcludedPlayer }) {
  return (
    <li className="text-xs text-slate-700">
      <span className="font-medium">{player.player_name}</span>
      {player.team_sot_share_pct != null ? (
        <span className="font-mono text-slate-500"> — share {player.team_sot_share_pct.toFixed(1)}%</span>
      ) : null}
      <span className="text-slate-500">
        {' '}
        — escluso: {player.exclusion_reason ?? 'non più in rosa attuale'}
      </span>
    </li>
  )
}

function SideImpactBlock({ side }: { side: LineupImpactSideSimulation }) {
  const base = side.base_sot ?? side.base_expected_sot
  const adj = side.adjusted_sot ?? side.adjusted_sot_simulated
  const pct = side.impact_pct
  const offFactor = side.offensive_lineup_factor ?? side.attacking_lineup_factor
  const oppDef = side.opponent_defensive_weakness_factor ?? 1
  const finalFactor = side.factor ?? (offFactor != null ? offFactor * oppDef : undefined)
  const topPlayers = side.top_sot_players ?? side.top5_sot_players ?? []
  const defPlayers = side.defensive_key_players ?? []
  const excluded = side.excluded_players ?? []

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
      {side.formation ? (
        <p className="text-xs text-slate-600">
          Modulo <span className="font-mono">{side.formation}</span>
        </p>
      ) : null}
      {side.roster_sync_hint ? (
        <p
          className={`mt-1 text-[10px] ${side.roster_sync_hint === 'ok' ? 'text-emerald-800' : 'text-amber-800'}`}
        >
          {rosterHintLabel(side.roster_sync_hint)}
        </p>
      ) : null}

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-slate-500">Base SOT</dt>
        <dd className="font-mono font-medium">{base != null ? base.toFixed(1) : '—'}</dd>
        <dt className="text-slate-500">Adjusted simulato</dt>
        <dd className="font-mono font-medium text-indigo-800">
          {adj != null ? adj.toFixed(1) : '—'}
        </dd>
        <dt className="text-slate-500">Impatto</dt>
        <dd className={pct != null && pct < 0 ? 'text-rose-700' : 'text-emerald-800'}>
          {pct != null ? `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
        </dd>
        <dt className="text-slate-500">Offensive factor</dt>
        <dd className="font-mono">{offFactor != null ? offFactor.toFixed(4) : '—'}</dd>
        <dt className="text-slate-500">Opp. defensive weakness</dt>
        <dd className="font-mono text-orange-800">{oppDef.toFixed(4)}</dd>
        <dt className="text-slate-500">Factor finale</dt>
        <dd className="font-mono font-semibold">
          {finalFactor != null ? finalFactor.toFixed(4) : '—'}
        </dd>
      </dl>

      <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-50/50 px-2 py-2 text-[10px]">
        <p className="font-semibold uppercase text-indigo-800">Impatto offensivo</p>
        <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5">
          <dt className="text-slate-500">Gross penalty</dt>
          <dd className="font-mono">
            {side.gross_penalty_share != null
              ? `${(side.gross_penalty_share * 100).toFixed(1)}%`
              : '—'}
          </dd>
          <dt className="text-slate-500">Replacement credit</dt>
          <dd className="font-mono text-emerald-800">
            {side.replacement_credit_share != null
              ? `${(side.replacement_credit_share * 100).toFixed(1)}%`
              : '—'}
          </dd>
          <dt className="text-slate-500">Net loss</dt>
          <dd className="font-mono text-rose-800">
            {side.net_lineup_loss_share != null
              ? `${(side.net_lineup_loss_share * 100).toFixed(1)}%`
              : '—'}
          </dd>
        </dl>
      </div>

      <div className="mt-2 rounded-lg border border-orange-100 bg-orange-50/40 px-2 py-2 text-[10px]">
        <p className="font-semibold uppercase text-orange-900">Impatto difensivo (concessione avversario)</p>
        <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5">
          <dt className="text-slate-500">Weakness factor (nostro)</dt>
          <dd className="font-mono">
            {(side.defensive_weakness_factor ?? 1).toFixed(4)}
          </dd>
          <dt className="text-slate-500">Net defensive loss</dt>
          <dd className="font-mono">
            {side.net_defensive_loss != null
              ? `${(side.net_defensive_loss * 100).toFixed(1)}%`
              : '—'}
          </dd>
        </dl>
        {defPlayers.length > 0 ? (
          <ul className="mt-2 list-none space-y-0">
            {defPlayers.map((p, i) => (
              <DefensivePlayerRow key={p.player_id ?? i} player={p} />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-slate-500">Nessun difensore chiave penalizzato</p>
        )}
      </div>

      {topPlayers.length > 0 ? (
        <div className="mt-3">
          <p className="text-[10px] font-semibold uppercase text-slate-500">
            Top 5 SOT — Stato giocatori
          </p>
          <ol className="mt-1 list-none">
            {topPlayers.map((p, i) => (
              <TopPlayerRow key={p.player_id ?? i} player={p} index={i} />
            ))}
          </ol>
        </div>
      ) : null}

      {excluded.length > 0 ? (
        <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-2 py-2">
          <p className="text-[10px] font-semibold uppercase text-slate-500">
            Giocatori esclusi dal calcolo
          </p>
          <ul className="mt-1 list-inside list-disc">
            {excluded.map((ex, i) => (
              <ExcludedRow key={i} player={ex} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export function LineupImpactSimulationCard({
  data,
  showMatching = true,
  fixtureId,
  onDataRefresh,
}: {
  data: LineupImpactSimulationPayload | null | undefined
  showMatching?: boolean
  fixtureId?: number
  onDataRefresh?: () => void | Promise<void>
}) {
  const [syncLoading, setSyncLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)

  const effectiveFixtureId = fixtureId ?? data?.fixture_id
  const rosterMissing =
    data?.roster_filter_active === false ||
    data?.home?.roster_sync_hint === 'missing' ||
    data?.away?.roster_sync_hint === 'missing' ||
    data?.home?.roster_sync_hint === 'stale' ||
    data?.away?.roster_sync_hint === 'stale'

  const runSyncSquads = useCallback(async () => {
    const fid = effectiveFixtureId
    if (fid == null) return
    setSyncLoading(true)
    setSyncError(null)
    try {
      await syncSportApiFixtureSquads(fid)
      await onDataRefresh?.()
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : String(e))
    } finally {
      setSyncLoading(false)
    }
  }, [effectiveFixtureId, onDataRefresh])

  const runFetchLineups = useCallback(async () => {
    const fid = effectiveFixtureId
    if (fid == null) return
    if (!window.confirm('Aggiorna formazione SportAPI? Consuma 1 chiamata SportAPI.')) return
    setFetchLoading(true)
    setSyncError(null)
    try {
      await fetchSportApiLineups(fid)
      await onDataRefresh?.()
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : String(e))
    } finally {
      setFetchLoading(false)
    }
  }, [effectiveFixtureId, onDataRefresh])

  if (!data || data.status === 'error') {
    return null
  }

  const noLineups = !data.sportapi_lineups_available && data.status === 'no_lineups'

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">
            Lineup Impact — Simulazione SOT
          </h2>
          <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-900">
            Simulazione — non usata nel modello
          </span>
          {data.confidence_label ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${confidenceBadgeClass(data.confidence_label)}`}
            >
              Confidence: {data.confidence_label}
            </span>
          ) : null}
          {data.confirmed === true ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
              Peso ufficiale 100%
            </span>
          ) : (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-950">
              Peso probabile 60%
            </span>
          )}
        </div>
        {data.profiles_missing ? (
          <p className="mt-1 text-[11px] text-amber-800">
            Profili player_sot_profiles assenti per questa stagione — eseguire build profili da Admin.
          </p>
        ) : null}
        {effectiveFixtureId != null ? (
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={fetchLoading || syncLoading}
              onClick={() => void runFetchLineups()}
              className="rounded-md border border-violet-300 bg-white px-2 py-1 text-[10px] font-medium text-violet-900 hover:bg-violet-50 disabled:opacity-50"
            >
              {fetchLoading ? 'Fetch…' : 'Aggiorna formazione SportAPI'}
            </button>
            <button
              type="button"
              disabled={syncLoading || fetchLoading}
              onClick={() => void runSyncSquads()}
              className="rounded-md border border-amber-300 bg-white px-2 py-1 text-[10px] font-medium text-amber-950 hover:bg-amber-100 disabled:opacity-50"
            >
              {syncLoading ? 'Sincronizzazione…' : 'Aggiorna rosa attuale API-Sports'}
            </button>
          </div>
        ) : null}
        {syncError ? <p className="mt-1 text-[11px] text-rose-700">{syncError}</p> : null}
        {rosterMissing ? (
          <p className="mt-2 text-[11px] text-amber-950">
            Rosa attuale non aggiornata: il filtro giocatori trasferiti potrebbe non essere attivo.
          </p>
        ) : null}
        {(data.confidence_reasons?.length ?? 0) > 0 ? (
          <ul className="mt-2 list-inside list-disc text-[11px] text-slate-600">
            {data.confidence_reasons!.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="space-y-4 p-4">
        {noLineups ? (
          <p className="text-xs text-slate-600">
            Nessuna lineup SportAPI importata. La simulazione richiede dati da Admin → SportAPI Debug.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <SideImpactBlock side={data.home} />
              <SideImpactBlock side={data.away} />
            </div>

            {(data.explanation_bullets?.length ?? 0) > 0 ? (
              <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                <p className="text-[10px] font-semibold uppercase text-slate-500">Motivi</p>
                <ul className="mt-1 list-inside list-disc text-xs text-slate-700">
                  {data.explanation_bullets!.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}

        {showMatching && (data.sportapi_player_matching?.length ?? 0) > 0 ? (
          <SportApiPlayerMatchingPanel matches={data.sportapi_player_matching!} compact />
        ) : null}
      </div>
    </section>
  )
}
