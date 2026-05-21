import type { ExplanationFixture, SideSummary } from '../../types/sotExplanation'

function fmtSot(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function SideBox({
  title,
  predicted,
  emphasize,
}: {
  title: string
  predicted: number | null | undefined
  emphasize?: boolean
}) {
  return (
    <div
      className={`rounded-xl border p-4 text-center ${
        emphasize
          ? 'border-indigo-200 bg-indigo-50/60'
          : 'border-slate-200 bg-slate-50/80'
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-slate-900">
        {fmtSot(predicted)}
      </p>
      <p className="mt-1 text-[11px] text-slate-500">SOT attesi</p>
    </div>
  )
}

export function PredictionModelSummary({
  fixture,
  home,
  away,
  matchTotal,
}: {
  fixture: ExplanationFixture
  home: SideSummary
  away: SideSummary
  matchTotal: { predicted_sot: number | null }
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <SideBox title={fixture.home_team.name} predicted={home.predicted_sot} />
      <SideBox title="Totale match" predicted={matchTotal.predicted_sot} emphasize />
      <SideBox title={fixture.away_team.name} predicted={away.predicted_sot} />
    </div>
  )
}
