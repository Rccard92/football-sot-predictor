import type { QuickPlayMarket, UpcomingActiveMatchRow } from '../../lib/api'
import { formatKickoffReport } from '../../utils/sportApiLineupMeta'
import {
  confidenceBadgeClass,
  formationBadgeClass,
  pickShortLabel,
  riskBadgeClass,
} from '../../utils/bettingAdviceDisplay'
import { formatNum, formatSignedNum } from './format'

function TeamLogosMatch({ match }: { match: UpcomingActiveMatchRow }) {
  return (
    <div className="flex min-w-[10rem] flex-wrap items-center gap-1.5">
      {match.home_team.logo_url ? (
        <img src={match.home_team.logo_url} alt="" className="h-5 w-5 shrink-0 object-contain" />
      ) : (
        <span className="inline-block h-5 w-5 shrink-0 rounded-full bg-slate-100" />
      )}
      <span className="font-medium text-slate-900">{match.home_team.name}</span>
      <span className="text-slate-400">–</span>
      {match.away_team.logo_url ? (
        <img src={match.away_team.logo_url} alt="" className="h-5 w-5 shrink-0 object-contain" />
      ) : (
        <span className="inline-block h-5 w-5 shrink-0 rounded-full bg-slate-100" />
      )}
      <span className="font-medium text-slate-900">{match.away_team.name}</span>
    </div>
  )
}

function StatCell({ market }: { market: QuickPlayMarket | undefined }) {
  if (!market?.statistical_pick) {
    return <span className="text-[11px] text-amber-800">Nessuna giocata</span>
  }
  return (
    <div className="space-y-0.5">
      <p className="font-semibold text-slate-900">{pickShortLabel(market.statistical_pick)}</p>
      {market.statistical_margin != null ? (
        <p className="text-[10px] text-slate-600 tabular-nums">{formatSignedNum(market.statistical_margin)}</p>
      ) : null}
      {market.statistical_risk ? (
        <span className={`inline-block rounded-full border px-1.5 py-0.5 text-[9px] font-medium ${riskBadgeClass(market.statistical_risk)}`}>
          {market.statistical_risk}
        </span>
      ) : null}
    </div>
  )
}

function CautCell({ market }: { market: QuickPlayMarket | undefined }) {
  if (!market?.cautious_pick) {
    return <span className="text-[11px] text-amber-800">—</span>
  }
  const same = market.cautious_same_as_statistical
  return (
    <div className="space-y-0.5">
      <p className="font-semibold text-emerald-900">{pickShortLabel(market.cautious_pick)}</p>
      {market.cautious_margin != null ? (
        <p className="text-[10px] text-slate-600 tabular-nums">{formatSignedNum(market.cautious_margin)}</p>
      ) : null}
      <span className="inline-block rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[9px] font-medium text-emerald-900">
        {same ? 'Cauta già valida' : 'Cauta'}
      </span>
    </div>
  )
}

export function QuickPlayReportTable({ matches }: { matches: UpcomingActiveMatchRow[] }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="min-w-full text-left text-[11px] text-slate-800">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/80 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-3 py-2">Data/Ora</th>
            <th className="px-3 py-2">Match</th>
            <th className="px-3 py-2">Mercato</th>
            <th className="px-3 py-2">Previsti</th>
            <th className="px-3 py-2">Statistica</th>
            <th className="px-3 py-2">Cauta</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Formazione</th>
            <th className="px-3 py-2">Azione</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((m) => {
            const market = m.markets?.[0]
            return (
              <tr key={m.fixture_id} className="border-b border-slate-100 hover:bg-slate-50/50">
                <td className="whitespace-nowrap px-3 py-2.5 tabular-nums">{formatKickoffReport(m.kickoff_at)}</td>
                <td className="px-3 py-2.5">
                  <TeamLogosMatch match={m} />
                </td>
                <td className="px-3 py-2.5 font-medium">{market?.label ?? 'SOT Totale'}</td>
                <td className="px-3 py-2.5 tabular-nums font-semibold">
                  {market?.predicted_value != null ? formatNum(market.predicted_value) : '—'}
                </td>
                <td className="px-3 py-2.5">
                  <StatCell market={market} />
                </td>
                <td className="px-3 py-2.5">
                  <CautCell market={market} />
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${confidenceBadgeClass(market?.confidence_label)}`}
                  >
                    {market?.confidence_label ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${formationBadgeClass(m.lineup_status?.label)}`}
                  >
                    {m.lineup_status?.label ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <a
                    href={`#match-${m.fixture_id}`}
                    className="font-medium text-indigo-800 underline hover:text-indigo-950"
                  >
                    Dettaglio
                  </a>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
