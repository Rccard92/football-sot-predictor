import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { PatternPanel, useLiveFixture } from './CecchinoV25Panel'

/** Pattern Master V2 accesi nella scheda V2: moduli V2 ricalcolati come nella RUN V2. */
export function CecchinoV2Patterns({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-32 animate-pulse`} aria-busy="true" />
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
  const p = data?.models['V2']
  if (!p || p.status === 'error' || p.status === 'unavailable') {
    return (
      <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>
        Pattern Master V2 non calcolabili per questa partita{p?.error ? `: ${p.error}` : '.'}
      </div>
    )
  }
  return <PatternPanel p={p} title="Pattern Master V2 accesi" model="V2" />
}
