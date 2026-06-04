import type { CecchinoPicchetto } from '../../lib/cecchinoApi'
import { formatWdl, fmtNum, fmtPct, statusBadgeClass, statusLabel } from '../../lib/cecchinoUtils'

const PICCHETTO_ORDER = ['home_away', 'totals', 'last5_home_away', 'last6_totals']

function recordHome(p: CecchinoPicchetto): string {
  if (p.input_records?.home) return formatWdl(p.input_records.home)
  return formatWdl(p.home_context)
}

function recordAway(p: CecchinoPicchetto): string {
  if (p.input_records?.away) return formatWdl(p.input_records.away)
  return formatWdl(p.away_context)
}

function fmtSample(p: CecchinoPicchetto): string {
  const h = p.sample_home
  const a = p.sample_away
  const th = p.target_sample_home
  const ta = p.target_sample_away
  if (h == null && a == null) return '—'
  const left = th != null ? `${h ?? 0}/${th}` : String(h ?? 0)
  const right = ta != null ? `${a ?? 0}/${ta}` : String(a ?? 0)
  return `${left} · ${right}`
}

type Props = {
  picchetti: Record<string, CecchinoPicchetto>
}

export function CecchinoPicchettiDashboardTable({ picchetti }: Props) {
  const rows = PICCHETTO_ORDER.map((k) => picchetti[k]).filter(Boolean)

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <h3 className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-800">
        Picchetti tecnici
      </h3>
      <table className="min-w-full text-left text-xs text-slate-700">
        <thead className="border-b border-slate-200 bg-slate-50/80 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2" rowSpan={2}>
              Picchetto
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Record casa
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Record trasferta
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Campione
            </th>
            <th className="px-3 py-2" rowSpan={2}>
              Stato
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
              <td className="px-3 py-2 text-slate-600">{recordHome(p)}</td>
              <td className="px-3 py-2 text-slate-600">{recordAway(p)}</td>
              <td className="px-3 py-2 text-center tabular-nums text-slate-600">{fmtSample(p)}</td>
              <td className="px-3 py-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${statusBadgeClass(p.status)}`}
                >
                  {statusLabel(p.status)}
                </span>
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_1.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtNum(p.outcome_1.quota)}
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_x.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtNum(p.outcome_x.quota)}
              </td>
              <td className="border-l border-slate-100 px-2 py-2 text-center tabular-nums">
                {fmtPct(p.outcome_2.prob_pct)}
              </td>
              <td className="px-2 py-2 text-center font-medium tabular-nums">
                {fmtNum(p.outcome_2.quota)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
