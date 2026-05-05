import type {
  ModelLimitations,
  UpcomingMatchRow,
  UpcomingPlayerAdjustedMatchRow,
} from '../../lib/api'
import { formatKickoff, formatNum } from './format'
import { BreakdownTable } from './BreakdownTable'
import { MatchDebugLayers } from './MatchDebugLayers'

export function MatchCard({
  match,
  limitations,
  playerAdjustedMatch,
  usePlayerAdjustedView,
}: {
  match: UpcomingMatchRow
  limitations: ModelLimitations
  playerAdjustedMatch: UpcomingPlayerAdjustedMatchRow | null
  usePlayerAdjustedView: boolean
}) {
  const hp = match.home_prediction
  const ap = match.away_prediction
  const matchCtx = (match.match_context ?? {}) as Record<string, unknown>
  const homeCtx = (match.home_team_context ?? {}) as Record<string, unknown>
  const awayCtx = (match.away_team_context ?? {}) as Record<string, unknown>
  const riskFlags = Array.isArray(matchCtx.risk_flags) ? (matchCtx.risk_flags as unknown[]) : []
  const homePA = playerAdjustedMatch?.home ?? null
  const awayPA = playerAdjustedMatch?.away ?? null
  const totalAdjusted = playerAdjustedMatch?.total_expected_sot_adjusted ?? null
  const totalBaseline = playerAdjustedMatch?.total_expected_sot_baseline ?? null

  const showPlayerAdjusted = usePlayerAdjustedView && homePA && awayPA
  const mainHome = showPlayerAdjusted ? homePA.adjusted_expected_sot : hp?.expected_sot ?? null
  const mainAway = showPlayerAdjusted ? awayPA.adjusted_expected_sot : ap?.expected_sot ?? null
  const mainTotal =
    showPlayerAdjusted && totalAdjusted != null
      ? totalAdjusted
      : match.total_expected_sot != null
        ? match.total_expected_sot
        : null

  let insight = 'Previsione stabile, nessun warning rilevante.'
  if (match.context_status === 'not_available') {
    insight = 'Classifica non disponibile: contesto motivazionale non calcolabile.'
  } else if (riskFlags.includes('fine_stagione')) {
    insight = 'Partita di fine stagione: previsione da leggere con prudenza.'
  } else if (riskFlags.length > 0) {
    insight = 'Warning contesto presenti: leggere la previsione con prudenza.'
  }

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {match.round ?? 'Giornata'}
          </p>
          <span className="rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-100">
            Pre-partita
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-600">{formatKickoff(match.kickoff_at)}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            {match.home_team.logo_url ? (
              <img src={match.home_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.home_team.name}</span>
          </div>
          <span className="text-slate-400">vs</span>
          <div className="flex items-center gap-2">
            {match.away_team.logo_url ? (
              <img src={match.away_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.away_team.name}</span>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {riskFlags.includes('fine_stagione') ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Fine stagione
            </span>
          ) : null}
          {homeCtx.turnover_risk === 'alto' || awayCtx.turnover_risk === 'alto' ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Rischio turnover
            </span>
          ) : null}
          {riskFlags.length > 0 && !riskFlags.includes('fine_stagione') ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Contesto prudente
            </span>
          ) : null}
        </div>
      </div>

      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.home_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainHome != null ? formatNum(mainHome) : '—'}
            </p>
            {homePA ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(homePA.baseline_expected_sot)} · Player impact{' '}
                {formatNum(homePA.player_adjustment)}
              </p>
            ) : hp ? (
              <p className="mt-1 text-xs text-slate-600">Baseline {formatNum(hp.expected_sot)}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Totale match</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainTotal != null ? formatNum(mainTotal) : '—'}
            </p>
            {totalBaseline != null && totalAdjusted != null ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(totalBaseline)} · v0.2 {formatNum(totalAdjusted)}
                <span className="text-slate-500">
                  {' '}
                  · Δ {formatNum(totalAdjusted - totalBaseline)}
                </span>
              </p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.away_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainAway != null ? formatNum(mainAway) : '—'}
            </p>
            {awayPA ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(awayPA.baseline_expected_sot)} · Player impact{' '}
                {formatNum(awayPA.player_adjustment)}
              </p>
            ) : ap ? (
              <p className="mt-1 text-xs text-slate-600">Baseline {formatNum(ap.expected_sot)}</p>
            ) : null}
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-700">{insight}</p>
      </div>

      <div className="border-t border-slate-100 px-5 py-4 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Perché è cambiata?
              <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
              <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
            </span>
          </summary>
          {homePA && awayPA ? (
            <div className="space-y-2 border-t border-slate-200 px-4 py-4 text-sm text-slate-700">
              <p>
                {match.home_team.name}: Baseline {formatNum(homePA.baseline_expected_sot)} · Aggiustata{' '}
                {formatNum(homePA.adjusted_expected_sot)} · Player impact {formatNum(homePA.player_adjustment)}
              </p>
              <p>
                {match.away_team.name}: Baseline {formatNum(awayPA.baseline_expected_sot)} · Aggiustata{' '}
                {formatNum(awayPA.adjusted_expected_sot)} · Player impact {formatNum(awayPA.player_adjustment)}
              </p>
              <p className="text-xs text-slate-600">
                Totale match Baseline: {totalBaseline != null ? formatNum(totalBaseline) : '—'} · Totale match v0.2:{' '}
                {totalAdjusted != null ? formatNum(totalAdjusted) : '—'}
              </p>
            </div>
          ) : (
            <div className="border-t border-slate-200 px-4 py-4 text-sm text-slate-600">
              <p>Correzione v0.2 non disponibile per questa partita.</p>
            </div>
          )}
        </details>
      </div>

      <div className="border-t border-slate-100 px-5 pb-5 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Dettaglio matematico baseline
              <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
              <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
            </span>
          </summary>
          <div className="space-y-6 border-t border-slate-200 px-4 py-4">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{match.home_team.name}</p>
              <BreakdownTable teamName={match.home_team.name} breakdown={hp?.calculation_breakdown} />
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{match.away_team.name}</p>
              <BreakdownTable teamName={match.away_team.name} breakdown={ap?.calculation_breakdown} />
            </div>
          </div>
        </details>
      </div>
      <MatchDebugLayers match={match} playerAdjustedMatch={playerAdjustedMatch} usePlayerAdjustedView={usePlayerAdjustedView} />
      <p className="border-t border-slate-100 px-5 py-3 text-xs leading-relaxed text-slate-500 sm:px-6">
        {limitations.note}
      </p>
    </article>
  )
}

