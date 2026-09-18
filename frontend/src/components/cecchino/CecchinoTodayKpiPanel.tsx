import { useCallback, useState } from 'react'
import type {
  CecchinoKpiExplanation,
  CecchinoKpiExplanationsResponse,
  CecchinoKpiV2Panel,
  CecchinoKpiV2Row,
} from '../../lib/cecchinoTodayApi'
import { getKpiExplanations } from '../../lib/cecchinoTodayApi'
import { CecchinoFormulaAuditModal } from './CecchinoFormulaAuditModal'
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

export type AnalyzableMetricKey =
  | 'quota_cecchino'
  | 'prob_book'
  | 'prob_cecchino'
  | 'vantaggio_prob'
  | 'edge_pct'
  | 'score_acquisto'
  | 'rating'
  | 'historical_reliability'

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
  todayFixtureId,
  providerFixtureId,
}: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'
  const oddsMeta = panel.odds_meta
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

  return (
    <section className="rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="text-center sm:text-left">
            <h3 className="text-sm font-bold tracking-wide text-white sm:text-base">PANNELLO KPI</h3>
            <p className="mt-1 text-[10px] text-slate-300 sm:text-xs">
              Book · {panel.bookmaker?.policy_label ?? 'Betfair primario · Bet365 fallback'}
            </p>
            {status === 'not_available' && (
              <p className="mt-1 text-[10px] text-amber-100 sm:text-xs">
                Quote Book non disponibili
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
              Ultimo refresh Book:{' '}
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
            <col className="w-[14%]" />
            <col className="w-[10%]" />
            <col className="w-[11%]" />
            <col className="w-[10%]" />
            <col className="w-[11%]" />
            <col className="w-[11%]" />
            <col className="w-[10%]" />
            <col className="w-[9%]" />
            <col className="w-[14%]" />
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
                          label={`${segnoLabel} · Quota Cecchino`}
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
                    </tr>
                  )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 bg-[#163352] p-3 xl:hidden">
        {(panel.rows || []).map((row) => {
          const segnoLabel = kpiSegnoLabel(row)
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
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
                <dt className="text-slate-400">Quota Book</dt>
                <dd>{fmtKpiCell(row.quota_book, true)}</dd>
                <dt className="text-slate-400">Quota Cecchino</dt>
                <dd className="text-amber-100">
                  <AnalyzableCell
                    active={analysisMode}
                    label={`${segnoLabel} · Quota Cecchino`}
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

      {selectedExplanation ? (
        <CecchinoFormulaAuditModal
          explanation={selectedExplanation}
          onClose={() => setSelectedExplanation(null)}
        />
      ) : null}
    </section>
  )
}
