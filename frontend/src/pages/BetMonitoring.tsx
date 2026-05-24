import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_SEASON,
  getTrackedBettingPicks,
  postCreateTrackedPicksFromRound,
  postRefreshTrackedPickResults,
  type TrackedBettingPickRow,
  type TrackedBettingPicksSummary,
} from '../lib/api'
import { formatKickoffReport } from '../utils/sportApiLineupMeta'
import {
  formatOdd,
  formatSotDisplay,
  formatSotTotal,
  isLiveFixture,
  LIVE_MONITOR_REFRESH_MS,
  outcomeClass,
} from '../utils/monitoring'

const AUTO_REFRESH_COOLDOWN_MS = 120_000

type RefreshScope = 'all' | 'live' | 'unfinished' | 'unfinished_or_recent'

const TABLE_HEADERS = [
  'Data evento',
  'Partita',
  'Tiri in porta iniziali',
  'Tiri in porta post ufficiali',
  'Scommessa iniziale',
  'Quota iniziale',
  'Scommessa post ufficiali',
  'Quota post ufficiali',
  'Tiri in porta reali',
  'Esito iniziale',
  'Esito post ufficiali',
  'Stato partita',
] as const

function sortByKickoffAsc(rows: TrackedBettingPickRow[]): TrackedBettingPickRow[] {
  return [...rows].sort((a, b) => {
    const ta = a.kickoff_at ? new Date(a.kickoff_at).getTime() : Number.POSITIVE_INFINITY
    const tb = b.kickoff_at ? new Date(b.kickoff_at).getTime() : Number.POSITIVE_INFINITY
    if (ta !== tb) return ta - tb
    return a.id - b.id
  })
}

function formatLastRefreshed(iso: string | null): string {
  if (!iso) return ''
  try {
    return formatKickoffReport(iso)
  } catch {
    return iso
  }
}

function formatWinRate(rate: number | null | undefined): string {
  if (rate == null) return '—'
  return `${(rate * 100).toFixed(1)}%`
}

function SummaryCards({ summary }: { summary: TrackedBettingPicksSummary | null }) {
  if (!summary) return null
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ['Monitorate', summary.total],
        ['Live', summary.live],
        ['Win rate iniziale', formatWinRate(summary.initial_win_rate)],
        ['Win rate post ufficiali', formatWinRate(summary.official_win_rate)],
      ].map(([label, val]) => (
        <div key={String(label)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">{val}</p>
        </div>
      ))}
    </div>
  )
}

function DashboardRow({ p }: { p: TrackedBettingPickRow }) {
  const live = isLiveFixture(p)
  const sot = formatSotDisplay(p)
  const rowClass = live
    ? 'border-b border-slate-100 bg-sky-50/60 font-semibold hover:bg-sky-50/80'
    : 'border-b border-slate-100 hover:bg-slate-50/50'

  return (
    <tr className={rowClass}>
      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-xs">
        {p.kickoff_at ? formatKickoffReport(p.kickoff_at) : '—'}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span>{p.match_name}</span>
          {live ? (
            <span className="rounded-full bg-sky-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
              LIVE
            </span>
          ) : null}
        </div>
      </td>
      <td className="px-3 py-2.5 tabular-nums text-sm">{formatSotTotal(p.initial_predicted_total_sot)}</td>
      <td className="px-3 py-2.5 tabular-nums text-sm">{formatSotTotal(p.official_predicted_total_sot)}</td>
      <td className="px-3 py-2.5 text-sm">{p.initial_suggested_pick ?? '—'}</td>
      <td className="px-3 py-2.5 tabular-nums text-sm">{formatOdd(p.initial_odd)}</td>
      <td className="px-3 py-2.5 text-sm">{p.official_suggested_pick ?? '—'}</td>
      <td className="px-3 py-2.5 tabular-nums text-sm">{formatOdd(p.official_odd)}</td>
      <td className="px-3 py-2.5 tabular-nums text-xs" title={sot.title}>
        {sot.main}
      </td>
      <td className={`px-3 py-2.5 text-sm ${outcomeClass(p.initial_outcome)}`}>{p.initial_outcome}</td>
      <td className={`px-3 py-2.5 text-sm ${outcomeClass(p.official_outcome)}`}>{p.official_outcome}</td>
      <td className="px-3 py-2.5 text-sm tabular-nums">{p.fixture_status_label}</td>
    </tr>
  )
}

export function BetMonitoring() {
  const [rows, setRows] = useState<TrackedBettingPickRow[]>([])
  const [summary, setSummary] = useState<TrackedBettingPicksSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [createBusy, setCreateBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [lastResultsRefreshAt, setLastResultsRefreshAt] = useState<string | null>(null)
  const [autoRefreshStatus, setAutoRefreshStatus] = useState<string | null>(null)
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null)
  const refreshBusyRef = useRef(false)
  const lastAutoRefreshAtRef = useRef(0)
  const initialRefreshDoneRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTrackedBettingPicks(DEFAULT_SEASON)
      setRows(sortByKickoffAsc(data.picks ?? []))
      setSummary(data.summary ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runRefreshResults = useCallback(
    async (scope: RefreshScope = 'all', opts?: { force?: boolean; isAuto?: boolean }) => {
      if (refreshBusyRef.current) return
      const isManualAll = scope === 'all' && !opts?.isAuto
      refreshBusyRef.current = true
      setRefreshBusy(true)
      if (isManualAll) {
        setActionMsg(null)
        setRefreshWarning(null)
      }
      if (opts?.isAuto) {
        setAutoRefreshStatus('Aggiornamento risultati in corso…')
      }
      try {
        const out = await postRefreshTrackedPickResults(
          DEFAULT_SEASON,
          { scope, force: opts?.force },
          { timeoutMs: 300_000 },
        )
        if (out.last_refreshed_at) {
          setLastResultsRefreshAt(out.last_refreshed_at)
        }
        if (opts?.isAuto) {
          lastAutoRefreshAtRef.current = Date.now()
        }
        if (isManualAll) {
          setActionMsg(
            `Aggiornate ${out.picks_updated} giocate su ${out.picks_checked} controllate` +
              (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
          )
        } else if (opts?.isAuto && out.errors?.length) {
          setRefreshWarning(
            `Aggiornamento automatico: ${out.errors.length} errori (alcune giocate potrebbero non essere aggiornate).`,
          )
        }
        await load()
      } catch (e) {
        if (isManualAll) {
          setActionMsg(e instanceof Error ? e.message : String(e))
        } else if (opts?.isAuto) {
          setRefreshWarning(e instanceof Error ? e.message : String(e))
        }
      } finally {
        refreshBusyRef.current = false
        setRefreshBusy(false)
        if (opts?.isAuto) {
          setAutoRefreshStatus(null)
        }
      }
    },
    [load],
  )

  const runAutoRefreshIfAllowed = useCallback(() => {
    if (refreshBusyRef.current) return
    const now = Date.now()
    if (now - lastAutoRefreshAtRef.current < AUTO_REFRESH_COOLDOWN_MS) return
    void runRefreshResults('unfinished_or_recent', { isAuto: true })
  }, [runRefreshResults])

  useEffect(() => {
    if (initialRefreshDoneRef.current) return
    initialRefreshDoneRef.current = true
    void runAutoRefreshIfAllowed()
  }, [runAutoRefreshIfAllowed])

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return
      const lastAt = lastResultsRefreshAt
        ? new Date(lastResultsRefreshAt).getTime()
        : lastAutoRefreshAtRef.current
      if (Date.now() - lastAt < AUTO_REFRESH_COOLDOWN_MS) return
      runAutoRefreshIfAllowed()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [lastResultsRefreshAt, runAutoRefreshIfAllowed])

  useEffect(() => {
    const hasLive = rows.some(isLiveFixture)
    if (!hasLive || document.visibilityState === 'hidden') {
      return
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === 'hidden' || refreshBusyRef.current) return
      void runRefreshResults('live', { isAuto: true })
    }, LIVE_MONITOR_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [rows, runRefreshResults])

  const runCreateFromRound = async (force = false) => {
    setCreateBusy(true)
    setActionMsg(null)
    try {
      const out = await postCreateTrackedPicksFromRound(
        DEFAULT_SEASON,
        {
          round: 'current',
          model_id: 'baseline_v2_0_lineup_impact',
          pick_type: 'cautious',
          force,
        },
        { timeoutMs: 120_000 },
      )
      setActionMsg(
        `Turno: create ${out.created}, aggiornate ${out.updated}, saltate ${out.skipped} su ${out.fixtures_total} partite` +
          (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
      )
      await load()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setCreateBusy(false)
    }
  }

  const hasPicks = rows.length > 0
  const hasLiveRows = rows.some(isLiveFixture)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">Monitoraggio Giocate</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Confronto tra previsione iniziale (probabili), previsione post formazioni ufficiali, scommesse proposte ed
            esiti sui tiri in porta reali da API-Sports.
          </p>
          {lastResultsRefreshAt ? (
            <p className="mt-1 text-xs text-slate-500">
              Ultimo aggiornamento risultati: {formatLastRefreshed(lastResultsRefreshAt)}
              {hasLiveRows ? ' · auto-refresh ogni 5 min per partite live' : ''}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={createBusy}
            onClick={() => void runCreateFromRound(hasPicks)}
            className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
          >
            {createBusy
              ? 'Creazione…'
              : hasPicks
                ? 'Crea/aggiorna monitoraggio turno'
                : 'Crea monitoraggio turno'}
          </button>
          <button
            type="button"
            disabled={refreshBusy || !hasPicks}
            onClick={() => void runRefreshResults('all', { force: true })}
            className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-sm font-medium text-indigo-900 hover:bg-indigo-50 disabled:opacity-50"
          >
            {refreshBusy ? 'Aggiornamento…' : 'Aggiorna risultati'}
          </button>
        </div>
      </div>

      {autoRefreshStatus ? <p className="text-sm text-indigo-700">{autoRefreshStatus}</p> : null}
      {refreshWarning ? <p className="text-sm text-amber-700">{refreshWarning}</p> : null}
      {actionMsg ? <p className="text-sm text-slate-700">{actionMsg}</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {!loading && hasPicks ? <SummaryCards summary={summary} /> : null}

      {loading ? (
        <p className="text-sm text-slate-500">Caricamento…</p>
      ) : !hasPicks ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          <p>
            Nessuna giocata tracciata. Puoi crearle dal turno corrente usando le predizioni già disponibili, oppure
            attendere il job pre-match automatico.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-[1100px] w-full text-left text-sm text-slate-800">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {TABLE_HEADERS.map((h) => (
                  <th key={h} className="whitespace-nowrap px-3 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <DashboardRow key={p.id} p={p} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
