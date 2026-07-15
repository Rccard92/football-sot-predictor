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

function fmt(n: number | null | undefined, digits = 3): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function familyOf(r: DrawCredibilityFeatureLeaderboardRow): string {
  return r.family ?? r.feature_family ?? '—'
}

function discCi(r: DrawCredibilityFeatureLeaderboardRow): string {
  const lo = r.bootstrap?.discriminative_auc_ci_lower ?? r.bootstrap?.auc_ci_lower
  const hi = r.bootstrap?.discriminative_auc_ci_upper ?? r.bootstrap?.auc_ci_upper
  if (typeof lo !== 'number' || typeof hi !== 'number') return '—'
  return `${lo.toFixed(3)}–${hi.toFixed(3)}`
}

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
                {o === 'all' ? 'Tutte le reliability' : o}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
            onClick={() => setSortAsc((v) => !v)}
          >
            AUC disc. {sortAsc ? '↑' : '↓'}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="px-2 py-2">Feature</th>
              <th className="px-2 py-2">Famiglia</th>
              <th
                className="px-2 py-2"
                title="Verso dell'associazione (dirAUC &gt; 0.5 → valori alti associati a più pareggi)"
              >
                AUC dir.
              </th>
              <th
                className="px-2 py-2"
                title="Separazione indipendente dal verso (max(AUC, 1−AUC))"
              >
                AUC disc.
              </th>
              <th className="px-2 py-2">CI 95% disc.</th>
              <th className="px-2 py-2">Pearson</th>
              <th className="px-2 py-2">Spearman</th>
              <th className="px-2 py-2">Trend</th>
              <th className="px-2 py-2">Spread pp</th>
              <th className="px-2 py-2">Stabilità Prim/Sens</th>
              <th className="px-2 py-2">Reliability</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.feature} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium text-slate-800">{r.feature}</td>
                <td className="px-2 py-2 text-slate-600">{familyOf(r)}</td>
                <td
                  className="px-2 py-2 tabular-nums"
                  title="Verso dell'associazione con il pareggio"
                >
                  {fmt(r.directional_auc)}
                </td>
                <td
                  className="px-2 py-2 tabular-nums"
                  title="Separazione indipendente dal verso"
                >
                  {fmt(r.discriminative_auc)}
                </td>
                <td className="px-2 py-2 tabular-nums text-slate-600">{discCi(r)}</td>
                <td className="px-2 py-2 tabular-nums">{fmt(r.pearson)}</td>
                <td className="px-2 py-2 tabular-nums">{fmt(r.spearman)}</td>
                <td className="px-2 py-2">{r.trend}</td>
                <td className="px-2 py-2 tabular-nums">{fmt(r.spread_pp, 1)}</td>
                <td className="px-2 py-2">{r.stability_status ?? '—'}</td>
                <td className="px-2 py-2">{r.reliability_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
