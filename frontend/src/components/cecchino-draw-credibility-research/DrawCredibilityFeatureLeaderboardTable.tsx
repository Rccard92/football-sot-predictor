import { useMemo, useState } from 'react'
import type { DrawCredibilityFeatureLeaderboardRow } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  rows: DrawCredibilityFeatureLeaderboardRow[]
}

const RELIABILITY_OPTIONS = [
  'all',
  'potentially_useful',
  'modest',
  'weak',
  'uncertain',
  'insufficient_sample',
] as const

export function DrawCredibilityFeatureLeaderboardTable({ rows }: Props) {
  const [reliabilityFilter, setReliabilityFilter] = useState<(typeof RELIABILITY_OPTIONS)[number]>('all')
  const [sortAsc, setSortAsc] = useState(false)

  const filtered = useMemo(() => {
    let list = [...rows]
    if (reliabilityFilter !== 'all') {
      list = list.filter((r) => r.reliability_status === reliabilityFilter)
    }
    list.sort((a, b) => {
      const av = a.discriminative_auc ?? 0
      const bv = b.discriminative_auc ?? 0
      return sortAsc ? av - bv : bv - av
    })
    return list
  }, [reliabilityFilter, rows, sortAsc])

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">Feature leaderboard</h3>
        <div className="flex flex-wrap gap-2">
          <select
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
            value={reliabilityFilter}
            onChange={(e) =>
              setReliabilityFilter(e.target.value as (typeof RELIABILITY_OPTIONS)[number])
            }
          >
            {RELIABILITY_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
            onClick={() => setSortAsc((v) => !v)}
          >
            AUC {sortAsc ? '↑' : '↓'}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="px-2 py-2">Feature</th>
              <th className="px-2 py-2">AUC disc.</th>
              <th className="px-2 py-2">Pearson</th>
              <th className="px-2 py-2">Trend</th>
              <th className="px-2 py-2">Spread pp</th>
              <th className="px-2 py-2">Reliability</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.feature} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium text-slate-800">{r.feature}</td>
                <td className="px-2 py-2 tabular-nums">
                  {r.discriminative_auc?.toFixed(3) ?? '—'}
                </td>
                <td className="px-2 py-2 tabular-nums">{r.pearson?.toFixed(3) ?? '—'}</td>
                <td className="px-2 py-2">{r.trend}</td>
                <td className="px-2 py-2 tabular-nums">{r.spread_pp?.toFixed(1) ?? '—'}</td>
                <td className="px-2 py-2">{r.reliability_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
