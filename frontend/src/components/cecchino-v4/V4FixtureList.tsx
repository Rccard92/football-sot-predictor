import type { V4FixturesResponse } from '../../lib/cecchinoV4Api'
import { todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding, todaySectionTitle } from '../cecchino/cecchinoTodayStyles'
import { dayCounts, type V4DayCounts } from './dayCounts'
import { V4FixtureCard } from './V4FixtureCard'
import { V4Empty, V4Error, V4Loading } from './V4States'

type Props = {
  data: V4FixturesResponse | null
  loading: boolean
  error: string | null
  onRetry: () => void
  selectedId: number | null
  onSelect: (id: number) => void
  hasActiveFilters: boolean
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** Riga di riepilogo come CecchinoTodayDaySummary: tre badge piccoli. */
export function V4DaySummaryBadges({ counts }: { counts: V4DayCounts }) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="v4-abstention-line">
      <span className={todayBadgeMuted}>{plural(counts.fixtures, 'partita', 'partite')}</span>
      <span className={counts.plays > 0 ? todayBadgeOk : todayBadgeMuted}>{plural(counts.plays, 'giocata', 'giocate')}</span>
      <span className={todayBadgeMuted} title={counts.reasons || undefined}>
        {plural(counts.abstained, 'astensione', 'astensioni')}
      </span>
    </div>
  )
}

export function V4FixtureList({ data, loading, error, onRetry, selectedId, onSelect, hasActiveFilters }: Props) {
  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`} data-testid="v4-fixture-list">
      <div className="sticky top-0 z-[1] -mx-1 flex flex-wrap items-center justify-between gap-2 bg-white/95 px-1 py-1 backdrop-blur-sm">
        <h2 className={todaySectionTitle}>Partite</h2>
        {data && !loading ? <V4DaySummaryBadges counts={dayCounts(data)} /> : null}
      </div>

      {loading ? <V4Loading label="Carico le partite…" rows={4} /> : null}
      {error ? <V4Error message={error} onRetry={onRetry} /> : null}

      {data && !loading && !error ? (
        data.items.length === 0 ? (
          <V4Empty
            title={hasActiveFilters ? 'Nessuna partita con questi filtri' : 'Nessuna partita dei 16 campionati in questo giorno'}
            hint={hasActiveFilters ? 'Allarga i filtri per vedere le altre partite analizzate.' : undefined}
          />
        ) : (
          <ul className="space-y-2">
            {data.items.map((f) => (
              <li key={f.id}>
                <V4FixtureCard fixture={f} selected={f.id === selectedId} onSelect={onSelect} />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  )
}
