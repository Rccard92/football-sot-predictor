import type { UpcomingActiveMatchRow } from '../../lib/api'
import { formatKickoffReport } from '../../utils/sportApiLineupMeta'
import {
  AFFIDABILITA_HELP,
  confidenceBadgeClass,
  formationBadgeClass,
  formationStatusTooltip,
  pickShortLabel,
  riskBadgeClass,
} from '../../utils/bettingAdviceDisplay'
import { LineupRefreshImpactBadge } from './LineupRefreshImpactBadge'
import { formatNum } from './format'

export function QuickPlayReportMobile({
  matches,
  onOpenDetail,
  selectedFixtureId,
}: {
  matches: UpcomingActiveMatchRow[]
  onOpenDetail?: (fixtureId: number) => void
  selectedFixtureId?: number | null
}) {
  return (
    <div className="space-y-3 md:hidden">
      {matches.map((m) => {
        const market = m.markets?.[0]
        const formLabel = m.lineup_status?.label
        const formTip = formationStatusTooltip(formLabel)
        return (
          <article
            key={m.fixture_id}
            className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
          >
            <p className="text-[10px] font-medium text-slate-500">{formatKickoffReport(m.kickoff_at)}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm font-semibold text-slate-900">
              {m.home_team.logo_url ? (
                <img src={m.home_team.logo_url} alt="" className="h-5 w-5 object-contain" />
              ) : null}
              {m.home_team.name}
              <span className="font-normal text-slate-400">vs</span>
              {m.away_team.logo_url ? (
                <img src={m.away_team.logo_url} alt="" className="h-5 w-5 object-contain" />
              ) : null}
              {m.away_team.name}
            </div>
            <p className="mt-2 text-[11px] text-slate-600">
              {market?.label ?? 'SOT Totale'} · Previsti{' '}
              <span className="font-semibold tabular-nums text-slate-900">
                {market?.predicted_value != null ? formatNum(market.predicted_value) : '—'}
              </span>
            </p>
            <div className="mt-2">
              <p className="text-[10px] font-medium text-slate-500">Variazione</p>
              <LineupRefreshImpactBadge impact={m.lineup_refresh_impact} showReason compact />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-[10px] text-slate-500">Statistica</p>
                <p className="font-semibold">{pickShortLabel(market?.statistical_pick)}</p>
                {market?.statistical_risk ? (
                  <span className={`mt-1 inline-block rounded-full border px-1.5 py-0.5 text-[9px] ${riskBadgeClass(market.statistical_risk)}`}>
                    {market.statistical_risk}
                  </span>
                ) : null}
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-[10px] text-slate-500">Cauta</p>
                <p className="font-semibold text-emerald-900">{pickShortLabel(market?.cautious_pick)}</p>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <span
                title={AFFIDABILITA_HELP}
                className={`rounded-full border px-2 py-0.5 text-[10px] ${confidenceBadgeClass(market?.confidence_label)}`}
              >
                Affidabilità: {market?.confidence_label ?? '—'}
              </span>
              <span
                title={formTip || undefined}
                className={`rounded-full border px-2 py-0.5 text-[10px] ${formationBadgeClass(formLabel)}`}
              >
                {formLabel ?? '—'}
              </span>
            </div>
            {onOpenDetail ? (
              <button
                type="button"
                onClick={() => onOpenDetail(m.fixture_id)}
                className="mt-2 text-[11px] font-medium text-indigo-800 underline"
              >
                {selectedFixtureId === m.fixture_id ? 'Dettaglio ▾' : 'Dettaglio'}
              </button>
            ) : (
              <a
                href={`#match-${m.fixture_id}`}
                className="mt-2 inline-block text-[11px] font-medium text-indigo-800 underline"
              >
                Dettaglio
              </a>
            )}
          </article>
        )
      })}
    </div>
  )
}
