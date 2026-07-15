import type { DrawCredibilityCohortTargetSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  primary: DrawCredibilityCohortTargetSummary
  sensitivity: DrawCredibilityCohortTargetSummary
  market: DrawCredibilityCohortTargetSummary
}

function CohortCard({ label, summary }: { label: string; summary: DrawCredibilityCohortTargetSummary }) {
  const ci = summary.wilson_ci_95
  return (
    <div className="rounded-xl border border-slate-100 bg-gradient-to-br from-white to-slate-50/80 p-3 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
        {summary.draw_rate_pct.toFixed(2)}%
      </p>
      <p className="text-xs text-slate-600">
        {summary.draws}/{summary.rows} pareggi
      </p>
      {ci.lower_pct != null && ci.upper_pct != null ? (
        <p className="mt-1 text-[10px] text-slate-500">
          Wilson 95%: {ci.lower_pct.toFixed(1)}–{ci.upper_pct.toFixed(1)}%
        </p>
      ) : null}
    </div>
  )
}

export function DrawCredibilityStatisticsBaselinePanel({ primary, sensitivity, market }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Baseline draw rate per coorte</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <CohortCard label="Primary" summary={primary} />
        <CohortCard label="Sensitivity" summary={sensitivity} />
        <CohortCard label="Market" summary={market} />
      </div>
    </section>
  )
}
