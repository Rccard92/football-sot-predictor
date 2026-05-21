import type { LineupImpactSideSimulation } from '../../types/lineupImpact'
import type { ExplanationFixture, SideSummary } from '../../types/sotExplanation'
import { V20_MODEL } from '../../lib/modelVersions'

function fmtNum(v: number | null | undefined, d = 3): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(d)
}

function product3(a: number | null, b: number | null, c: number | null): number | null {
  if (a == null || b == null || c == null) return null
  return Math.round(a * b * c * 1000) / 1000
}

function readBaseV11(side: LineupImpactSideSimulation | undefined): number | null {
  const fromLi = side?.base_sot ?? side?.base_expected_sot
  if (fromLi != null && !Number.isNaN(Number(fromLi))) return Number(fromLi)
  return null
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    STARTER: 'Titolare',
    BENCH: 'Panchina',
    MISSING: 'Indisponibile',
    OUT_OF_LINEUP: 'Fuori lista',
    UNMAPPED: 'Non mappato',
  }
  return map[status] ?? status
}

function TopPlayersTable({
  teamName,
  side,
}: {
  teamName: string
  side: LineupImpactSideSimulation | undefined
}) {
  const players = side?.top_sot_players ?? side?.top5_sot_players ?? []
  if (!players.length) {
    return (
      <p className="text-[11px] text-slate-500">
        Nessun top shooter nel payload Lineup Impact per {teamName}.
      </p>
    )
  }

  return (
    <div>
      <p className="mb-1.5 text-[10px] font-semibold uppercase text-slate-500">{teamName} — Top shooter</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-[10px] text-slate-800">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-1 pr-2 font-medium">Giocatore</th>
              <th className="py-1 pr-2 font-medium">Status</th>
              <th className="py-1 pr-2 font-medium">Quota SOT</th>
              <th className="py-1 pr-2 font-medium">Penalità</th>
              <th className="py-1 pr-2 font-medium">Sostituto</th>
            </tr>
          </thead>
          <tbody>
            {players.slice(0, 5).map((p, i) => (
              <tr key={`${p.player_id ?? i}-${p.sportapi_player_id ?? ''}`} className="border-b border-slate-100">
                <td className="max-w-[8rem] truncate py-1 pr-2 font-medium" title={p.player_name}>
                  {p.player_name ?? '—'}
                </td>
                <td className="py-1 pr-2">{statusLabel(p.status)}</td>
                <td className="py-1 pr-2 tabular-nums">
                  {p.team_sot_share_pct != null ? `${fmtNum(p.team_sot_share_pct, 1)}%` : '—'}
                </td>
                <td className="py-1 pr-2 tabular-nums">{fmtNum(p.penalty_share, 3)}</td>
                <td className="max-w-[6rem] truncate py-1 pr-2" title={p.replacement_player_name ?? ''}>
                  {p.replacement_player_name ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function V20LineupImpactBreakdown({
  fixture: _fixture,
  homeSummary,
  awaySummary,
  lineupImpact,
  sportapiFetchedAt,
  activeModelVersion,
}: {
  fixture: ExplanationFixture
  homeSummary: SideSummary
  awaySummary: SideSummary
  lineupImpact: import('../../types/lineupImpact').LineupImpactSimulationPayload | null | undefined
  sportapiFetchedAt?: string | null
  activeModelVersion?: string | null
}) {
  if (activeModelVersion !== V20_MODEL) return null

  const homeLi = lineupImpact?.home
  const awayLi = lineupImpact?.away

  const homeBase = readBaseV11(homeLi)
  const awayBase = readBaseV11(awayLi)

  const homeOff = homeLi?.offensive_lineup_factor ?? homeLi?.attacking_lineup_factor ?? null
  const awayOff = awayLi?.offensive_lineup_factor ?? awayLi?.attacking_lineup_factor ?? null
  const homeOppDef = homeLi?.opponent_defensive_weakness_factor ?? null
  const awayOppDef = awayLi?.opponent_defensive_weakness_factor ?? null

  const homeV2 = product3(homeBase, homeOff, homeOppDef) ?? homeSummary.predicted_sot
  const awayV2 = product3(awayBase, awayOff, awayOppDef) ?? awaySummary.predicted_sot

  return (
    <section className="overflow-hidden rounded-2xl border border-indigo-200/80 bg-indigo-50/30 shadow-sm">
      <div className="border-b border-indigo-100 bg-indigo-50/60 px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight text-indigo-950">Modello v2.0 — Lineup Impact</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-indigo-900/90">
          Il modello v2.0 usa la forza della formazione attuale importata da SportAPI. Se la formazione viene
          aggiornata, i fattori e la previsione possono cambiare.
        </p>
        {sportapiFetchedAt ? (
          <p className="mt-1 text-[10px] text-slate-600">SportAPI import: {sportapiFetchedAt}</p>
        ) : null}
      </div>

      <div className="space-y-4 p-4">
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <th className="px-3 py-2 font-medium">Voce</th>
                <th className="px-3 py-2 font-medium">{homeSummary.team_name}</th>
                <th className="px-3 py-2 font-medium">{awaySummary.team_name}</th>
              </tr>
            </thead>
            <tbody className="text-slate-800">
              <tr className="border-b border-slate-100">
                <td className="px-3 py-2 font-medium">Base v1.1 SOT</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(homeBase)}</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(awayBase)}</td>
              </tr>
              <tr className="border-b border-slate-100">
                <td className="px-3 py-2 font-medium">offensive_lineup_factor</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(homeOff)}</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(awayOff)}</td>
              </tr>
              <tr className="border-b border-slate-100">
                <td className="px-3 py-2 font-medium">opponent_defensive_weakness_factor</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(homeOppDef)}</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(awayOppDef)}</td>
              </tr>
              <tr className="bg-indigo-50/50 font-semibold">
                <td className="px-3 py-2">Previsione v2.0</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(homeV2)}</td>
                <td className="px-3 py-2 tabular-nums">{fmtNum(awayV2)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-[10px] leading-relaxed text-slate-800">
          <p>
            <span className="font-semibold text-slate-900">Casa:</span> v2 = base v1.1 ({fmtNum(homeBase)}) × offensive (
            {fmtNum(homeOff)}) × debolezza dif. avversario ({fmtNum(homeOppDef)}) = {fmtNum(homeV2)}
          </p>
          <p className="mt-1">
            <span className="font-semibold text-slate-900">Trasferta:</span> v2 = base v1.1 ({fmtNum(awayBase)}) × offensive (
            {fmtNum(awayOff)}) × debolezza dif. avversario ({fmtNum(awayOppDef)}) = {fmtNum(awayV2)}
          </p>
        </div>

        <p className="text-[11px] text-slate-600">
          I Top 5 sono riferimento stagionale SOT (profili API-Sports + filtro rosa attuale). La rosa completa non entra
          direttamente nel moltiplicatore: contano status lineup (titolare / panchina / assente) e compensazioni da
          sostituti SportAPI.
        </p>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <TopPlayersTable teamName={homeSummary.team_name} side={homeLi} />
          <TopPlayersTable teamName={awaySummary.team_name} side={awayLi} />
        </div>

        {lineupImpact?.status === 'no_lineups' ? (
          <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
            Lineup Impact non disponibile: la previsione v2.0 può coincidere con v1.1 (fallback).
          </p>
        ) : null}
      </div>
    </section>
  )
}
