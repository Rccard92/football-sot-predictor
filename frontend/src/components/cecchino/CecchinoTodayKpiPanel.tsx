import { useCallback, useState } from 'react'
import type { HistoricalReliabilityItem } from '../../lib/cecchinoKpiSignalsApi'
import type {
  CecchinoKpiExplanation,
  CecchinoKpiExplanationsResponse,
  CecchinoKpiV2Panel,
  CecchinoKpiV2Row,
  CecchinoPurchasabilityObservationalItem,
  CecchinoPurchasabilityPreviewItem,
} from '../../lib/cecchinoTodayApi'
import { getKpiExplanations } from '../../lib/cecchinoTodayApi'
import { CecchinoFormulaAuditModal } from './CecchinoFormulaAuditModal'
import {
  edgeClassName,
  fmtKpiCell,
  fmtProbPct,
  fmtRoiPct,
  fmtScoreAcquisto,
  fmtVantaggioProb,
  formatEdgePct,
  historicalReliabilityBadgeClass,
  isKpiPrimaryRow,
  purchasabilityBadgeClass,
  purchasabilityV11BadgeClass,
  ratingBadgeClass,
  vantaggioClassName,
} from './cecchinoKpiUiUtils'

type AnalyzableMetricKey =
  | 'quota_cecchino'
  | 'prob_book'
  | 'prob_cecchino'
  | 'vantaggio_prob'
  | 'edge_pct'
  | 'score_acquisto'
  | 'rating'
  | 'historical_reliability'
  | 'purchasability'
  | 'purchasability_v1_1'
  | 'purchasability_v2'

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
  historicalReliabilityByMarketKey?: Record<string, HistoricalReliabilityItem>
  historicalReliabilityLoading?: boolean
  historicalReliabilityError?: string | null
  purchasabilityByMarketKey?: Record<string, CecchinoPurchasabilityPreviewItem>
  purchasabilityV2ByMarketKey?: Record<string, CecchinoPurchasabilityPreviewItem>
  purchasabilityObservationalV11ByMarketKey?: Record<
    string,
    CecchinoPurchasabilityObservationalItem
  >
  purchasabilityObservationalV2ByMarketKey?: Record<
    string,
    CecchinoPurchasabilityObservationalItem
  >
  todayFixtureId?: number
  providerFixtureId?: number | null
}

function AnalyzableCell({
  active,
  onOpen,
  className,
  children,
  label,
}: {
  active: boolean
  onOpen: () => void
  className?: string
  children: React.ReactNode
  label: string
}) {
  if (!active) {
    return <>{children}</>
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Analizza formula: ${label}`}
      className={`block w-full rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 cursor-pointer hover:bg-white/5 ${className ?? ''}`}
    >
      {children}
    </button>
  )
}

function PurchasabilityCell({
  item,
  observational,
  variant = 'v2',
  ariaPrefix = 'Acquistabilità',
}: {
  item: CecchinoPurchasabilityPreviewItem | undefined
  observational?: CecchinoPurchasabilityObservationalItem
  variant?: 'v1_1' | 'v2'
  ariaPrefix?: string
}) {
  if (!item || item.status === 'unavailable' || item.score == null) {
    return <span className="text-slate-500">—</span>
  }
  const label =
    item.class != null
      ? `${ariaPrefix} ${item.score}, classe ${item.class}`
      : `${ariaPrefix} ${item.score}`
  const badgeFn = variant === 'v1_1' ? purchasabilityV11BadgeClass : purchasabilityBadgeClass

  let subline: string
  if (observational?.status === 'available') {
    const n = observational.sample_size ?? 0
    const roi = observational.roi_pct
    let roiLabel = '—'
    if (roi != null && !Number.isNaN(Number(roi))) {
      const pct = Number(roi)
      const sign = pct > 0 ? '+' : ''
      roiLabel = `${sign}${pct.toFixed(1)}%`
    }
    subline = `${n} casi · ROI ${roiLabel}`
  } else if (observational?.status === 'insufficient_data') {
    subline = 'Campione insufficiente'
  } else {
    subline = 'Non valutato'
  }

  return (
    <span className="text-left" aria-label={`${label}. ${subline}`}>
      <span
        className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[10px] font-semibold tabular-nums ${badgeFn(
          item.class,
          item.calculation_quality,
        )}`}
      >
        {item.score}
      </span>
      <span className="mt-0.5 block text-[9px] text-slate-400">{subline}</span>
    </span>
  )
}

function cohortScopeChip(scope?: HistoricalReliabilityItem['cohort_scope']) {
  if (scope === 'same_competition') {
    return (
      <span className="mt-0.5 inline-block rounded border border-sky-500/40 px-1 py-px text-[8px] font-medium uppercase tracking-wide text-sky-200">
        Campionato
      </span>
    )
  }
  // Chip "Globale" rimosso dalla UI KPI (fallback resta solo nel popover).
  return null
}

function HistoricalReliabilityCell({
  item,
  loading,
  error,
  onOpen,
  interactive = true,
}: {
  item?: HistoricalReliabilityItem
  loading?: boolean
  error?: string | null
  onOpen: () => void
  interactive?: boolean
}) {
  if (loading) {
    return <span className="text-[10px] text-slate-400">Calcolo storico…</span>
  }
  if (error && !item) {
    return <span className="text-[10px] text-slate-400">Affidabilità non disponibile</span>
  }
  if (!item) {
    return <span className="text-slate-500">—</span>
  }

  if (item.status === 'rating_below_scope') {
    return (
      <span
        className="text-left"
        title="L’Affidabilità storica viene calcolata per Rating almeno pari a 50."
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
    const body = (
      <>
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">{n} casi globali</span>
      </>
    )
    if (!interactive) return <span className="text-left">{body}</span>
    return (
      <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
        {body}
      </button>
    )
  }

  if (item.score == null) {
    const body = (
      <>
        <span className="block text-slate-300">—</span>
        <span className="block text-[9px] text-slate-400">{item.class}</span>
      </>
    )
    if (!interactive) return <span className="text-left">{body}</span>
    return (
      <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
        {body}
      </button>
    )
  }

  const body = (
    <>
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${historicalReliabilityBadgeClass(item.class)}`}
      >
        <span className="tabular-nums">{item.score}</span>
        <span className="hidden lg:inline">{item.class}</span>
      </span>
      <span className="mt-0.5 block text-[9px] text-slate-400">
        {item.selected_sample_size ?? item.sample_size ?? 0} casi · ROI {fmtRoiPct(item.roi)}
      </span>
      {cohortScopeChip(item.cohort_scope)}
    </>
  )
  if (!interactive) return <span className="text-left">{body}</span>
  return (
    <button type="button" onClick={onOpen} className="text-left hover:opacity-90">
      {body}
    </button>
  )
}

function HistoricalReliabilityPopover({
  item,
  onClose,
}: {
  item: HistoricalReliabilityItem
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <h4 className="text-sm font-bold text-slate-900">Affidabilità storica</h4>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            Chiudi
          </button>
        </div>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-slate-800">
          <dt className="text-slate-500">Mercato</dt>
          <dd>{item.label || item.selection || item.market_key || '—'}</dd>
          <dt className="text-slate-500">Rating</dt>
          <dd>{item.rating ?? '—'}</dd>
          <dt className="text-slate-500">Fascia</dt>
          <dd>{item.rating_band?.label ?? '—'}</dd>
          <dt className="text-slate-500">Ambito coorte</dt>
          <dd>
            {item.cohort_scope === 'all_competitions_fallback'
              ? 'Globale (fallback)'
              : item.cohort_scope === 'same_competition'
                ? 'Campionato'
                : '—'}
          </dd>
          <dt className="text-slate-500">Casi campionato</dt>
          <dd>{item.local_sample_size ?? '—'}</dd>
          <dt className="text-slate-500">Casi globali</dt>
          <dd>{item.global_sample_size ?? '—'}</dd>
          <dt className="text-slate-500">Casi usati</dt>
          <dd>{item.selected_sample_size ?? item.sample_size ?? '—'}</dd>
          <dt className="text-slate-500">W / L / V</dt>
          <dd>
            {item.wins ?? 0} / {item.losses ?? 0} / {item.voids ?? 0}
          </dd>
          <dt className="text-slate-500">Quota media</dt>
          <dd>{item.average_odds != null ? Number(item.average_odds).toFixed(2) : '—'}</dd>
          <dt className="text-slate-500">Win Rate</dt>
          <dd>{fmtPct(item.win_rate)}</dd>
          <dt className="text-slate-500">Break-even</dt>
          <dd>{fmtPct(item.average_break_even_probability)}</dd>
          <dt className="text-slate-500">Margine</dt>
          <dd>{fmtPp(item.realized_margin)}</dd>
          <dt className="text-slate-500">ROI</dt>
          <dd>{fmtRoiPct(item.roi)}</dd>
          <dt className="text-slate-500">Stabilità</dt>
          <dd>
            {item.positive_periods != null && item.total_periods != null
              ? `${item.positive_periods}/${item.total_periods}`
              : '—'}
          </dd>
          <dt className="text-slate-500">Intervallo storico</dt>
          <dd>
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
          L’Affidabilità storica descrive come si sono comportati in passato lo stesso mercato e la
          stessa fascia Rating. Non rappresenta la nuova Acquistabilità, una probabilità di vittoria
          o uno stake consigliato.
        </p>
      </div>
    </div>
  )
}

function downloadAuditJson(
  payload: CecchinoKpiExplanationsResponse,
  providerFixtureId: number | null | undefined,
) {
  const id = providerFixtureId ?? payload.fixture?.provider_fixture_id ?? 'unknown'
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cecchino-kpi-audit-${id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function CecchinoTodayKpiPanel({
  panel,
  bookmakerStatus,
  historicalReliabilityByMarketKey,
  historicalReliabilityLoading,
  historicalReliabilityError,
  purchasabilityByMarketKey,
  purchasabilityV2ByMarketKey,
  purchasabilityObservationalV11ByMarketKey,
  purchasabilityObservationalV2ByMarketKey,
  todayFixtureId,
  providerFixtureId,
}: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'
  const oddsMeta = panel.odds_meta
  const [openItem, setOpenItem] = useState<HistoricalReliabilityItem | null>(null)
  const [analysisMode, setAnalysisMode] = useState(false)
  const [explanations, setExplanations] = useState<CecchinoKpiExplanationsResponse | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [selectedExplanation, setSelectedExplanation] = useState<CecchinoKpiExplanation | null>(
    null,
  )
  const [analysisFixtureId, setAnalysisFixtureId] = useState(todayFixtureId)

  if (analysisFixtureId !== todayFixtureId) {
    setAnalysisFixtureId(todayFixtureId)
    setAnalysisMode(false)
    setExplanations(null)
    setAnalysisError(null)
    setAnalysisLoading(false)
    setSelectedExplanation(null)
    setOpenItem(null)
  }

  const loadExplanations = useCallback(async (): Promise<CecchinoKpiExplanationsResponse | null> => {
    if (explanations) return explanations
    if (todayFixtureId == null) return null
    setAnalysisLoading(true)
    setAnalysisError(null)
    try {
      const res = await getKpiExplanations(todayFixtureId)
      if (res.status === 'error') {
        setAnalysisError(res.message || res.code || 'Errore caricamento audit KPI')
        return null
      }
      setExplanations(res)
      return res
    } catch (e) {
      setAnalysisError(e instanceof Error ? e.message : 'Errore caricamento audit KPI')
      return null
    } finally {
      setAnalysisLoading(false)
    }
  }, [explanations, todayFixtureId])

  const toggleAnalysis = async () => {
    if (analysisMode) {
      setAnalysisMode(false)
      setSelectedExplanation(null)
      return
    }
    const res = await loadExplanations()
    if (res) setAnalysisMode(true)
  }

  const handleDownload = async () => {
    const res = await loadExplanations()
    if (res) downloadAuditJson(res, providerFixtureId)
  }

  const openMetric = (marketKey: string, metricKey: AnalyzableMetricKey) => {
    const expl = explanations?.markets?.[marketKey]?.[metricKey]
    if (expl) setSelectedExplanation(expl)
  }

  const lookup = (row: CecchinoKpiV2Row) =>
    historicalReliabilityByMarketKey?.[row.market_key] ||
    historicalReliabilityByMarketKey?.[row.segno] ||
    undefined

  const lookupPurch = (row: CecchinoKpiV2Row) =>
    purchasabilityByMarketKey?.[row.market_key] ||
    purchasabilityByMarketKey?.[row.segno] ||
    undefined

  const lookupPurchV2 = (row: CecchinoKpiV2Row) =>
    purchasabilityV2ByMarketKey?.[row.market_key] ||
    purchasabilityV2ByMarketKey?.[row.segno] ||
    undefined

  const lookupObsV11 = (row: CecchinoKpiV2Row) =>
    purchasabilityObservationalV11ByMarketKey?.[row.market_key] ||
    purchasabilityObservationalV11ByMarketKey?.[row.segno] ||
    undefined

  const lookupObsV2 = (row: CecchinoKpiV2Row) =>
    purchasabilityObservationalV2ByMarketKey?.[row.market_key] ||
    purchasabilityObservationalV2ByMarketKey?.[row.segno] ||
    undefined

  return (
    <section className="rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
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
            {analysisError ? (
              <p className="mt-1 text-[10px] text-amber-100 sm:text-xs">{analysisError}</p>
            ) : null}
            {analysisMode ? (
              <p className="mt-1 text-[10px] text-amber-100/90 sm:text-xs">
                Modalità analisi: clicca una metrica per la formula
              </p>
            ) : null}
          </div>
          {todayFixtureId != null ? (
            <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-end">
              <button
                type="button"
                onClick={() => void toggleAnalysis()}
                disabled={analysisLoading}
                className={`rounded-md border px-2.5 py-1 text-[11px] font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 disabled:opacity-60 ${
                  analysisMode
                    ? 'border-amber-200/50 bg-amber-400/20 text-amber-50'
                    : 'border-white/40 bg-white/10 text-white hover:bg-white/20'
                }`}
              >
                {analysisLoading
                  ? 'Caricamento…'
                  : analysisMode
                    ? 'Analisi attiva'
                    : 'ƒx Analisi formule'}
              </button>
              <button
                type="button"
                onClick={() => void handleDownload()}
                disabled={analysisLoading}
                className="rounded-md border border-white/40 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 disabled:opacity-60"
              >
                Scarica audit KPI
              </button>
            </div>
          ) : null}
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

      <div className="hidden bg-[#163352] xl:block">
        <table className="w-full table-fixed border-collapse text-center text-[11px] text-white 2xl:text-xs">
          <colgroup>
            <col className="w-[8%]" />
            <col className="w-[5%]" />
            <col className="w-[5%]" />
            <col className="w-[5%]" />
            <col className="w-[5%]" />
            <col className="w-[6%]" />
            <col className="w-[5%]" />
            <col className="w-[5%]" />
            <col className="w-[9%]" />
            <col className="w-[18%]" />
            <col className="w-[8%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
          </colgroup>
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-slate-400/50 bg-[#0f2847]">
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-300">
                Segno
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Quota Book
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-amber-200">
                Quota Cecchino
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Prob. Book
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Prob. Cecchino
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Vant. Prob.
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Edge
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Score
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Rating
              </th>
              <th className="border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">
                Affidabilità
              </th>
              <th className="border-r border-slate-500/40 px-1 py-2 text-[9px] font-semibold uppercase leading-tight text-slate-300">
                Acq. V1.1
              </th>
              <th className="px-1 py-2 text-[9px] font-semibold uppercase leading-tight text-slate-100">
                Acq. V2
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
              const purch = lookupPurch(row)
              const purchV2 = lookupPurchV2(row)
              const obsV11 = lookupObsV11(row)
              const obsV2 = lookupObsV2(row)
              const mk = row.market_key

              return (
                <tr
                  key={row.market_key}
                  className={`border-b border-slate-600/40 hover:bg-slate-800/25 ${rowBg}`}
                >
                  <td
                    className={`border-r border-slate-500/40 px-1.5 py-2.5 text-left whitespace-nowrap ${labelClass}`}
                  >
                    {segnoLabel}
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums text-slate-100">
                    {fmtKpiCell(row.quota_book, true)}
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap font-semibold tabular-nums text-amber-100">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Quota Cecchino"
                      onOpen={() => openMetric(mk, 'quota_cecchino')}
                    >
                      {fmtKpiCell(row.quota_cecchino, true)}
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums text-slate-100">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Prob. Book"
                      onOpen={() => openMetric(mk, 'prob_book')}
                    >
                      {fmtProbPct(row.prob_book)}
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums text-slate-100">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Prob. Cecchino"
                      onOpen={() => openMetric(mk, 'prob_cecchino')}
                    >
                      {fmtProbPct(row.prob_cecchino)}
                    </AnalyzableCell>
                  </td>
                  <td
                    className={`border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums ${vantaggioClassName(row.vantaggio_prob)}`}
                  >
                    <AnalyzableCell
                      active={analysisMode}
                      label="Vant. Prob."
                      onOpen={() => openMetric(mk, 'vantaggio_prob')}
                    >
                      {fmtVantaggioProb(row.vantaggio_prob)}
                    </AnalyzableCell>
                  </td>
                  <td
                    className={`border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums ${edgeClassName(row.edge_pct)}`}
                  >
                    <AnalyzableCell
                      active={analysisMode}
                      label="Edge"
                      onOpen={() => openMetric(mk, 'edge_pct')}
                    >
                      {formatEdgePct(row.edge_pct)}
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums text-slate-300">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Score"
                      onOpen={() => openMetric(mk, 'score_acquisto')}
                    >
                      {fmtScoreAcquisto(row.score_acquisto)}
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Rating"
                      onOpen={() => openMetric(mk, 'rating')}
                    >
                      {row.rating != null ? (
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                        >
                          <span className="tabular-nums">{row.rating}</span>
                          {row.rating_label && (
                            <span className="hidden 2xl:inline">{row.rating_label}</span>
                          )}
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Affidabilità"
                      onOpen={() => openMetric(mk, 'historical_reliability')}
                    >
                      <HistoricalReliabilityCell
                        item={emp}
                        loading={historicalReliabilityLoading}
                        error={historicalReliabilityError}
                        interactive={!analysisMode}
                        onOpen={() => {
                          if (emp) setOpenItem(emp)
                        }}
                      />
                    </AnalyzableCell>
                  </td>
                  <td className="border-r border-slate-500/40 px-1 py-2.5">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Acquistabilità v1.1"
                      onOpen={() => openMetric(mk, 'purchasability_v1_1')}
                    >
                      <PurchasabilityCell
                        item={purch}
                        observational={obsV11}
                        variant="v1_1"
                        ariaPrefix="Acquistabilità v1.1"
                      />
                    </AnalyzableCell>
                  </td>
                  <td className="px-1 py-2.5">
                    <AnalyzableCell
                      active={analysisMode}
                      label="Acquistabilità v2"
                      onOpen={() => openMetric(mk, 'purchasability_v2')}
                    >
                      <PurchasabilityCell
                        item={purchV2}
                        observational={obsV2}
                        variant="v2"
                        ariaPrefix="Acquistabilità v2"
                      />
                    </AnalyzableCell>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 bg-[#163352] p-3 xl:hidden">
        {(panel.rows || []).map((row) => {
          const segnoLabel = kpiSegnoLabel(row)
          const emp = lookup(row)
          const purch = lookupPurch(row)
          const purchV2 = lookupPurchV2(row)
          const obsV11 = lookupObsV11(row)
          const obsV2 = lookupObsV2(row)
          const mk = row.market_key
          return (
            <article
              key={row.market_key}
              className="rounded-lg border border-slate-500/40 bg-[#1a3d5c]/40 p-3 text-xs text-white"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="break-words font-semibold">{segnoLabel}</span>
                {row.rating != null && (
                  <AnalyzableCell
                    active={analysisMode}
                    label="Rating"
                    onOpen={() => openMetric(mk, 'rating')}
                    className="shrink-0"
                  >
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ratingBadgeClass(row.rating_label)}`}
                    >
                      {row.rating} {row.rating_label}
                    </span>
                  </AnalyzableCell>
                )}
              </div>
              <div className="mb-2">
                <p className="mb-1 text-[10px] uppercase text-slate-400">Affidabilità</p>
                <AnalyzableCell
                  active={analysisMode}
                  label="Affidabilità"
                  onOpen={() => openMetric(mk, 'historical_reliability')}
                >
                  <HistoricalReliabilityCell
                    item={emp}
                    loading={historicalReliabilityLoading}
                    error={historicalReliabilityError}
                    interactive={!analysisMode}
                    onOpen={() => {
                      if (emp) setOpenItem(emp)
                    }}
                  />
                </AnalyzableCell>
              </div>
              <div className="mb-2 space-y-2">
                <div>
                  <p className="mb-1 text-[10px] uppercase text-slate-400">Acquistabilità V1.1</p>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Acquistabilità v1.1"
                    onOpen={() => openMetric(mk, 'purchasability_v1_1')}
                  >
                    <PurchasabilityCell
                      item={purch}
                      observational={obsV11}
                      variant="v1_1"
                      ariaPrefix="Acquistabilità v1.1"
                    />
                  </AnalyzableCell>
                </div>
                <div>
                  <p className="mb-1 text-[10px] uppercase text-slate-300">Acquistabilità V2</p>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Acquistabilità v2"
                    onOpen={() => openMetric(mk, 'purchasability_v2')}
                  >
                    <PurchasabilityCell
                      item={purchV2}
                      observational={obsV2}
                      variant="v2"
                      ariaPrefix="Acquistabilità v2"
                    />
                  </AnalyzableCell>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
                <dt className="text-slate-400">Quota Book</dt>
                <dd>{fmtKpiCell(row.quota_book, true)}</dd>
                <dt className="text-slate-400">Quota Cecchino</dt>
                <dd className="text-amber-100">
                  <AnalyzableCell
                    active={analysisMode}
                    label="Quota Cecchino"
                    onOpen={() => openMetric(mk, 'quota_cecchino')}
                  >
                    {fmtKpiCell(row.quota_cecchino, true)}
                  </AnalyzableCell>
                </dd>
                <dt className="text-slate-400">Prob. Book</dt>
                <dd>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Prob. Book"
                    onOpen={() => openMetric(mk, 'prob_book')}
                  >
                    {fmtProbPct(row.prob_book)}
                  </AnalyzableCell>
                </dd>
                <dt className="text-slate-400">Prob. Cecchino</dt>
                <dd>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Prob. Cecchino"
                    onOpen={() => openMetric(mk, 'prob_cecchino')}
                  >
                    {fmtProbPct(row.prob_cecchino)}
                  </AnalyzableCell>
                </dd>
                <dt className="text-slate-400">Vant. Prob.</dt>
                <dd className={vantaggioClassName(row.vantaggio_prob)}>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Vant. Prob."
                    onOpen={() => openMetric(mk, 'vantaggio_prob')}
                  >
                    {fmtVantaggioProb(row.vantaggio_prob)}
                  </AnalyzableCell>
                </dd>
                <dt className="text-slate-400">Edge</dt>
                <dd className={edgeClassName(row.edge_pct)}>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Edge"
                    onOpen={() => openMetric(mk, 'edge_pct')}
                  >
                    {formatEdgePct(row.edge_pct)}
                  </AnalyzableCell>
                </dd>
                <dt className="text-slate-400">Score</dt>
                <dd>
                  <AnalyzableCell
                    active={analysisMode}
                    label="Score"
                    onOpen={() => openMetric(mk, 'score_acquisto')}
                  >
                    {fmtScoreAcquisto(row.score_acquisto)}
                  </AnalyzableCell>
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

      {!analysisMode && openItem ? (
        <HistoricalReliabilityPopover item={openItem} onClose={() => setOpenItem(null)} />
      ) : null}
      {selectedExplanation ? (
        <CecchinoFormulaAuditModal
          explanation={selectedExplanation}
          onClose={() => setSelectedExplanation(null)}
        />
      ) : null}
    </section>
  )
}
