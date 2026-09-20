import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CecchinoTodayFixtureDrawer } from '../components/cecchino/CecchinoTodayFixtureDrawer'
import {
  todayCard,
  todayCardPadding,
  todayPageGrid,
  todaySectionTitle,
  todayStickyListColumn,
} from '../components/cecchino/cecchinoTodayStyles'
import { parseV4View, v4SmallButton, v4Title, type V4View } from '../components/cecchino-v4/constants'
import { isIsoDate } from '../components/cecchino-v4/format'
import { useIsDesktopPanel } from '../components/cecchino-v4/useMediaQuery'
import { useV4Query } from '../components/cecchino-v4/useV4Query'
import { V4DayTimeline } from '../components/cecchino-v4/V4DayTimeline'
import { V4EngineView } from '../components/cecchino-v4/V4EngineView'
import { V4Filters, type V4FiltersValue } from '../components/cecchino-v4/V4Filters'
import { V4FixtureList } from '../components/cecchino-v4/V4FixtureList'
import { V4MeasureView } from '../components/cecchino-v4/V4MeasureView'
import { V4Reasoning } from '../components/cecchino-v4/V4Reasoning'
import { V4ShortlistView } from '../components/cecchino-v4/V4ShortlistView'
import { V4Error, V4Loading } from '../components/cecchino-v4/V4States'
import { V4ViewSwitch } from '../components/cecchino-v4/V4ViewSwitch'
import { cecchinoV4Api, type CecchinoV4Api } from '../lib/cecchinoV4Api'
import { todayLocalIso } from '../utils/dateLocal'

export type CecchinoV4PageProps = {
  /** Client dati; i test iniettano il mock. */
  api?: CecchinoV4Api
}

const DEFAULT_FILTERS: V4FiltersValue = { league: '', onlyPlays: false, onlyLineups: false, sort: 'kickoff' }

function parseFixtureId(raw: string | null): number | null {
  return raw && /^\d+$/.test(raw) ? Number(raw) : null
}

export function CecchinoV4Page({ api = cecchinoV4Api }: CecchinoV4PageProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const today = todayLocalIso()
  const view = parseV4View(searchParams.get('view'))
  const dateParam = searchParams.get('date')
  const date = isIsoDate(dateParam) ? dateParam : today
  const selectedId = parseFixtureId(searchParams.get('fixture'))
  const isDesktop = useIsDesktopPanel()
  const [filters, setFilters] = useState<V4FiltersValue>(DEFAULT_FILTERS)

  const updateParams = useCallback(
    (patch: Record<string, string | null>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v == null || v === '') next.delete(k)
            else next.set(k, v)
          }
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const showTimeline = view === 'partite' || view === 'shortlist'
  const daysQ = useV4Query(showTimeline ? `days:${today}` : null, (signal) =>
    api.getDays({ from: today, days: 7 }, signal),
  )

  const fixturesKey =
    view === 'partite'
      ? `fixtures:${date}:${filters.league}:${filters.onlyPlays}:${filters.onlyLineups}:${filters.sort}`
      : null
  const fixturesQ = useV4Query(fixturesKey, (signal) =>
    api.getFixtures(
      {
        date,
        league: filters.league || null,
        only_plays: filters.onlyPlays,
        only_lineups: filters.onlyLineups,
        sort: filters.sort,
      },
      signal,
    ),
  )

  const detailKey = view === 'partite' && selectedId != null ? `detail:${selectedId}` : null
  const detailQ = useV4Query(detailKey, (signal) => api.getFixtureDetail(selectedId ?? 0, signal))

  const handleView = (next: V4View) => updateParams({ view: next === 'partite' ? null : next })
  const handleDay = (next: string) => updateParams({ date: next === today ? null : next, fixture: null })
  const handleSelectFixture = (id: number) => updateParams({ fixture: String(id) })
  const closeDetail = () => updateParams({ fixture: null })

  const hasActiveFilters = filters.league !== '' || filters.onlyPlays || filters.onlyLineups

  let detailContent = null
  if (selectedId == null) {
    detailContent = (
      <div
        className={`${todayCard} ${todayCardPadding} flex min-h-[200px] flex-col items-center justify-center text-center`}
        data-testid="v4-detail-placeholder"
      >
        <p className="text-sm font-medium text-slate-700">Seleziona una partita dalla lista</p>
        <p className="mt-2 max-w-xs text-xs text-slate-500">
          Qui compare il ragionamento in sei blocchi: perché sì e perché no, chi sono, come giocano, contesto, cosa
          prevede, come è andata.
        </p>
      </div>
    )
  } else if (detailQ.loading) {
    detailContent = <V4Loading label="Carico il ragionamento…" rows={4} />
  } else if (detailQ.error) {
    detailContent = <V4Error message={detailQ.error} onRetry={detailQ.reload} />
  } else if (detailQ.data) {
    detailContent = <V4Reasoning detail={detailQ.data} />
  }

  return (
    <div className="w-full space-y-5">
      <header className="space-y-3">
        <div>
          <h1 className={v4Title}>Cecchino V4</h1>
          <p className="mt-1 text-sm text-slate-500">Vedi tutto, gioca poco: le partite dei 16 campionati con il ragionamento completo.</p>
          <p className="mt-1 text-xs text-slate-500" data-testid="v4-help">
            Ogni partita mostra la giocata migliore secondo la regola del profitto; apri la partita per il ragionamento in
            sei blocchi. &quot;In osservazione&quot; = esame E4 non superato: si guarda, non si gioca.
          </p>
        </div>
        <V4ViewSwitch view={view} onChange={handleView} />
      </header>

      {showTimeline ? (
        daysQ.loading ? (
          <V4Loading label="Carico i giorni…" rows={1} />
        ) : daysQ.error ? (
          <V4Error message={daysQ.error} onRetry={daysQ.reload} />
        ) : daysQ.data ? (
          <V4DayTimeline days={daysQ.data.days} selectedDay={date} today={today} onSelectDay={handleDay} />
        ) : null
      ) : null}

      {view === 'partite' ? (
        <>
          <V4Filters value={filters} onChange={setFilters} />
          <div className={isDesktop ? todayPageGrid : 'grid grid-cols-1'}>
            <div className={isDesktop ? todayStickyListColumn : 'min-w-0'}>
              <V4FixtureList
                data={fixturesQ.data}
                loading={fixturesQ.loading}
                error={fixturesQ.error}
                onRetry={fixturesQ.reload}
                selectedId={selectedId}
                onSelect={handleSelectFixture}
                hasActiveFilters={hasActiveFilters}
              />
            </div>
            {isDesktop ? (
              <section className="min-w-0 space-y-3" aria-label="Ragionamento" data-testid="v4-detail-panel">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className={todaySectionTitle}>Ragionamento</h2>
                  {selectedId != null ? (
                    <button type="button" onClick={closeDetail} className={v4SmallButton}>
                      Chiudi
                    </button>
                  ) : null}
                </div>
                {detailContent}
              </section>
            ) : null}
          </div>
          {!isDesktop ? (
            <CecchinoTodayFixtureDrawer open={selectedId != null} onClose={closeDetail} title="Ragionamento">
              {detailContent}
            </CecchinoTodayFixtureDrawer>
          ) : null}
        </>
      ) : null}

      {view === 'shortlist' ? <V4ShortlistView api={api} date={date} /> : null}
      {view === 'misura' ? <V4MeasureView api={api} /> : null}
      {view === 'motore' ? <V4EngineView api={api} /> : null}
    </div>
  )
}
