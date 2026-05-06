import type { AuditResponse } from './types'

export function MatchAuditHero({ data }: { data: AuditResponse }) {
  const fx = data.fixture
  const roundLabel = fx.round ?? 'Giornata'
  const kickoff = new Date(fx.kickoff_at).toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
  const noLeakage = data.data_policy.no_data_leakage

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            {fx.home_team.logo_url ? (
              <img src={fx.home_team.logo_url} alt="" className="h-8 w-8 object-contain" />
            ) : null}
            <span className="text-base font-semibold text-slate-900">{fx.home_team.name}</span>
          </div>
          <span className="text-slate-400">vs</span>
          <div className="flex items-center gap-2">
            {fx.away_team.logo_url ? (
              <img src={fx.away_team.logo_url} alt="" className="h-8 w-8 object-contain" />
            ) : null}
            <span className="text-base font-semibold text-slate-900">{fx.away_team.name}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
            {fx.status_short}
          </span>
          <span
            className={`rounded-full px-2.5 py-0.5 font-medium ring-1 ${
              noLeakage
                ? 'bg-emerald-50 text-emerald-900 ring-emerald-200'
                : 'bg-amber-50 text-amber-900 ring-amber-200'
            }`}
          >
            {data.mode === 'pre_match' ? 'Pre-match audit' : 'Post-match audit'}
          </span>
          {noLeakage ? (
            <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 font-medium text-emerald-900 ring-1 ring-emerald-200">
              No data leakage
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <span className="font-medium text-slate-800">{roundLabel}</span>
        <span className="text-slate-300">·</span>
        <span>{kickoff}</span>
      </div>

      <p className="mt-3 text-xs text-slate-600">
        <strong>Policy dati:</strong> {data.data_policy.included_matches_rule}
      </p>
    </section>
  )
}

