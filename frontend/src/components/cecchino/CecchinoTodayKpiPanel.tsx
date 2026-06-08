import { useState } from 'react'
import type { CecchinoKpiV2Panel, CecchinoKpiV2Row, CecchinoOddsMeta } from '../../lib/cecchinoTodayApi'
import {
  getBetfairMarketsJson,
  getCecchinoKpiDebugJson,
  refreshBetfairOdds,
} from '../../lib/cecchinoTodayApi'
import {
  edgeClassName,
  fmtKpiCell,
  fmtProbPct,
  fmtScoreAcquisto,
  fmtVantaggioProb,
  formatEdgePct,
  isKpiPrimaryRow,
  ratingBadgeClass,
  vantaggioClassName,
} from './cecchinoKpiUiUtils'

function kpiSegnoLabel(row: CecchinoKpiV2Row): string {
  return row.segno || row.label || row.market_key
}

function fmtOddsTimestamp(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'medium' })
  } catch {
    return iso
  }
}

type Props = {
  panel: CecchinoKpiV2Panel
  bookmakerStatus?: string
  todayFixtureId?: number
  providerFixtureId?: number
  onKpiPanelUpdate?: (panel: CecchinoKpiV2Panel, oddsMeta?: CecchinoOddsMeta) => void
}

export function CecchinoTodayKpiPanel({
  panel,
  bookmakerStatus,
  todayFixtureId,
  providerFixtureId,
  onKpiPanelUpdate,
}: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'
  const oddsMeta = panel.odds_meta
  const [jsonBusy, setJsonBusy] = useState(false)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [marketsBusy, setMarketsBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [actionMsgTone, setActionMsgTone] = useState<'ok' | 'warn' | 'err'>('ok')

  function setMsg(text: string, tone: 'ok' | 'warn' | 'err' = 'ok') {
    setActionMsg(text)
    setActionMsgTone(tone)
  }

  async function fetchDebugJson() {
    if (!todayFixtureId) return null
    return getCecchinoKpiDebugJson(todayFixtureId)
  }

  async function handleDownloadJson() {
    if (!todayFixtureId || !providerFixtureId) return
    setJsonBusy(true)
    setActionMsg(null)
    try {
      const data = await fetchDebugJson()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cecchino-kpi-betfair-${providerFixtureId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setMsg('Download non riuscito', 'err')
    } finally {
      setJsonBusy(false)
    }
  }

  async function handleCopyJson() {
    if (!todayFixtureId) return
    setJsonBusy(true)
    setActionMsg(null)
    try {
      const data = await fetchDebugJson()
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2))
      setMsg('JSON KPI copiato')
    } catch {
      setMsg('Copia non riuscita', 'err')
    } finally {
      setJsonBusy(false)
    }
  }

  async function handleRefreshOdds() {
    if (!todayFixtureId) return
    setRefreshBusy(true)
    setActionMsg(null)
    try {
      const res = await refreshBetfairOdds(todayFixtureId, { force: true, rebuild_kpi: true })
      if (res.status === 'budget_blocked') {
        setMsg(res.message ?? 'Budget API bloccato', 'warn')
        return
      }
      if (res.status !== 'ok') {
        setMsg(res.message ?? 'Refresh non riuscito', 'err')
        return
      }
      if (res.kpi_panel) {
        onKpiPanelUpdate?.(res.kpi_panel, res.bookmaker ?? res.kpi_panel.odds_meta)
      }
      if (res.changed) {
        const mkts = (res.changed_markets ?? []).join(', ')
        setMsg(`Quote aggiornate (${mkts || '1X2'})`)
      } else {
        setMsg('Nessuna variazione sul feed API-Football', 'warn')
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Errore refresh quote', 'err')
    } finally {
      setRefreshBusy(false)
    }
  }

  async function handleDownloadMarkets() {
    if (!todayFixtureId || !providerFixtureId) return
    setMarketsBusy(true)
    setActionMsg(null)
    try {
      const data = await getBetfairMarketsJson(todayFixtureId, true)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `betfair-markets-${providerFixtureId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setMsg('Download mercati non riuscito', 'err')
    } finally {
      setMarketsBusy(false)
    }
  }

  async function handleCopyMarkets() {
    if (!todayFixtureId) return
    setMarketsBusy(true)
    setActionMsg(null)
    try {
      const data = await getBetfairMarketsJson(todayFixtureId, true)
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2))
      setMsg('JSON mercati copiato')
    } catch {
      setMsg('Copia mercati non riuscita', 'err')
    } finally {
      setMarketsBusy(false)
    }
  }

  const msgClass =
    actionMsgTone === 'err'
      ? 'text-red-200'
      : actionMsgTone === 'warn'
        ? 'text-amber-200'
        : 'text-emerald-200'

  const anyBusy = jsonBusy || refreshBusy || marketsBusy

  return (
    <section className="rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1 text-center sm:text-left">
            <h3 className="text-sm font-bold tracking-wide text-white sm:text-base">PANNELLO KPI</h3>
            <p className="mt-1 text-[10px] text-slate-300 sm:text-xs">
              Bookmaker: {panel.bookmaker?.name ?? 'Betfair'}
            </p>
            {status === 'not_available' && (
              <p className="mt-1 text-[10px] text-amber-100 sm:text-xs">
                Quote Betfair non disponibili
              </p>
            )}
          </div>
          {todayFixtureId != null && providerFixtureId != null && (
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
              <button
                type="button"
                disabled={anyBusy}
                onClick={() => void handleRefreshOdds()}
                className="rounded-md border border-emerald-500/50 bg-emerald-900/40 px-2 py-1 text-[10px] font-medium text-emerald-100 hover:bg-emerald-800/50 disabled:opacity-50 sm:text-xs"
              >
                {refreshBusy ? 'Aggiornamento…' : 'Aggiorna quote Betfair'}
              </button>
              <button
                type="button"
                disabled={anyBusy}
                onClick={() => void handleDownloadMarkets()}
                className="rounded-md border border-slate-500/60 bg-slate-800/50 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700/60 disabled:opacity-50 sm:text-xs"
              >
                Scarica mercati Betfair
              </button>
              <button
                type="button"
                disabled={anyBusy}
                onClick={() => void handleCopyMarkets()}
                className="rounded-md border border-slate-500/60 bg-slate-800/50 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700/60 disabled:opacity-50 sm:text-xs"
              >
                Copia JSON mercati
              </button>
              <button
                type="button"
                disabled={anyBusy}
                onClick={() => void handleDownloadJson()}
                className="rounded-md border border-slate-500/60 bg-slate-800/50 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700/60 disabled:opacity-50 sm:text-xs"
              >
                Scarica JSON KPI
              </button>
              <button
                type="button"
                disabled={anyBusy}
                onClick={() => void handleCopyJson()}
                className="rounded-md border border-slate-500/60 bg-slate-800/50 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700/60 disabled:opacity-50 sm:text-xs"
              >
                Copia JSON KPI
              </button>
            </div>
          )}
        </div>
        {actionMsg && <p className={`mt-1 text-right text-[10px] ${msgClass}`}>{actionMsg}</p>}
        {oddsMeta && (
          <div className="mt-2 rounded-md border border-slate-500/30 bg-slate-900/30 px-2 py-1.5 text-[10px] text-slate-300 sm:text-xs">
            <p>
              Ultimo refresh Betfair:{' '}
              <span className="text-slate-100">
                {fmtOddsTimestamp(oddsMeta.last_betfair_refresh_at ?? oddsMeta.odds_fetched_at)}
              </span>
            </p>
            <p className="mt-0.5">
              source: <span className="text-slate-100">{oddsMeta.odds_source ?? '—'}</span>
              {' · '}
              bookmaker_id:{' '}
              <span className="text-slate-100">
                {panel.bookmaker?.provider_bookmaker_id ?? 3}
              </span>
              {' · '}
              is_cached:{' '}
              <span className="text-slate-100">
                {oddsMeta.is_cached == null ? '—' : String(oddsMeta.is_cached)}
              </span>
            </p>
          </div>
        )}
      </div>

      <div className="hidden bg-[#163352] md:block">
        <table className="w-full table-fixed border-collapse text-center text-xs text-white sm:text-[13px]">
          <colgroup>
            <col className="w-[12%]" />
            <col className="w-[9%]" />
            <col className="w-[9%]" />
            <col className="w-[8%]" />
            <col className="w-[8%]" />
            <col className="w-[9%]" />
            <col className="w-[8%]" />
            <col className="w-[9%]" />
            <col className="w-[18%]" />
          </colgroup>
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-slate-400/50 bg-[#0f2847]">
              <th className="border-r border-slate-500/40 px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-300 sm:text-xs">
                Segno
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Quota Book
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-amber-200 sm:text-xs">
                Quota Cecch.
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Prob. Book
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Prob. Cecch.
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Vant. Prob.
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Edge %
              </th>
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Score
              </th>
              <th className="px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Rating
              </th>
            </tr>
          </thead>
          <tbody>
            {(panel.rows || []).map((row) => {
              const segnoLabel = kpiSegnoLabel(row)
              const primary = isKpiPrimaryRow(segnoLabel)
              const rowBg = primary ? 'bg-[#1a3d5c]/60' : 'bg-transparent'
              const labelClass = primary
                ? 'font-bold text-white'
                : 'font-medium text-slate-300'

              return (
                <tr
                  key={row.market_key}
                  className={`border-b border-slate-600/40 hover:bg-slate-800/25 ${rowBg}`}
                >
                  <td
                    className={`border-r border-slate-500/40 px-2 py-2.5 text-left whitespace-nowrap ${labelClass}`}
                  >
                    {segnoLabel}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 tabular-nums text-slate-100">
                    {fmtKpiCell(row.quota_book, true)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 font-semibold tabular-nums text-amber-100">
                    {fmtKpiCell(row.quota_cecchino, true)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 tabular-nums text-slate-100">
                    {fmtProbPct(row.prob_book)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 tabular-nums text-slate-100">
                    {fmtProbPct(row.prob_cecchino)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-2 py-2.5 tabular-nums ${vantaggioClassName(row.vantaggio_prob)}`}>
                    {fmtVantaggioProb(row.vantaggio_prob)}
                  </td>
                  <td className={`border-r border-slate-500/40 px-2 py-2.5 tabular-nums ${edgeClassName(row.edge_pct)}`}>
                    {formatEdgePct(row.edge_pct)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 tabular-nums text-slate-300">
                    {fmtScoreAcquisto(row.score_acquisto)}
                  </td>
                  <td className="px-2 py-2.5">
                    {row.rating != null ? (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                      >
                        <span className="tabular-nums">{row.rating}</span>
                        {row.rating_label && (
                          <span className="hidden lg:inline">{row.rating_label}</span>
                        )}
                      </span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 bg-[#163352] p-3 md:hidden">
        {(panel.rows || []).map((row) => {
          const segnoLabel = kpiSegnoLabel(row)
          return (
            <article
              key={row.market_key}
              className="rounded-lg border border-slate-500/40 bg-[#1a3d5c]/40 p-3 text-xs text-white"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="break-words font-semibold">{segnoLabel}</span>
                {row.rating != null && (
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                  >
                    {row.rating} {row.rating_label}
                  </span>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
                <dt className="text-slate-400">Quota Book</dt>
                <dd>{fmtKpiCell(row.quota_book, true)}</dd>
                <dt className="text-slate-400">Quota Cecchino</dt>
                <dd className="text-amber-100">{fmtKpiCell(row.quota_cecchino, true)}</dd>
                <dt className="text-slate-400">Edge %</dt>
                <dd className={edgeClassName(row.edge_pct)}>{formatEdgePct(row.edge_pct)}</dd>
                <dt className="text-slate-400">Vant. Prob.</dt>
                <dd className={vantaggioClassName(row.vantaggio_prob)}>
                  {fmtVantaggioProb(row.vantaggio_prob)}
                </dd>
              </dl>
            </article>
          )
        })}
      </div>

      {(panel.warnings ?? []).length > 0 && (
        <div className="border-t border-slate-500/40 bg-[#0f2847] px-4 py-3 text-xs text-amber-200">
          <ul className="list-disc space-y-1 pl-4">
            {(panel.warnings ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
