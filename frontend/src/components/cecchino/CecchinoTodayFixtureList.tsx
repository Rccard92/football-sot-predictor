import { useState } from 'react'
import type { CecchinoTodayListCountry, CecchinoTodayListFixture } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayFixtureCard } from './CecchinoTodayFixtureCard'
import { todayCard, todayCardPadding, todaySectionTitle, todaySkeleton } from './cecchinoTodayStyles'

function SafeImg({ src, alt, className }: { src: string | null | undefined; alt: string; className: string }) {
  const [hidden, setHidden] = useState(false)
  if (!src || hidden) return null
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setHidden(true)}
    />
  )
}

type Props = {
  countries: CecchinoTodayListCountry[]
  selectedId: number | null
  onSelect: (id: number) => void
  loading: boolean
  error: string | null
  selectedDay: string
  isScanned: boolean
  hasActiveFilters: boolean
  totalBeforeFilter: number
  onScanDay: () => void
}

function FixtureSkeleton() {
  return <div className={`${todaySkeleton} h-36 w-full`} />
}

export function CecchinoTodayFixtureList({
  countries,
  selectedId,
  onSelect,
  loading,
  error,
  selectedDay,
  isScanned,
  hasActiveFilters,
  totalBeforeFilter,
  onScanDay,
}: Props) {
  const fixtureCount = countries.reduce(
    (n, c) => n + c.leagues.reduce((ln, l) => ln + l.fixtures.length, 0),
    0,
  )

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className={todaySectionTitle}>Partite eleggibili</h2>
        {!loading && <span className="text-xs text-slate-500">{fixtureCount} visibili</span>}
      </div>

      {loading && (
        <div className="space-y-3" aria-busy="true">
          <FixtureSkeleton />
          <FixtureSkeleton />
        </div>
      )}

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {!loading && !error && !isScanned && (
        <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50 px-6 py-10 text-center">
          <p className="text-sm font-medium text-slate-800">
            Giornata non ancora scansionata ({selectedDay}).
          </p>
          <p className="mt-2 text-xs text-slate-600">
            Avvia la scansione per importare e salvare le partite eleggibili.
          </p>
          <button
            type="button"
            onClick={onScanDay}
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Avvia scansione giornata
          </button>
        </div>
      )}

      {!loading && !error && isScanned && totalBeforeFilter === 0 && (
        <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50/80 px-6 py-10 text-center">
          <p className="text-sm font-medium text-slate-800">
            Scansione completata: nessuna partita ha superato i controlli.
          </p>
          <p className="mt-2 text-xs text-slate-600">
            Consulta il pannello debug escluse per i dettagli.
          </p>
        </div>
      )}

      {!loading && !error && isScanned && totalBeforeFilter > 0 && fixtureCount === 0 && hasActiveFilters && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center text-sm text-slate-600">
          Nessuna partita corrisponde ai filtri selezionati.
        </div>
      )}

      {!loading && !error && fixtureCount > 0 && (
        <div className="space-y-8 pr-1">
          {countries.map((country) => (
            <div key={country.country_name} className="space-y-4">
              <div className="flex items-center gap-2 border-b-2 border-slate-200 pb-2">
                <SafeImg
                  src={country.country_flag_url}
                  alt=""
                  className="h-4 w-6 object-cover"
                />
                <h3 className="text-base font-semibold text-slate-900">{country.country_name}</h3>
              </div>
              {country.leagues.map((league) => (
                <div key={`${country.country_name}-${league.league_name}`} className="space-y-3 pl-1">
                  <div className="flex items-center gap-2 py-1">
                    <SafeImg src={league.league_logo_url} alt="" className="h-5 w-5 object-contain" />
                    <h4 className="text-sm font-semibold text-slate-700">{league.league_name}</h4>
                  </div>
                  <ul className="space-y-3">
                    {league.fixtures.map((fixture: CecchinoTodayListFixture) => (
                      <li key={fixture.today_fixture_id}>
                        <CecchinoTodayFixtureCard
                          fixture={fixture}
                          selected={selectedId === fixture.today_fixture_id}
                          onSelect={() => onSelect(fixture.today_fixture_id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
