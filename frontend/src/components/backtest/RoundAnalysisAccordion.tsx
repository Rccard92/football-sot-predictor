import { useCallback, useEffect, useState } from 'react'
import {
  deleteRoundAnalysis,
  getRoundAnalysisDetail,
  getRoundAnalyses,
  getRoundAnalysisVersions,
  postRoundAnalysisRecalculate,
  type RoundAnalysisDetail,
  type RoundAnalysisListItem,
  type RoundAnalysisOverviewRound,
  type RoundAnalysisVersionsResponse,
  type RoundOverviewModelChip,
} from '../../lib/api'
import { RoundAnalysisDeleteConfirm } from './RoundAnalysisDeleteConfirm'
import {
  dataQualityBadgeClass,
  errorCodeLabelIt,
  hitRateBadgeClass,
  modelDisplayBadgeClass,
  statusLabelIt,
} from './roundAnalysisUtils'

type Props = {
  competitionId: number | null
  seasonYear: number
  selectedId: number | null
  onSelect: (detail: RoundAnalysisDetail) => void
  onDeleted: (analysisId: number) => void
  onReloadList?: () => void
  reloadToken: number
  overviewRounds?: RoundAnalysisOverviewRound[]
}

const MODEL_CHIP_ORDER = [
  { key: 'baseline_v1_1_sot', label: 'v1.1' },
  { key: 'baseline_v2_0_lineup_impact', label: 'v2.0' },
  { key: 'baseline_v2_1_weighted_components', label: 'v2.1' },
  { key: 'baseline_v3_0_sot_value_selector', label: 'v3.0' },
] as const

function chipsFromItem(
  item: RoundAnalysisListItem,
  overviewRound?: RoundAnalysisOverviewRound,
): Record<string, RoundOverviewModelChip> | null {
  if (overviewRound?.models && Object.keys(overviewRound.models).length > 0) {
    return overviewRound.models
  }
  if (item.model_chips && Object.keys(item.model_chips).length > 0) {
    return item.model_chips
  }
  return null
}

function completenessForItem(
  item: RoundAnalysisListItem,
  overviewRound?: RoundAnalysisOverviewRound,
): 'ok' | 'stale' | 'empty' | null | undefined {
  return overviewRound?.completeness ?? item.completeness
}

function staleMessageForItem(
  item: RoundAnalysisListItem,
  overviewRound?: RoundAnalysisOverviewRound,
): string | null | undefined {
  return (
    overviewRound?.stale_message ??
    item.stale_message ??
    'Analisi creata con una versione precedente o risultati incompleti.'
  )
}

function accordionModelLine(item: RoundAnalysisListItem): string {
  const s = item.accordion_summary
  if (!s) return ''
  const parts = ['v1.1', 'v2.0', 'v2.1', 'v3.0'].map((k) => {
    const v = s[k]
    return v ? `${k}: ${v}` : null
  }).filter(Boolean)
  return parts.join(' · ')
}

export function RoundAnalysisAccordion({
  competitionId,
  seasonYear,
  selectedId,
  onSelect,
  onDeleted,
  onReloadList,
  reloadToken,
  overviewRounds,
}: Props) {
  const [items, setItems] = useState<RoundAnalysisListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<RoundAnalysisListItem | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [recalculatingId, setRecalculatingId] = useState<number | null>(null)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [versionsError, setVersionsError] = useState<string | null>(null)
  const [versionsData, setVersionsData] = useState<RoundAnalysisVersionsResponse | null>(null)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    try {
      const res = await getRoundAnalyses(competitionId, seasonYear, {
        limit: 50,
        sortBy: 'round_number',
        sortDir: 'desc',
        latestOnlyPerRound: true,
      })
      setItems(res.items)
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const open = async (id: number) => {
    const detail = await getRoundAnalysisDetail(id)
    onSelect(detail)
  }

  const recalculate = async (item: RoundAnalysisListItem) => {
    setRecalculatingId(item.id)
    setErrorMessage(null)
    try {
      const { analysis } = await postRoundAnalysisRecalculate(item.id)
      onSelect(analysis)
      onReloadList?.()
      setSuccessMessage(`Giornata ${item.round_number} ricalcolata (v${analysis.analysis_version}).`)
      window.setTimeout(() => setSuccessMessage(null), 4000)
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : String(e))
    } finally {
      setRecalculatingId(null)
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    setErrorMessage(null)
    try {
      await deleteRoundAnalysis(pendingDelete.id)
      setItems((prev) => prev.filter((i) => i.id !== pendingDelete.id))
      onDeleted(pendingDelete.id)
      setSuccessMessage('Analisi eliminata correttamente.')
      setPendingDelete(null)
      window.setTimeout(() => setSuccessMessage(null), 4000)
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : String(e))
    } finally {
      setDeleting(false)
    }
  }

  const openVersions = async (item: RoundAnalysisListItem) => {
    if (competitionId == null) return
    setVersionsOpen(true)
    setVersionsLoading(true)
    setVersionsError(null)
    setVersionsData(null)
    try {
      const data = await getRoundAnalysisVersions(competitionId, seasonYear, item.round_number)
      setVersionsData(data)
    } catch (e) {
      setVersionsError(e instanceof Error ? e.message : String(e))
    } finally {
      setVersionsLoading(false)
    }
  }

  if (competitionId == null) return null

  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-slate-900">Giornate analizzate</h2>
      {successMessage ? (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{successMessage}</p>
      ) : null}
      {errorMessage ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">{errorMessage}</p>
      ) : null}
      {loading ? <p className="text-sm text-slate-500">Caricamento…</p> : null}
      {!loading && items.length === 0 ? (
        <p className="text-sm text-slate-500">Nessuna analisi salvata per questa stagione.</p>
      ) : null}
      <div className="space-y-2">
        {items.map((item) => {
          const active = selectedId === item.id
          const modelLine = accordionModelLine(item)
          const overviewRound = overviewRounds?.find(
            (r) => r.analysis_id === item.id || r.round_number === item.round_number,
          )
          const chips = chipsFromItem(item, overviewRound)
          const completeness = completenessForItem(item, overviewRound)
          const isStale = completeness === 'stale' || completeness === 'empty'
          const motive = item.accordion_summary?.motive
          const isFailed = item.status === 'failed'
          return (
            <div
              key={item.id}
              className={`rounded-xl border ${
                isFailed
                  ? 'border-rose-200 bg-rose-50/40'
                  : isStale
                    ? 'border-amber-200 bg-amber-50/30'
                    : active
                      ? 'border-slate-400 bg-slate-50'
                      : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex w-full flex-col gap-1 px-4 py-3">
                <div className="flex w-full items-start justify-between gap-3">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => void open(item.id)}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">
                        Giornata {item.round_number}
                      </span>
                      <span className="text-xs text-slate-500">
                        {item.total_fixtures} partite · v{item.analysis_version}
                      </span>
                    </div>
                  </button>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs">
                    {isStale ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-900">
                        Da ricalcolare
                      </span>
                    ) : (
                      <span
                        className={`rounded-full px-2 py-0.5 ${dataQualityBadgeClass(item.data_quality_badge)}`}
                      >
                        {item.data_quality_badge ?? '—'}
                      </span>
                    )}
                    <span className="text-slate-600">
                      {item.status_label ?? statusLabelIt(item.status)}
                    </span>
                    {isStale ? (
                      <button
                        type="button"
                        disabled={recalculatingId === item.id}
                        className="rounded-lg border border-amber-300 px-2 py-1 text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                        onClick={(e) => {
                          e.stopPropagation()
                          void recalculate(item)
                        }}
                      >
                        {recalculatingId === item.id ? 'Ricalcolo…' : 'Ricalcola'}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="rounded-lg border border-slate-200 px-2 py-1 text-slate-800 hover:bg-slate-50"
                      onClick={(e) => {
                        e.stopPropagation()
                        void openVersions(item)
                      }}
                    >
                      Versioni
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-rose-200 px-2 py-1 text-rose-800 hover:bg-rose-50"
                      onClick={(e) => {
                        e.stopPropagation()
                        setPendingDelete(item)
                        setErrorMessage(null)
                      }}
                    >
                      Elimina
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => void open(item.id)}
                >
                  {chips ? (
                    <div className="flex flex-wrap gap-2">
                      {MODEL_CHIP_ORDER.map(({ key, label }) => {
                        const chip = chips[key]
                        if (!chip) return null
                        return (
                          <span key={key} className="text-xs text-slate-700">
                            <span className="font-medium">{label}</span>{' '}
                            <span
                              className={`rounded px-1 py-0.5 ${hitRateBadgeClass(chip.cautious_hit_rate)}`}
                            >
                              {chip.cautious_display}
                            </span>{' '}
                            <span
                              className={`rounded px-1 py-0.5 ${hitRateBadgeClass(chip.aggressive_hit_rate)}`}
                            >
                              {chip.aggressive_display}
                            </span>
                          </span>
                        )
                      })}
                    </div>
                  ) : modelLine ? (
                    <p className="text-xs text-slate-600">{modelLine}</p>
                  ) : null}
                  {isStale ? (
                    <p className="mt-1 text-xs text-amber-800">{staleMessageForItem(item, overviewRound)}</p>
                  ) : null}
                  {motive ? (
                    <p className="text-xs text-amber-800">Motivo: {motive}</p>
                  ) : item.status_reason ? (
                    <p className="text-xs text-amber-800">Motivo: {item.status_reason}</p>
                  ) : null}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-slate-500">
        Mostriamo solo l’ultima versione di ogni giornata. Le versioni precedenti restano consultabili nello storico.
      </p>

      {pendingDelete ? (
        <RoundAnalysisDeleteConfirm
          roundNumber={pendingDelete.round_number}
          deleting={deleting}
          onCancel={() => {
            if (!deleting) setPendingDelete(null)
          }}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}

      {versionsOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setVersionsOpen(false)}
        >
          <div
            className="w-full max-w-2xl rounded-xl bg-white p-4 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Versioni</h3>
                {versionsData ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Giornata {versionsData.round_number} · {versionsData.season_year}/{versionsData.season_year + 1}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                onClick={() => setVersionsOpen(false)}
              >
                Chiudi
              </button>
            </div>

            {versionsLoading ? <p className="mt-3 text-sm text-slate-500">Caricamento…</p> : null}
            {versionsError ? <p className="mt-3 text-sm text-rose-700">{versionsError}</p> : null}
            {versionsData && !versionsLoading ? (
              <div className="mt-3 space-y-2 text-sm text-slate-800">
                {versionsData.items.map((v) => (
                  <div key={v.id} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium">
                        v{v.analysis_version}{' '}
                        <span className="text-xs font-normal text-slate-500">({v.status})</span>
                      </div>
                      <div className="text-xs text-slate-500">{v.created_at}</div>
                    </div>
                    {v.models_calculated_last_run?.length ? (
                      <div className="mt-2 text-xs text-slate-700">
                        Modelli aggiornati: {v.models_calculated_last_run.join(', ')}
                      </div>
                    ) : null}
                    {v.models_preserved_last_run?.length ? (
                      <div className="mt-1 text-xs text-slate-700">
                        Modelli preservati: {v.models_preserved_last_run.join(', ')}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

export function ModelSummaryBar({
  summary,
}: {
  summary: RoundAnalysisDetail['model_summary_json']
}) {
  if (!summary) return null
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {Object.values(summary).map((m) => {
        const display = m.display ?? ((m.predictions_available ?? 0) > 0 ? 'OK' : 'ND')
        const nd = display === 'ND' || display === 'ERROR'
        const okCount = m.fixtures_ok ?? m.predictions_available ?? 0
        const total = m.fixtures ?? 0
        return (
          <div key={m.model_key} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
            <div className="font-semibold text-slate-900">
              {m.label}
              <span
                className={`ml-2 rounded px-1.5 py-0.5 text-xs ${modelDisplayBadgeClass(display)}`}
              >
                {display}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {okCount}/{total} calcolate
              {m.model_engine_name ? ` · ${m.model_engine_name}` : ''}
            </p>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span
                className={`rounded-full px-2 py-0.5 ${
                  nd ? 'bg-slate-100 text-slate-600' : hitRateBadgeClass(m.aggressive_hit_rate)
                }`}
              >
                Agg{' '}
                {m.aggressive_hit_rate != null
                  ? `${m.aggressive_wins ?? 0}/${(m.aggressive_wins ?? 0) + (m.aggressive_losses ?? 0)} · ${m.aggressive_hit_rate}%`
                  : 'ND'}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 ${
                  nd ? 'bg-slate-100 text-slate-600' : hitRateBadgeClass(m.cautious_hit_rate)
                }`}
              >
                Cauta{' '}
                {m.cautious_hit_rate != null
                  ? `${m.cautious_wins ?? 0}/${(m.cautious_wins ?? 0) + (m.cautious_losses ?? 0)} · ${m.cautious_hit_rate}%`
                  : 'ND'}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {nd && m.prevalent_error_code
                ? `Motivo prevalente: ${errorCodeLabelIt(m.prevalent_error_code)}`
                : nd
                  ? 'Nessuna predizione su questa giornata'
                  : `MAE ${m.mae ?? '—'} · Bias ${m.bias ?? '—'}`}
            </p>
          </div>
        )
      })}
    </div>
  )
}
