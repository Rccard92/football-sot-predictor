import type { V36Item } from '../../lib/cecchinoTodayApi'
import { CecchinoPatternHero } from './CecchinoPatternHero'
import { getV36Score } from './cecchinoPurchasabilityV36UiUtils'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { GoalIntensityPanel, PatternPanel, useLiveFixture } from './CecchinoV25Panel'

/** Pattern Master V2 nella scheda V2 (moduli V2 ricalcolati come nella RUN V2). */

export function CecchinoV2PatternHero({
  todayFixtureId,
  v36ByMarket,
}: {
  todayFixtureId: number
  v36ByMarket: Record<string, V36Item>
}) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-32 animate-pulse`} aria-busy="true" />
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
  const p = data?.models['V2']
  return (
    <CecchinoPatternHero
      p={p && p.status !== 'error' && p.status !== 'unavailable' ? p : undefined}
      model="V2"
      indexFor={(k) => {
        const it = v36ByMarket[k]
        return it && it.status === 'score' ? { score: getV36Score(it), label: it.class, title: 'Indice V3.6' } : null
      }}
    />
  )
}

/** Mercati indicati dai Pattern Master V2 con quota accesi (per segnalare contrasti nell'indice). */
export function useV2PatternMarkets(todayFixtureId: number | undefined): string[] {
  const { data } = useLiveFixture(todayFixtureId)
  return (data?.models['V2']?.modules?.patterns?.active ?? []).filter((x) => x.target_type === 'market').map((x) => x.target_key)
}

export function CecchinoV2Patterns({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-32 animate-pulse`} aria-busy="true" />
  if (error) return null
  const p = data?.models['V2']
  if (!p || p.status === 'error' || p.status === 'unavailable') return null
  return <PatternPanel p={p} title="Pattern Master V2 senza quota" model="V2" />
}

/** Intensità Goal della scheda V2: gli stessi valori (RUN V2) che leggono pattern e predizione. */
export function CecchinoV2GoalIntensity({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-32 animate-pulse`} aria-busy="true" />
  if (error) return null
  const p = data?.models['V2']
  if (!p || p.status === 'error' || p.status === 'unavailable' || !p.modules?.goal_intensity_pillars) {
    return <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>Intensità Goal V2 non calcolabile per questa partita.</div>
  }
  return (
    <GoalIntensityPanel
      p={p}
      model="V2"
      reference="alle partite della RUN V2 2025/2026 (16 campionati del Lab), le stesse usate dai Pattern Master V2"
    />
  )
}
