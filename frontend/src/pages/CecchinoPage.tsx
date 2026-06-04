import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CecchinoFixtureDetail } from '../components/cecchino/CecchinoFixtureDetail'
import { CecchinoFixtureList } from '../components/cecchino/CecchinoFixtureList'
import { ContextBanner } from '../components/ContextBanner'
import { useCompetition } from '../contexts/CompetitionContext'
import {
  getCecchinoFixtureDetail,
  getCecchinoUpcomingForCompetition,
  type CecchinoFixtureDetailResponse,
  type CecchinoUpcomingResponse,
} from '../lib/api'
import { formatFetchError } from '../utils/formatFetchError'

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export function CecchinoPage() {
  const qs = useQuery()
  const navigate = useNavigate()
  const { selectedCompetitionId } = useCompetition()

  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')
  const [upcoming, setUpcoming] = useState<CecchinoUpcomingResponse | null>(null)
  const [detail, setDetail] = useState<CecchinoFixtureDetailResponse | null>(null)
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const syncUrl = useCallback(
    (nextFixtureId: number | null) => {
      if (selectedCompetitionId == null) return
      const p = new URLSearchParams()
      p.set('competition_id', String(selectedCompetitionId))
      if (nextFixtureId != null) p.set('fixture_id', String(nextFixtureId))
      navigate(`/cecchino?${p.toString()}`, { replace: true })
    },
    [navigate, selectedCompetitionId],
  )

  useEffect(() => {
    const load = async () => {
      setListError(null)
      setUpcoming(null)
      setDetail(null)
      if (selectedCompetitionId == null) {
        setListError('Seleziona un campionato nella sidebar.')
        setFixtureId(null)
        return
      }
      setListLoading(true)
      try {
        const data = await getCecchinoUpcomingForCompetition(selectedCompetitionId, { limit: 50 })
        setUpcoming(data)
        if (fixtureId == null && data.fixtures.length > 0) {
          const first = data.fixtures[0].fixture.fixture_id
          setFixtureId(first)
          syncUrl(first)
        }
      } catch (e) {
        setListError(formatFetchError(e))
      } finally {
        setListLoading(false)
      }
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on competition change only
  }, [selectedCompetitionId])

  useEffect(() => {
    const loadDetail = async () => {
      setDetailError(null)
      setDetail(null)
      if (selectedCompetitionId == null || fixtureId == null) return
      setDetailLoading(true)
      try {
        const data = await getCecchinoFixtureDetail(selectedCompetitionId, fixtureId)
        setDetail(data)
      } catch (e) {
        setDetailError(formatFetchError(e))
      } finally {
        setDetailLoading(false)
      }
    }
    void loadDetail()
  }, [selectedCompetitionId, fixtureId])

  const onSelectFixture = (id: number) => {
    setFixtureId(id)
    syncUrl(id)
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Cecchino</h1>
        <p className="mt-1 text-sm text-slate-600">
          Quote 1X2 da picchetti tecnici (v0.1 parità Excel). Modulo separato dal modello SOT — non
          influenza le previsioni SOT v2.0/v2.1.
        </p>
      </header>

      <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 px-4 py-3 text-xs text-indigo-900">
        Modulo separato dal modello SOT. Non influenza le previsioni SOT v2.0/v2.1.
      </div>

      <ContextBanner showModelSelector={false} />

      {listError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {listError}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(240px,280px)_1fr]">
        <aside className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-800">
            Prossime partite
            {upcoming?.round_label ? ` · ${upcoming.round_label}` : ''}
          </h2>
          {listLoading && <p className="text-xs text-slate-500">Caricamento…</p>}
          {upcoming && (
            <CecchinoFixtureList
              fixtures={upcoming.fixtures}
              selectedFixtureId={fixtureId}
              onSelect={onSelectFixture}
            />
          )}
        </aside>

        <section className="space-y-4">
          {detailLoading && <p className="text-xs text-slate-500">Calcolo dettaglio…</p>}
          {detailError && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {detailError}
            </p>
          )}
          {detail && detail.status === 'ok' && (
            <>
              <div className="text-sm text-slate-700">
                <span className="font-medium text-slate-900">
                  {detail.fixture.home_team.name} vs {detail.fixture.away_team.name}
                </span>
                <span className="ml-2 text-xs text-slate-500">
                  {detail.cecchino_version} · {detail.calculation_status}
                </span>
              </div>
              <CecchinoFixtureDetail detail={detail} />
            </>
          )}
        </section>
      </div>
    </div>
  )
}
