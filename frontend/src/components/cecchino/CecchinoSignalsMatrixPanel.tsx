import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'

type Props = {
  matrix: CecchinoSignalsMatrix
}

function SiNoBadge({ value }: { value: string }) {
  const isSi = value === 'SI'
  return (
    <span
      className={`inline-block min-w-[2rem] rounded px-1.5 py-0.5 text-center text-[10px] font-semibold uppercase ${
        isSi ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
      }`}
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

export function CecchinoSignalsMatrixPanel({ matrix }: Props) {
  const rows = matrix.rows ?? []
  const rel = matrix.reliability
  const inputs = matrix.inputs

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
        <span className="text-[10px] text-slate-500">{matrix.source ?? ''}</span>
      </div>

      {inputs && (
        <p className="text-[11px] tabular-nums text-slate-600">
          F32={inputs.q1 != null ? Number(inputs.q1).toFixed(2) : '—'} · F33=
          {inputs.qx != null ? Number(inputs.qx).toFixed(2) : '—'} · F34=
          {inputs.q2 != null ? Number(inputs.q2).toFixed(2) : '—'} · F35=
          {inputs.avg_q != null ? Number(inputs.avg_q).toFixed(2) : '—'} · F36=
          {inputs.diff_1_2 != null ? Number(inputs.diff_1_2).toFixed(2) : '—'}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs text-slate-700">
          <thead className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2">Mercato / Segnale</th>
              {EXCEL_HEADERS.map((h) => (
                <th key={h} className="px-2 py-2 text-center">
                  {h}
                </th>
              ))}
              <th className="px-2 py-2 text-center">Scala</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const sig = row.signals ?? {}
              const scala =
                signalVal(sig, 'scala_1x') !== '—'
                  ? signalVal(sig, 'scala_1x')
                  : signalVal(sig, 'scala_x2')
              return (
                <tr key={row.key} className="border-t border-slate-100">
                  <td className="px-2 py-1.5 font-medium">{row.label}</td>
                  {EXCEL_COLS.map((col) => (
                    <td key={col} className="px-2 py-1.5 text-center">
                      <SiNoBadge value={signalVal(sig, col)} />
                    </td>
                  ))}
                  <td className="px-2 py-1.5 text-center">
                    {scala !== '—' ? <SiNoBadge value={scala} /> : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {rel && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-3 text-xs text-slate-700">
          <p className="font-semibold text-indigo-900">Indice affidabilità</p>
          <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Sample</dt>
              <dd className="font-medium tabular-nums">{rel.sample ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Indice</dt>
              <dd className="font-medium tabular-nums">
                {rel.index != null && Number.isFinite(rel.index)
                  ? Number(rel.index).toFixed(2)
                  : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd className="font-medium">{rel.status ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Livello</dt>
              <dd className="font-medium">{rel.level ?? '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      {(matrix.warnings?.length ?? 0) > 0 && (
        <ul className="list-inside list-disc text-[11px] text-amber-800">
          {matrix.warnings!.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
