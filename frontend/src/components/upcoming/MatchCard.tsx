import type {
  ModelLimitations,
  UpcomingActiveMatchRow,
} from '../../lib/api'
import { V20_MODEL, labelForModelVersion } from '../../lib/modelVersions'
import { LineupRefreshImpactDetail } from './LineupRefreshImpactDetail'
import { formatKickoff, formatNum, formatSignedNum } from './format'
import { Link } from 'react-router-dom'

function readinessLabel(key: string, value: string): string {
  const labels: Record<string, Record<string, string>> = {
    sportapi_mapping: { ok: 'Mapping OK', missing: 'Mapping assente' },
    lineup_freshness: { ok: 'Lineups OK', stale: 'Lineups datate', missing: 'Lineups assenti' },
    roster_sync: { ok: 'Rosa OK', partial: 'Rosa parziale', missing: 'Rosa non sync' },
    player_mapping: { ok: 'Mapping giocatori OK', partial: 'Mapping parziale' },
    model_v20: { ready: 'v2.0 pronto', partial: 'v2.0 parziale', fallback_v11: 'Fallback v1.1' },
  }
  return labels[key]?.[value] ?? `${key}: ${value}`
}

export function MatchCard({
  match,
}: {
  match: UpcomingActiveMatchRow
  limitations: ModelLimitations
}) {
  const home = match.home_prediction
  const away = match.away_prediction
  const mainHome = home?.expected_sot ?? null
  const mainAway = away?.expected_sot ?? null
  const mainTotal = match.total_expected_sot ?? null
  const isV20 = match.model_version_used === V20_MODEL
  const homeB11 = home?.baseline_v11_expected_sot ?? null
  const awayB11 = away?.baseline_v11_expected_sot ?? null
  const homeDiff = home?.difference_from_v11 ?? null
  const awayDiff = away?.difference_from_v11 ?? null
  const readiness =
    (home?.pre_match_readiness as Record<string, string> | undefined) ??
    (away?.pre_match_readiness as Record<string, string> | undefined)

  return (
    <article
      id={`match-${match.fixture_id}`}
      className="scroll-mt-24 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
    >
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
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-800 ring-1 ring-slate-200">
            Modello: {labelForModelVersion(match.model_version_used)}
          </span>
          {match.tracked_pick_badge ? (
            <span
              title={match.tracked_pick_summary ?? undefined}
              className="rounded-full bg-violet-50 px-2 py-0.5 font-medium text-violet-900 ring-1 ring-violet-200"
            >
              {match.tracked_pick_badge}
            </span>
          ) : null}
        </div>
        {match.tracked_pick_summary ? (
          <p className="mt-1 text-[10px] text-violet-800">{match.tracked_pick_summary}</p>
        ) : null}
        {isV20 && readiness ? (
          <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[10px] text-slate-600">
            {Object.entries(readiness).map(([k, v]) => (
              <span key={k} className="rounded bg-slate-50 px-1.5 py-0.5 ring-1 ring-slate-200">
                {readinessLabel(k, v)}
              </span>
            ))}
          </p>
        ) : null}
      </div>

      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.home_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainHome != null ? formatNum(mainHome) : '—'}
            </p>
            {isV20 && homeB11 != null && homeDiff != null ? (
              homeDiff === 0 ? (
                <p className="mt-1 text-xs text-slate-600">Allineato alla base v1.1.</p>
              ) : (
                <p className="mt-1 text-xs text-slate-600">
                  vs v1.1: {formatNum(homeB11)} <span className="text-slate-500">· Δ {formatSignedNum(homeDiff)}</span>
                </p>
              )
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Totale match</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainTotal != null ? formatNum(mainTotal) : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.away_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainAway != null ? formatNum(mainAway) : '—'}
            </p>
            {isV20 && awayB11 != null && awayDiff != null ? (
              awayDiff === 0 ? (
                <p className="mt-1 text-xs text-slate-600">Allineato alla base v1.1.</p>
              ) : (
                <p className="mt-1 text-xs text-slate-600">
                  vs v1.1: {formatNum(awayB11)} <span className="text-slate-500">· Δ {formatSignedNum(awayDiff)}</span>
                </p>
              )
            ) : null}
          </div>
        </div>
        {isV20 ? (
          <div className="mt-4 rounded-lg border border-violet-100 bg-violet-50/30 px-3 py-3">
            <p className="text-xs font-semibold text-violet-950">
              Variazione dopo ultimo aggiornamento formazioni
            </p>
            <div className="mt-2">
              <LineupRefreshImpactDetail impact={match.lineup_refresh_impact} />
            </div>
          </div>
        ) : null}
        {match.betting_advice_compact ? (
          <div className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50/40 px-3 py-2 text-xs text-slate-800">
            <p className="font-medium text-indigo-950">Consiglio giocata SOT (totale)</p>
            <p className="mt-1 tabular-nums">
              Totale previsto:{' '}
              {match.betting_advice_compact.total_expected_sot != null
                ? formatNum(match.betting_advice_compact.total_expected_sot)
                : '—'}
            </p>
            <p className="mt-0.5">
              Statistica:{' '}
              <span className="font-semibold">{match.betting_advice_compact.statistical_pick ?? '—'}</span>
              {match.betting_advice_compact.statistical_margin != null ? (
                <span className="text-slate-600">
                  {' '}
                  (margine {formatSignedNum(match.betting_advice_compact.statistical_margin)})
                </span>
              ) : null}
            </p>
            <p className="mt-0.5">
              Cauta:{' '}
              <span className="font-semibold">{match.betting_advice_compact.cautious_pick ?? '—'}</span>
            </p>
          </div>
        ) : null}

        <p className="mt-3 text-xs text-slate-600">
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              to={`/match-variable-audit?fixture_id=${match.fixture_id}`}
              className="font-medium text-slate-700 underline"
            >
              {match.betting_advice_compact ? 'Vedi consiglio completo' : 'Vedi consiglio giocata'}
            </Link>
            <Link
              to={`/match-variable-audit?fixture_id=${match.fixture_id}`}
              className="font-medium text-slate-500 underline"
            >
              Audit variabili
            </Link>
            {match.api_fixture_id ? (
              <Link
                to={`/admin?sportapi_fixture=${match.api_fixture_id}`}
                className="font-medium text-slate-700 underline"
              >
                Debug SportAPI
              </Link>
            ) : null}
          </span>
        </p>
      </div>
    </article>
  )
}
