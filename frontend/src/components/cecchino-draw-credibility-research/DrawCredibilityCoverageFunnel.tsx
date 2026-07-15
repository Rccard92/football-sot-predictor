import type { DrawCredibilityAuditCoverage, DrawCredibilityAuditSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  summary: DrawCredibilityAuditSummary
  coverage: DrawCredibilityAuditCoverage
}

type Step = {
  label: string
  count: number
  pct: number
}

function buildSteps(summary: DrawCredibilityAuditSummary, coverage: DrawCredibilityAuditCoverage): Step[] {
  const total = summary.total_fixtures || 1
  return [
    { label: 'Risultati FT', count: summary.finished_with_result, pct: (summary.finished_with_result / total) * 100 },
    {
      label: 'Cecchino 1X2 completo',
      count: summary.with_complete_cecchino_1x2,
      pct: coverage.cecchino.pct_complete_1x2,
    },
    {
      label: 'Cecchino Under/Over 2.5',
      count: summary.with_complete_cecchino_goal_pair,
      pct: coverage.cecchino.pct_complete_goal_pair,
    },
    { label: 'Book 1X2', count: summary.with_book_1x2, pct: (summary.with_book_1x2 / total) * 100 },
    {
      label: 'Book Under/Over 2.5',
      count: summary.with_complete_book_goal_pair,
      pct: (summary.with_complete_book_goal_pair / total) * 100,
    },
    {
      label: 'Dataset finale interno',
      count: summary.usable_internal_research,
      pct: coverage.research.pct_internal,
    },
    {
      label: 'Dataset con Book',
      count: summary.usable_market_comparison,
      pct: coverage.research.pct_market,
    },
  ]
}

export function DrawCredibilityCoverageFunnel({ summary, coverage }: Props) {
  const steps = buildSteps(summary, coverage)
  const maxCount = Math.max(...steps.map((s) => s.count), 1)

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Funnel copertura</h2>
      <div className="mt-4 space-y-3">
        {steps.map((step) => (
          <div key={step.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-slate-700">{step.label}</span>
              <span className="tabular-nums text-slate-500">
                {step.count} ({step.pct.toFixed(2)}%)
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet-500 to-indigo-500 transition-all"
                style={{ width: `${Math.max(2, (step.count / maxCount) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
