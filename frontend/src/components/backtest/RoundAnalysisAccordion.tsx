import { useCallback, useEffect, useState } from 'react'
import {
  deleteRoundAnalysis,
  getRoundAnalysisDetail,
  getRoundAnalyses,
  type RoundAnalysisDetail,
  type RoundAnalysisListItem,
} from '../../lib/api'
import { RoundAnalysisDeleteConfirm } from './RoundAnalysisDeleteConfirm'
import { dataQualityBadgeClass, hitRateBadgeClass, statusLabelIt } from './roundAnalysisUtils'

type Props = {
  competitionId: number | null
  seasonYear: number
  selectedId: number | null
  onSelect: (detail: RoundAnalysisDetail) => void
  onDeleted: (analysisId: number) => void
  reloadToken: number
}

function accordionModelLine(item: RoundAnalysisListItem): string {
  const s = item.accordion_summary
  if (!s) return ''
  const parts = ['v1.1', 'v2.0', 'v2.1'].map((k) => {
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
  reloadToken,
}: Props) {
  const [items, setItems] = useState<RoundAnalysisListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<RoundAnalysisListItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    try {
      const res = await getRoundAnalyses(competitionId, seasonYear, {
        limit: 50,
        sortBy: 'round_number',
        sortDir: 'desc',
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
          const motive = item.accordion_summary?.motive
          return (
            <div
              key={item.id}
              className={`rounded-xl border ${active ? 'border-slate-400 bg-slate-50' : 'border-slate-200 bg-white'}`}
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
                    <span
                      className={`rounded-full px-2 py-0.5 ${dataQualityBadgeClass(item.data_quality_badge)}`}
                    >
                      {item.data_quality_badge ?? '—'}
                    </span>
                    <span className="text-slate-600">
                      {item.status_label ?? statusLabelIt(item.status)}
                    </span>
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
                  {modelLine ? <p className="text-xs text-slate-600">{modelLine}</p> : null}
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
        const nd = (m.predictions_available ?? 0) === 0
        return (
          <div key={m.model_key} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
            <div className="font-semibold text-slate-900">
              {m.label}
              {nd ? (
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                  ND
                </span>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span
                className={`rounded-full px-2 py-0.5 ${
                  nd ? 'bg-slate-100 text-slate-600' : hitRateBadgeClass(m.aggressive_hit_rate)
                }`}
              >
                Agg {m.aggressive_hit_rate != null ? `${m.aggressive_hit_rate}%` : 'ND'}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 ${
                  nd ? 'bg-slate-100 text-slate-600' : hitRateBadgeClass(m.cautious_hit_rate)
                }`}
              >
                Cauta {m.cautious_hit_rate != null ? `${m.cautious_hit_rate}%` : 'ND'}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {nd
                ? 'Storico insufficiente per questa giornata'
                : `MAE ${m.mae ?? '—'} · Bias ${m.bias ?? '—'} · ${m.fixtures} partite`}
            </p>
          </div>
        )
      })}
    </div>
  )
}
