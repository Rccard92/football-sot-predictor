import { useCallback, useEffect, useState } from 'react'
import {
  getRoundAnalysisDetail,
  getRoundAnalyses,
  type RoundAnalysisDetail,
  type RoundAnalysisListItem,
} from '../../lib/api'
import { dataQualityBadgeClass, hitRateBadgeClass } from './roundAnalysisUtils'

type Props = {
  competitionId: number | null
  seasonYear: number
  selectedId: number | null
  onSelect: (detail: RoundAnalysisDetail) => void
  reloadToken: number
}

export function RoundAnalysisAccordion({
  competitionId,
  seasonYear,
  selectedId,
  onSelect,
  reloadToken,
}: Props) {
  const [items, setItems] = useState<RoundAnalysisListItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    try {
      const res = await getRoundAnalyses(competitionId, seasonYear, { limit: 50 })
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

  if (competitionId == null) return null

  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-slate-900">Giornate analizzate</h2>
      {loading ? <p className="text-sm text-slate-500">Caricamento…</p> : null}
      {!loading && items.length === 0 ? (
        <p className="text-sm text-slate-500">Nessuna analisi salvata per questa stagione.</p>
      ) : null}
      <div className="space-y-2">
        {items.map((item) => {
          const active = selectedId === item.id
          return (
            <div
              key={item.id}
              className={`rounded-xl border ${active ? 'border-slate-400 bg-slate-50' : 'border-slate-200 bg-white'}`}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                onClick={() => void open(item.id)}
              >
                <div>
                  <span className="font-medium text-slate-900">
                    Giornata {item.round_number}
                  </span>
                  <span className="ml-2 text-xs text-slate-500">v{item.analysis_version}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span
                    className={`rounded-full px-2 py-0.5 ${dataQualityBadgeClass(item.data_quality_badge)}`}
                  >
                    {item.data_quality_badge ?? '—'}
                  </span>
                  <span className="text-slate-500">{item.status}</span>
                </div>
              </button>
            </div>
          )
        })}
      </div>
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
      {Object.values(summary).map((m) => (
        <div key={m.model_key} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
          <div className="font-semibold text-slate-900">{m.label}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span className={`rounded-full px-2 py-0.5 ${hitRateBadgeClass(m.aggressive_hit_rate)}`}>
              Agg {m.aggressive_hit_rate != null ? `${m.aggressive_hit_rate}%` : '—'}
            </span>
            <span className={`rounded-full px-2 py-0.5 ${hitRateBadgeClass(m.cautious_hit_rate)}`}>
              Cauta {m.cautious_hit_rate != null ? `${m.cautious_hit_rate}%` : '—'}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            MAE {m.mae ?? '—'} · Bias {m.bias ?? '—'} · {m.fixtures} partite
          </p>
        </div>
      ))}
    </div>
  )
}
