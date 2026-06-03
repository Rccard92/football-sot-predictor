import { useState } from 'react'
import type { V31Top3FixtureComparison, V31WinQuality } from '../../lib/api'
import {
  CLUSTER_INTERPRETATION_IT,
  CLUSTER_LABELS_IT,
  TOP3_CLUSTER_UI_ORDER,
  clusterExamples,
  filterFixturesByWinQuality,
  fmtNum,
} from './predictiveVerdictUtils'

type Props = {
  fixtures: V31Top3FixtureComparison[]
  clusterSummary?: { total_fixtures?: number; counts?: Record<string, number>; pct?: Record<string, number> }
}

const MODEL_FILTER_KEYS = [
  'v31_bias_corrected',
  'v31_bias_dynamic_high_guard',
  'v31_chaos_game',
] as const

export function PatternAnalysisTop3Panel({ fixtures, clusterSummary }: Props) {
  const [openCluster, setOpenCluster] = useState<string | null>(null)
  const [winQualityFilter, setWinQualityFilter] = useState<V31WinQuality | 'all'>('all')
  const [modelFilter, setModelFilter] = useState<string>('v31_bias_corrected')

  const counts = clusterSummary?.counts ?? {}
  const pct = clusterSummary?.pct ?? {}
  const total = clusterSummary?.total_fixtures ?? fixtures.length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <label className="flex items-center gap-1">
          Modello
          <select
            className="rounded border px-1 py-0.5"
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
          >
            {MODEL_FILTER_KEYS.map((k) => (
              <option key={k} value={k}>
                {k.replace('v31_', '')}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          win_quality
          <select
            className="rounded border px-1 py-0.5"
            value={winQualityFilter}
            onChange={(e) => setWinQualityFilter(e.target.value as V31WinQuality | 'all')}
          >
            <option value="all">Tutti</option>
            <option value="HEALTHY_WIN">HEALTHY_WIN</option>
            <option value="UNDERSTATED_WIN">UNDERSTATED_WIN</option>
            <option value="BAD_LOSS_OVERESTIMATION">BAD_LOSS</option>
          </select>
        </label>
      </div>

      <div className="space-y-2">
        {TOP3_CLUSTER_UI_ORDER.map((cluster) => {
          const count = counts[cluster] ?? 0
          if (count === 0 && !counts[cluster]) return null
          const isOpen = openCluster === cluster
          const examples = clusterExamples(fixtures, cluster, 5)
          const filteredTable = filterFixturesByWinQuality(
            fixtures.filter((f) => f.top3_cluster === cluster),
            modelFilter,
            winQualityFilter,
          )

          return (
            <div key={cluster} className="rounded-lg border border-slate-200 bg-white">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left text-xs"
                onClick={() => setOpenCluster(isOpen ? null : cluster)}
              >
                <span className="font-medium text-slate-900">
                  {CLUSTER_LABELS_IT[cluster] ?? cluster}
                </span>
                <span className="text-slate-600">
                  {count} ({fmtNum(pct[cluster] ?? (total ? (100 * count) / total : 0), 1)}%)
                </span>
              </button>
              {isOpen ? (
                <div className="border-t border-slate-100 px-3 pb-3 pt-2 text-xs">
                  <p className="text-slate-700">
                    {CLUSTER_INTERPRETATION_IT[cluster] ?? '—'}
                  </p>
                  {examples.length ? (
                    <ul className="mt-2 space-y-1 text-slate-600">
                      {examples.map((ex) => (
                        <li key={ex.fixture_id}>
                          {ex.match ?? ex.fixture_id} — actual {ex.actual_total_sot} · bias{' '}
                          {fmtNum(ex.models?.v31_bias_corrected?.predicted_total_sot)} · hybrid{' '}
                          {fmtNum(ex.models?.v31_bias_dynamic_high_guard?.predicted_total_sot)} · chaos{' '}
                          {fmtNum(ex.models?.v31_chaos_game?.predicted_total_sot)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {filteredTable.length > 0 && filteredTable.length <= 10 ? (
                    <p className="mt-2 text-[10px] text-slate-500">
                      {filteredTable.length} fixture con filtro win_quality attivo
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
