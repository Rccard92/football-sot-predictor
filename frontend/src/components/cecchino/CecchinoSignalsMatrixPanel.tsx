import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'

type Props = {
  matrix: CecchinoSignalsMatrix
  variant?: 'default' | 'embedded'
}

function SiNoBadge({ value, embedded }: { value: string; embedded?: boolean }) {
  if (value !== 'SI' && value !== 'NO') {
    return <span className="text-slate-400">—</span>
  }
  const isSi = value === 'SI'
  const base = embedded
    ? isSi
      ? 'bg-emerald-100 text-emerald-800 ring-emerald-200/80'
      : 'bg-rose-50 text-rose-700/90 ring-rose-200/60'
    : isSi
      ? 'bg-emerald-100 text-emerald-800'
      : 'bg-slate-100 text-slate-600'
  return (
    <span
      className={`inline-block min-w-[2.25rem] rounded-md px-2 py-0.5 text-center text-[11px] font-semibold uppercase ring-1 ${base}`}
    >
      {value}
    </span>
  )
}

function signalVal(signals: Record<string, string>, key: string): string {
  const v = signals[key]
  return v === 'SI' || v === 'NO' ? v : '—'
}

const EXCEL_COLS = ['excel_d', 'excel_e', 'excel_f', 'excel_g'] as const
const EXCEL_HEADERS = ['Excel D', 'Excel E', 'Excel F', 'Excel G']

export function CecchinoSignalsMatrixPanel({ matrix, variant = 'default' }: Props) {
  const embedded = variant === 'embedded'
  const rows = matrix.rows ?? []
  const rel = matrix.reliability
  const inputs = matrix.inputs

  const outerClass = embedded
    ? 'space-y-4'
    : 'space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm'

  return (
    <div className={outerClass}>
      {!embedded && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
          <span className="text-[10px] text-slate-500">{matrix.source ?? ''}</span>
        </div>
      )}

      {inputs && (
        <p className="text-xs tabular-nums text-slate-600">
          F32={inputs.q1 != null ? Number(inputs.q1).toFixed(2) : '—'} · F33=
          {inputs.qx != null ? Number(inputs.qx).toFixed(2) : '—'} · F34=
          {inputs.q2 != null ? Number(inputs.q2).toFixed(2) : '—'} · F35=
          {inputs.avg_q != null ? Number(inputs.avg_q).toFixed(2) : '—'} · F36=
          {inputs.diff_1_2 != null ? Number(inputs.diff_1_2).toFixed(2) : '—'}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-sm text-slate-700">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2.5">Mercato / Segnale</th>
              {EXCEL_HEADERS.map((h) => (
                <th key={h} className="px-3 py-2.5 text-center">
                  {h}
                </th>
              ))}
              <th className="px-3 py-2.5 text-center">Scala</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const sig = row.signals ?? {}
              const scala =
                row.key === 'one_x'
                  ? signalVal(sig, 'scala_1x')
                  : row.key === 'x_two'
                    ? signalVal(sig, 'scala_x2')
                    : '—'
              return (
                <tr key={row.key} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <td className="px-3 py-2 font-medium text-slate-800">{row.label}</td>
                  {EXCEL_COLS.map((col) => (
                    <td key={col} className="px-3 py-2 text-center">
                      <SiNoBadge value={signalVal(sig, col)} embedded={embedded} />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-center">
                    {scala !== '—' ? <SiNoBadge value={scala} embedded={embedded} /> : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {rel && (
        <div
          className={
            embedded
              ? 'rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 to-indigo-50/40 px-4 py-4'
              : 'rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-3 text-xs text-slate-700'
          }
        >
          <p className="text-sm font-semibold text-slate-900">Indice affidabilità</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Sample</dt>
              <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">{rel.sample ?? '—'}</dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Indice</dt>
              <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                {rel.index != null && Number.isFinite(rel.index)
                  ? Number(rel.index).toFixed(2)
                  : '—'}
              </dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Status</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{rel.status ?? '—'}</dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Livello</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{rel.level ?? '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      {(matrix.warnings?.length ?? 0) > 0 && (
        <ul className="list-inside list-disc text-xs text-amber-800">
          {matrix.warnings!.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
