import type { CecchinoTodayScanMeta } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayFixtureCard } from './CecchinoTodayFixtureCard'
import { todayCard, todayCardPadding, todaySectionTitle, todaySkeleton } from './cecchinoTodayStyles'

export type TodayFlatFixture = {
  country: string
  league: string
  fixture: import('../../lib/cecchinoTodayApi').CecchinoTodayListFixture
}

type Props = {
  fixtures: TodayFlatFixture[]
  selectedId: number | null
  onSelect: (id: number) => void
  loading: boolean
  error: string | null
  selectedDay: string
  scanMeta: CecchinoTodayScanMeta | null | undefined
  onScanToday?: () => void
}

function FixtureSkeleton() {
  return <div className={`${todaySkeleton} h-28 w-full`} />
}

function EmptyMessage({
  selectedDay,
  scanMeta,
  onScanToday,
}: {
  selectedDay: string
  scanMeta: CecchinoTodayScanMeta | null | undefined
  onScanToday?: () => void
}) {
  if (!scanMeta || scanMeta.day_status === 'pending' || !scanMeta.has_scan) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/80 px-6 py-10 text-center">
        <p className="text-sm font-medium text-slate-700">
          Giornata non ancora scansionata ({selectedDay}).
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Usa &quot;Scansione oggi&quot; o &quot;Scansione domani&quot; per scoprire le partite
          eleggibili.
        </p>
        {onScanToday && (
          <button
            type="button"
            onClick={onScanToday}
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Scansione oggi
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50/80 px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-800">
        Nessuna partita eleggibile salvata per questa giornata.
      </p>
      <p className="mt-2 text-xs text-slate-600">
        Scansione completata: nessuna partita ha superato i controlli su quote bookmaker e
        statistiche ({scanMeta.excluded_count} escluse).
      </p>
    </div>
  )
}

export function CecchinoTodayFixtureList({
  fixtures,
  selectedId,
  onSelect,
  loading,
  error,
  selectedDay,
  scanMeta,
  onScanToday,
}: Props) {
  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className={todaySectionTitle}>Partite eleggibili</h2>
        {!loading && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            {fixtures.length}
          </span>
        )}
      </div>

      {loading && (
        <div className="space-y-3" aria-busy="true" aria-label="Caricamento partite">
          <FixtureSkeleton />
          <FixtureSkeleton />
          <FixtureSkeleton />
        </div>
      )}

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {!loading && !error && fixtures.length === 0 && (
        <EmptyMessage selectedDay={selectedDay} scanMeta={scanMeta} onScanToday={onScanToday} />
      )}

      {!loading && !error && fixtures.length > 0 && (
        <ul className="max-h-[calc(100vh-280px)] space-y-3 overflow-y-auto pr-1">
          {fixtures.map(({ country, league, fixture }) => (
            <li key={fixture.id}>
              <CecchinoTodayFixtureCard
                fixture={fixture}
                country={country}
                league={league}
                selected={selectedId === fixture.id}
                onSelect={() => onSelect(fixture.id)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
