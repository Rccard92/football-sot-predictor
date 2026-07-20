import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { HomeWinsDetailDrawer } from '../components/cecchino-home-wins/HomeWinsDetailDrawer'
import { HomeWinsFiltersBar } from '../components/cecchino-home-wins/HomeWinsFiltersBar'
import { HomeWinsSummaryCards } from '../components/cecchino-home-wins/HomeWinsSummaryCards'
import { HomeWinsTable } from '../components/cecchino-home-wins/HomeWinsTable'
import {
  downloadHomeWinsDataset,
  getHomeWinsDetail,
  getHomeWinsList,
  type HomeWinsCompleteness,
  type HomeWinsDetailResponse,
  type HomeWinsListItem,
  type HomeWinsListResponse,
  type HomeWinsSummary,
} from '../lib/cecchinoHomeWinsApi'

const PAGE_SIZE = 50

export function CecchinoHomeWinsPage() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [country, setCountry] = useState('')
  const [league, setLeague] = useState('')
  const [team, setTeam] = useState('')
  const [completeness, setCompleteness] = useState<HomeWinsCompleteness>('')
  const [page, setPage] = useState(1)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<HomeWinsListItem[]>([])
  const [summary, setSummary] = useState<HomeWinsSummary | null>(null)
  const [total, setTotal] = useState(0)
  const [availableCountries, setAvailableCountries] = useState<string[]>([])
  const [availableLeagues, setAvailableLeagues] = useState<string[]>([])

  const [detailId, setDetailId] = useState<number | null>(null)
  const [detail, setDetail] = useState<HomeWinsDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const loadList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload: HomeWinsListResponse = await getHomeWinsList({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        country: country || undefined,
        league: league || undefined,
        team: team || undefined,
        completeness: completeness || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      setItems(payload.items || [])
      setSummary(payload.summary || null)
      setTotal(payload.total || 0)
      setAvailableCountries(payload.available_filters?.countries || [])
      setAvailableLeagues(payload.available_filters?.leagues || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Errore caricamento lista'
      setError(message)
      setItems([])
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, country, league, team, completeness, page])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lista on filter/page change
    void loadList()
  }, [loadList])

  const openDetail = async (id: number) => {
    setDetailId(id)
    setDetail(null)
    setDetailLoading(true)
    try {
      const payload = await getHomeWinsDetail(id)
      setDetail(payload)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Errore dettaglio'
      toast.error(message)
      setDetailId(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDownload = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      await downloadHomeWinsDataset({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        country: country || undefined,
        league: league || undefined,
        team: team || undefined,
        completeness: completeness || undefined,
      })
      toast.success('Download dataset avviato')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Download fallito')
    } finally {
      setDownloading(false)
    }
  }

  const resetFilters = () => {
    setDateFrom('')
    setDateTo('')
    setCountry('')
    setLeague('')
    setTeam('')
    setCompleteness('')
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-5 pb-10">
      <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Monitoraggio Segno 1
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Archivio delle partite terminate con vittoria della squadra di casa. La selezione
            dipende esclusivamente dal risultato finale e non dall&apos;attivazione del Segnale 1.
          </p>
        </div>
        <button
          type="button"
          disabled={downloading}
          onClick={() => void handleDownload()}
          className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {downloading ? 'Download in corso…' : 'Scarica dataset completo'}
        </button>
      </header>

      <HomeWinsSummaryCards summary={summary} loading={loading} />

      <HomeWinsFiltersBar
        dateFrom={dateFrom}
        dateTo={dateTo}
        country={country}
        league={league}
        team={team}
        completeness={completeness}
        countries={availableCountries}
        leagues={availableLeagues}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        onCountry={setCountry}
        onLeague={setLeague}
        onTeam={setTeam}
        onCompleteness={setCompleteness}
        onApply={() => {
          setPage(1)
          void loadList()
        }}
        onReset={resetFilters}
        loading={loading}
      />

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <HomeWinsTable items={items} loading={loading} onOpenDetail={(id) => void openDetail(id)} />

      <div className="flex items-center justify-between gap-3 text-sm text-slate-600">
        <span>
          Pagina {page} di {totalPages} · {total} record
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            Precedente
          </button>
          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            Successiva
          </button>
        </div>
      </div>

      {detailId != null ? (
        <HomeWinsDetailDrawer
          detail={detail}
          loading={detailLoading}
          onClose={() => {
            setDetailId(null)
            setDetail(null)
          }}
        />
      ) : null}
    </div>
  )
}
