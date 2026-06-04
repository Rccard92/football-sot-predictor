import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CecchinoFixtureDetailPanel } from '../components/cecchino/CecchinoFixtureDetailPanel'
import { CecchinoFixturesTable } from '../components/cecchino/CecchinoFixturesTable'
import { CecchinoPageHeader } from '../components/cecchino/CecchinoPageHeader'
import { ContextBanner } from '../components/ContextBanner'
import { useCompetition } from '../contexts/CompetitionContext'
import {
  getCecchinoFixtureDetail,
  getCecchinoUpcomingForCompetition,
  type CecchinoFixtureDetailResponse,
  type CecchinoUpcomingResponse,
} from '../lib/cecchinoApi'
import { formatFetchError } from '../utils/formatFetchError'

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export function CecchinoPage() {
  const qs = useQuery()
  const navigate = useNavigate()
  const { selectedCompetitionId } = useCompetition()

  const fixtureId = useMemo(() => {
    const id = Number(qs.get('fixture_id') || '')
    return Number.isFinite(id) && id > 0 ? id : null
  }, [qs])
  const [upcoming, setUpcoming] = useState<CecchinoUpcomingResponse | null>(null)
  const [detail, setDetail] = useState<CecchinoFixtureDetailResponse | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [recalcLoading, setRecalcLoading] = useState(false)

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
        return
      }
      setListLoading(true)
      try {
        const data = await getCecchinoUpcomingForCompetition(selectedCompetitionId, { limit: 50 })
        setUpcoming(data)
      } catch (e) {
        setListError(formatFetchError(e))
      } finally {
        setListLoading(false)
      }
    }
    void load()
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
    syncUrl(id)
  }

  const onRecalculateDetail = async () => {
    if (selectedCompetitionId == null || fixtureId == null) return
    setRecalcLoading(true)
    setDetailError(null)
    try {
      const data = await getCecchinoFixtureDetail(selectedCompetitionId, fixtureId, {
        recalculate: true,
      })
      setDetail(data)
    } catch (e) {
      setDetailError(formatFetchError(e))
    } finally {
      setRecalcLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <CecchinoPageHeader cecchinoVersion={upcoming?.cecchino_version} />

      <ContextBanner showModelSelector={false} />

      {listError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {listError}
        </p>
      )}

      {listLoading && <p className="text-xs text-slate-500">Caricamento partite…</p>}

      {upcoming && (
        <CecchinoFixturesTable
          fixtures={upcoming.fixtures}
          selectedFixtureId={fixtureId}
          onSelect={onSelectFixture}
          roundLabel={upcoming.round_label}
        />
      )}

      {fixtureId == null && upcoming && upcoming.fixtures.length > 0 && (
        <p className="text-sm text-slate-500">
          Seleziona una partita dalla tabella e premi «Dettaglio» per vedere picchetti e quote.
        </p>
      )}

      {fixtureId != null && (
        <section className="space-y-3 border-t border-slate-200 pt-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Dettaglio partita</h2>
            <button
              type="button"
              disabled={detailLoading || recalcLoading}
              onClick={() => void onRecalculateDetail()}
              className="rounded-md border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {recalcLoading ? 'Ricalcolo…' : 'Ricalcola'}
            </button>
          </div>
          {detailLoading && <p className="text-xs text-slate-500">Caricamento dettaglio…</p>}
          {detailError && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {detailError}
            </p>
          )}
          {detail && <CecchinoFixtureDetailPanel detail={detail} />}
        </section>
      )}
    </div>
  )
}
