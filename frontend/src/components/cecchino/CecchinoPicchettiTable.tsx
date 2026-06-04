import type { CecchinoPicchetto } from '../../lib/api'

const PICCHETTO_ORDER = ['home_away', 'totals', 'last5_home_away', 'last6_totals']

function fmtQuota(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(2)}%`
}

function fmtSample(p: CecchinoPicchetto) {
  const h = p.sample_home
  const a = p.sample_away
  const th = p.target_sample_home
  const ta = p.target_sample_away
  if (h == null && a == null) return '—'
  const left = th != null ? `${h ?? 0}/${th}` : String(h ?? 0)
  const right = ta != null ? `${a ?? 0}/${ta}` : String(a ?? 0)
  return `${left} · ${right}`
}

function statusBadge(status: string) {
  const cls =
    status === 'available'
      ? 'bg-emerald-100 text-emerald-800'
      : status === 'partial_low_sample'
        ? 'bg-amber-100 text-amber-900'
        : status === 'insufficient_data'
          ? 'bg-amber-100 text-amber-800'
          : status === 'pending_formula_extraction'
            ? 'bg-slate-100 text-slate-600'
            : 'bg-red-100 text-red-800'
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      {status}
    </span>
  )
}

type Props = {
  picchetti: Record<string, CecchinoPicchetto>
}

export function CecchinoPicchettiTable({ picchetti }: Props) {
  const rows = PICCHETTO_ORDER.map((k) => picchetti[k]).filter(Boolean)

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full text-left text-xs text-slate-700">
        <thead className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2" rowSpan={2}>
              Picchetto
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Stato
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Campione
            </th>
            <th className="border-l border-slate-200 px-3 py-2 text-center" colSpan={2}>
              1
            </th>
            <th className="border-l border-slate-200 px-3 py-2 text-center" colSpan={2}>
              X
            </th>
            <th className="border-l border-slate-200 px-3 py-2 text-center" colSpan={2}>
              2
            </th>
          </tr>
          <tr>
            <th className="border-l border-slate-200 px-2 py-1 text-center">%</th>
            <th className="px-2 py-1 text-center">Quota</th>
            <th className="border-l border-slate-200 px-2 py-1 text-center">%</th>
            <th className="px-2 py-1 text-center">Quota</th>
            <th className="border-l border-slate-200 px-2 py-1 text-center">%</th>
            <th className="px-2 py-1 text-center">Quota</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.key} className="border-t border-slate-100">
              <td className="px-3 py-2 font-medium text-slate-900">{p.label}</td>
              <td className="px-3 py-2">{statusBadge(p.status)}</td>
              <td className="px-3 py-2 text-center tabular-nums text-slate-600">
                {fmtSample(p)}
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_1.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtQuota(p.outcome_1.quota)}
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_x.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtQuota(p.outcome_x.quota)}
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_2.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtQuota(p.outcome_2.quota)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
