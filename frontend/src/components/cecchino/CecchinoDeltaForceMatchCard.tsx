import type { CecchinoDeltaForceAnalysis } from '../../lib/cecchinoTodayApi'

type Props = {
  deltaForceAnalysis?: CecchinoDeltaForceAnalysis
}

function severityStyles(severity?: string): string {
  switch (severity) {
    case 'positive':
      return 'border-emerald-200 bg-emerald-50/80 text-emerald-950'
    case 'warning':
      return 'border-amber-200 bg-amber-50/80 text-amber-950'
    case 'negative':
      return 'border-violet-300 bg-violet-50/80 text-violet-950'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-800'
  }
}

function directionSummary(match: NonNullable<CecchinoDeltaForceAnalysis['match']>): string {
  if (match.responsible_direction === 'aligned') {
    return 'Quote 1/X/2 allineate al modello'
  }
  if (match.responsible_direction === 'quota_book_lower_than_cecchino') {
    return 'Betfair comprime la quota rispetto al Cecchino'
  }
  if (match.responsible_direction === 'quota_book_higher_than_cecchino') {
    return 'Betfair più alta della quota Cecchino'
  }
  return match.responsible_direction_label ?? '—'
}

export function CecchinoDeltaForceMatchCard({ deltaForceAnalysis }: Props) {
  if (!deltaForceAnalysis || deltaForceAnalysis.status !== 'available' || !deltaForceAnalysis.match) {
    return (
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        Delta Forza Match non disponibile: quote Betfair o Cecchino 1/X/2 insufficienti.
      </div>
    )
  }

  const match = deltaForceAnalysis.match

  return (
    <div className={`border-b border-slate-200 px-4 py-3 text-sm ${severityStyles(match.severity)}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-80">Delta Forza Match</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{match.delta_forza_abs?.toFixed(1)}%</p>
      <p className="mt-1 font-medium">{match.label ?? '—'}</p>
      <p className="mt-2 text-xs opacity-90">
        Segno responsabile: {match.responsible_side_label ?? '—'}
      </p>
      <p className="mt-1 text-xs opacity-90">{directionSummary(match)}</p>
    </div>
  )
}
