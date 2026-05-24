import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_SEASON,
  getTrackedBettingPicks,
  postCreateTrackedPicksFromRound,
  postRefreshTrackedPickResults,
  type TrackedBettingPickRow,
  type TrackedBettingPicksSummary,
  type UpcomingMatchTeam,
} from '../lib/api'
import { formatKickoffReport } from '../utils/sportApiLineupMeta'
import {
  formatOdd,
  formatSotDisplay,
  formatSotTotal,
  isLiveFixture,
  LIVE_MONITOR_REFRESH_MS,
  outcomeBadgeClass,
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

/** Larghezze colonna (%): full width senza scroll orizzontale. */
const COL_WIDTHS = ['8%', '16%', '7%', '7%', '9%', '5%', '9%', '5%', '8%', '7%', '7%', '7%'] as const

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

function TeamLogo({ team }: { team: UpcomingMatchTeam }) {
  if (team.logo_url) {
    return <img src={team.logo_url} alt="" className="h-5 w-5 shrink-0 object-contain" />
  }
  return <span className="inline-block h-5 w-5 shrink-0 rounded-full bg-slate-200/80" aria-hidden />
}

function MatchTeamsCell({ p, live }: { p: TrackedBettingPickRow; live: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <TeamLogo team={p.home_team} />
      <span className={live ? 'font-semibold text-slate-900' : 'font-medium text-slate-900'}>
        {p.home_team.name}
      </span>
      <span className="text-slate-400">–</span>
      <TeamLogo team={p.away_team} />
      <span className={live ? 'font-semibold text-slate-900' : 'font-medium text-slate-900'}>
        {p.away_team.name}
      </span>
      {live ? (
        <span className="rounded-full bg-sky-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          LIVE
        </span>
      ) : null}
    </div>
  )
}

function OutcomeCell({ outcome }: { outcome: string }) {
  return <span className={outcomeBadgeClass(outcome)}>{outcome}</span>
}

function SummaryCards({ summary }: { summary: TrackedBettingPicksSummary | null }) {
  if (!summary) return null
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ['Monitorate', summary.total],
        ['Live', summary.live],
        ['Win rate iniziale', formatWinRate(summary.initial_win_rate)],
        ['Win rate post ufficiali', formatWinRate(summary.official_win_rate)],
      ].map(([label, val]) => (
        <div
          key={String(label)}
          className="rounded-xl border border-slate-200/90 bg-gradient-to-b from-white to-slate-50/80 px-4 py-3 shadow-sm"
        >
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{val}</p>
        </div>
      ))}
    </div>
  )
}

function DashboardRow({ p, index }: { p: TrackedBettingPickRow; index: number }) {
  const live = isLiveFixture(p)
  const sot = formatSotDisplay(p)
  const rowClass = live
    ? 'bg-sky-50/70 font-semibold ring-1 ring-inset ring-sky-200/50 hover:bg-sky-50/90'
    : index % 2 === 0
      ? 'bg-white hover:bg-slate-50/80'
      : 'bg-slate-50/40 hover:bg-slate-50/70'

  return (
    <tr className={`border-b border-slate-100/90 transition-colors ${rowClass}`}>
      <td className="px-2 py-2.5 text-[11px] tabular-nums text-slate-600">
        {p.kickoff_at ? formatKickoffReport(p.kickoff_at) : '—'}
      </td>
      <td className="px-2 py-2.5 align-middle">
        <MatchTeamsCell p={p} live={live} />
      </td>
      <td className="px-2 py-2.5 text-right text-sm tabular-nums text-slate-800">
        {formatSotTotal(p.initial_predicted_total_sot)}
      </td>
      <td className="px-2 py-2.5 text-right text-sm tabular-nums text-slate-800">
        {formatSotTotal(p.official_predicted_total_sot)}
      </td>
      <td className="px-2 py-2.5 text-[11px] leading-snug text-slate-800 break-words">
        {p.initial_suggested_pick ?? '—'}
      </td>
      <td className="px-2 py-2.5 text-right text-sm tabular-nums text-slate-600">
        {formatOdd(p.initial_odd)}
      </td>
      <td className="px-2 py-2.5 text-[11px] leading-snug text-slate-800 break-words">
        {p.official_suggested_pick ?? '—'}
      </td>
      <td className="px-2 py-2.5 text-right text-sm tabular-nums text-slate-600">
        {formatOdd(p.official_odd)}
      </td>
      <td className="px-2 py-2.5 text-right text-[11px] tabular-nums text-slate-800" title={sot.title}>
        {sot.main}
      </td>
      <td className="px-2 py-2.5 text-center">
        <OutcomeCell outcome={p.initial_outcome} />
      </td>
      <td className="px-2 py-2.5 text-center">
        <OutcomeCell outcome={p.official_outcome} />
      </td>
      <td className="px-2 py-2.5 text-center text-[11px] font-medium tabular-nums text-slate-700">
        {p.fixture_status_label}
      </td>
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
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Monitoraggio Giocate</h1>
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
            className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-900 shadow-sm hover:bg-emerald-100 disabled:opacity-50"
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
            className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-900 shadow-sm hover:bg-indigo-50 disabled:opacity-50"
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
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
          <p>
            Nessuna giocata tracciata. Puoi crearle dal turno corrente usando le predizioni già disponibili, oppure
            attendere il job pre-match automatico.
          </p>
        </div>
      ) : (
        <div className="w-full overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-md">
          <table className="w-full table-fixed border-collapse text-left text-sm text-slate-800">
            <colgroup>
              {COL_WIDTHS.map((w, i) => (
                <col key={TABLE_HEADERS[i]} style={{ width: w }} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-b border-slate-200 bg-slate-100">
                {TABLE_HEADERS.map((h) => (
                  <th
                    key={h}
                    className="px-2 py-3 text-[10px] font-bold uppercase leading-tight tracking-wider text-slate-600"
                  >
                    <span className="block whitespace-normal">{h}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p, index) => (
                <DashboardRow key={p.id} p={p} index={index} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
