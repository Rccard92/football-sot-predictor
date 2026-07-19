import { useState } from 'react'
import type { EmpiricalPurchasabilityItem } from '../../lib/cecchinoKpiSignalsApi'
import type { CecchinoKpiV2Panel, CecchinoKpiV2Row } from '../../lib/cecchinoTodayApi'
import {
  edgeClassName,
  fmtKpiCell,
  fmtProbPct,
  fmtRoiPct,
  fmtScoreAcquisto,
  fmtVantaggioProb,
  formatEdgePct,
  isKpiPrimaryRow,
  purchasabilityBadgeClass,
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

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(digits)}%`
}

function fmtPp(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const pts = Number(v) * 100
  const sign = pts > 0 ? '+' : ''
  return `${sign}${pts.toFixed(1)} pp`
}

type Props = {
  panel: CecchinoKpiV2Panel
  bookmakerStatus?: string
  purchasabilityByMarketKey?: Record<string, EmpiricalPurchasabilityItem>
  purchasabilityLoading?: boolean
  purchasabilityError?: string | null
}

function cohortScopeChip(scope?: EmpiricalPurchasabilityItem['cohort_scope']) {
  if (scope === 'same_competition') {
    return (
      <span className="mt-0.5 inline-block rounded border border-sky-500/40 px-1 py-px text-[8px] font-medium uppercase tracking-wide text-sky-200">
        Campionato
      </span>
    )
  }
  if (scope === 'all_competitions_fallback') {
    return (
      <span className="mt-0.5 inline-block rounded border border-amber-500/40 px-1 py-px text-[8px] font-medium uppercase tracking-wide text-amber-200">
        Globale
      </span>
    )
  }
  return null
}

function PurchasabilityCell({
  item,
  loading,
  error,
  onOpen,
}: {
  item?: EmpiricalPurchasabilityItem
  loading?: boolean
  error?: string | null
  onOpen: () => void
}) {
  if (loading) {
    return <span className="text-[10px] text-slate-400">Calcolo storico…</span>
  }
  if (error && !item) {
    return <span className="text-[10px] text-slate-400">Acquistabilità non disponibile</span>
  }
  if (!item) {
    return <span className="text-slate-500">—</span>
  }

  if (item.status === 'rating_below_scope') {
    return (
      <span
        className="text-left"
        title="L’Acquistabilità viene calcolata per Rating almeno pari a 50."
      >
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">Non valutato</span>
      </span>
    )
  }

  if (item.status === 'unsupported_market') {
    return (
      <span className="text-left" title={item.unsupported_reason || item.explanation || undefined}>
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">Non disponibile</span>
      </span>
    )
  }

  if (item.status === 'insufficient_data') {
    const n =
      item.global_sample_size ?? item.selected_sample_size ?? item.sample_size ?? 0
    return (
      <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">{n} casi globali</span>
      </button>
    )
  }

  if (item.score == null) {
    return (
      <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">{item.class}</span>
      </button>
    )
  }

  return (
    <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${purchasabilityBadgeClass(item.class)}`}
      >
        <span className="tabular-nums">{item.score}</span>
        <span className="hidden lg:inline">{item.class}</span>
      </span>
      <span className="mt-0.5 block text-[9px] text-slate-400">
        {item.selected_sample_size ?? item.sample_size ?? 0} casi · ROI {fmtRoiPct(item.roi)}
      </span>
      {cohortScopeChip(item.cohort_scope)}
    </button>
  )
}

function PurchasabilityPopover({
  item,
  onClose,
}: {
  item: EmpiricalPurchasabilityItem
  onClose: () => void
}) {
  const band = item.rating_band
  const scopeLabel =
    item.cohort_scope === 'same_competition'
      ? 'Campionato'
      : item.cohort_scope === 'all_competitions_fallback'
        ? 'Globale (fallback)'
        : '—'
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-800 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <h4 className="font-semibold text-slate-900">Acquistabilità empirica</h4>
          <button type="button" className="text-slate-500 hover:text-slate-800" onClick={onClose}>
            Chiudi
          </button>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
          <dt className="text-slate-500">Mercato</dt>
          <dd>{item.label || item.selection || item.market_key || '—'}</dd>
          <dt className="text-slate-500">Rating attuale</dt>
          <dd>{item.rating ?? '—'}</dd>
          <dt className="text-slate-500">Fascia Rating</dt>
          <dd>{band?.label ?? '—'}</dd>
          <dt className="text-slate-500">Ambito coorte</dt>
          <dd>{scopeLabel}</dd>
          <dt className="text-slate-500">Casi campionato</dt>
          <dd>{item.local_sample_size ?? '—'}</dd>
          <dt className="text-slate-500">Casi globali</dt>
          <dd>{item.global_sample_size ?? '—'}</dd>
          <dt className="text-slate-500">Campione usato</dt>
          <dd>{item.selected_sample_size ?? item.sample_size ?? 0}</dd>
          <dt className="text-slate-500">Competizioni in coorte</dt>
          <dd>{item.competition_count ?? '—'}</dd>
          <dt className="text-slate-500">W / L / V</dt>
          <dd>
            {item.wins ?? 0} / {item.losses ?? 0} / {item.voids ?? 0}
          </dd>
          <dt className="text-slate-500">Quota media</dt>
          <dd>{item.average_odds != null ? Number(item.average_odds).toFixed(2) : '—'}</dd>
          <dt className="text-slate-500">Win Rate</dt>
          <dd>{fmtPct(item.win_rate)}</dd>
          <dt className="text-slate-500">Break-even medio</dt>
          <dd>{fmtPct(item.average_break_even_probability)}</dd>
          <dt className="text-slate-500">Margine realizzato</dt>
          <dd>{fmtPp(item.realized_margin)}</dd>
          <dt className="text-slate-500">ROI</dt>
          <dd>{fmtRoiPct(item.roi)}</dd>
          <dt className="text-slate-500">Stabilità (periodi +)</dt>
          <dd>
            {item.positive_periods != null && item.total_periods != null
              ? `${item.positive_periods} / ${item.total_periods}`
              : '—'}
          </dd>
          <dt className="text-slate-500">Intervallo storico</dt>
          <dd className="text-[11px]">
            {item.historical_date_from ?? '—'} → {item.historical_date_to ?? '—'}
          </dd>
          <dt className="text-slate-500">Score / classe</dt>
          <dd>
            {item.score ?? '—'} · {item.class}
          </dd>
        </dl>
        {item.explanation ? (
          <p className="mt-3 text-xs text-slate-700">{item.explanation}</p>
        ) : null}
        <p className="mt-3 rounded-md bg-slate-50 px-2 py-2 text-[11px] leading-snug text-slate-600">
          L’Acquistabilità descrive il comportamento storico di Rating simili sullo stesso mercato.
          Non rappresenta una probabilità di vittoria né uno stake consigliato. Lo storico globale
          si usa solo se il campionato non ha abbastanza casi.
        </p>
      </div>
    </div>
  )
}

export function CecchinoTodayKpiPanel({
  panel,
  bookmakerStatus,
  purchasabilityByMarketKey,
  purchasabilityLoading,
  purchasabilityError,
}: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'
  const oddsMeta = panel.odds_meta
  const [openItem, setOpenItem] = useState<EmpiricalPurchasabilityItem | null>(null)

  const lookup = (row: CecchinoKpiV2Row) =>
    purchasabilityByMarketKey?.[row.market_key] ||
    purchasabilityByMarketKey?.[row.segno] ||
    undefined

  return (
    <section className="rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3">
        <div className="text-center sm:text-left">
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

      <div className="hidden bg-[#163352] md:block overflow-x-auto">
        <table className="w-full table-fixed border-collapse text-center text-xs text-white sm:text-[13px] min-w-[900px]">
          <colgroup>
            <col className="w-[11%]" />
            <col className="w-[8%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
            <col className="w-[8%]" />
            <col className="w-[12%]" />
            <col className="w-[14%]" />
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
              <th className="border-r border-slate-500/40 px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Rating
              </th>
              <th className="px-2 py-2 text-[10px] font-semibold uppercase text-slate-200 sm:text-xs">
                Acquistabilità
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
              const emp = lookup(row)

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
                  <td
                    className={`border-r border-slate-500/40 px-2 py-2.5 tabular-nums ${vantaggioClassName(row.vantaggio_prob)}`}
                  >
                    {fmtVantaggioProb(row.vantaggio_prob)}
                  </td>
                  <td
                    className={`border-r border-slate-500/40 px-2 py-2.5 tabular-nums ${edgeClassName(row.edge_pct)}`}
                  >
                    {formatEdgePct(row.edge_pct)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5 tabular-nums text-slate-300">
                    {fmtScoreAcquisto(row.score_acquisto)}
                  </td>
                  <td className="border-r border-slate-500/40 px-2 py-2.5">
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
                  <td className="px-2 py-2.5">
                    <PurchasabilityCell
                      item={emp}
                      loading={purchasabilityLoading}
                      error={purchasabilityError}
                      onOpen={() => emp && setOpenItem(emp)}
                    />
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
          const emp = lookup(row)
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
              <div className="mb-2">
                <p className="mb-1 text-[10px] uppercase text-slate-400">Acquistabilità</p>
                <PurchasabilityCell
                  item={emp}
                  loading={purchasabilityLoading}
                  error={purchasabilityError}
                  onOpen={() => emp && setOpenItem(emp)}
                />
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

      {openItem ? (
        <PurchasabilityPopover item={openItem} onClose={() => setOpenItem(null)} />
      ) : null}
    </section>
  )
}
