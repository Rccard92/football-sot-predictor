import type { AuditVariable } from './types'
import { fmtNum } from './mapping'

function metaNum(meta: Record<string, unknown> | null | undefined, key: string): number | null {
  const v = meta?.[key]
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  return null
}

function metaStr(meta: Record<string, unknown> | null | undefined, key: string): string | null {
  const v = meta?.[key]
  if (typeof v === 'string') return v
  return null
}

export function VariableDetailDrawer({ v }: { v: AuditVariable }) {
  const meta = (v.calculation?.meta ?? null) as Record<string, unknown> | null
  const matchesCount = metaNum(meta, 'matches_count')
  const sum = metaNum(meta, 'sum')
  const sampleRowsCount = metaNum(meta, 'sample_rows_count') ?? v.sample_rows.length
  const sampleRowsNote = metaStr(meta, 'sample_rows_note')

  return (
    <details className="mt-3 rounded-2xl border border-slate-200 bg-white">
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-800">
        Vedi dettaglio tecnico
      </summary>
      <div className="border-t border-slate-200 p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-slate-50/40 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Calcolo</p>
            <p className="mt-2 text-xs text-slate-700">
              <span className="text-slate-500">Formula:</span>{' '}
              <span className="font-mono">{v.calculation?.formula ?? '—'}</span>
            </p>
            <p className="mt-1 text-xs text-slate-700">
              <span className="text-slate-500">Somma:</span> <strong>{fmtNum(sum)}</strong>
            </p>
            <p className="mt-1 text-xs text-slate-700">
              <span className="text-slate-500">Partite usate (calcolo):</span> <strong>{fmtNum(matchesCount, 0)}</strong>
            </p>
            <p className="mt-2 text-[11px] text-slate-600">
              {sampleRowsNote ??
                `Il calcolo usa tutte le partite valide: ${matchesCount ?? '—'}. Qui ne vengono mostrate solo ${sampleRowsCount} per comodità.`}
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50/40 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Fonte</p>
            <p className="mt-2 text-xs text-slate-700">
              <span className="text-slate-500">Tabella:</span> <strong>{v.source_table ?? '—'}</strong>
            </p>
            <p className="mt-1 text-xs text-slate-700">
              <span className="text-slate-500">Descrizione:</span> {v.source_description ?? '—'}
            </p>
            {v.notes ? <p className="mt-2 text-[11px] text-slate-600">{v.notes}</p> : null}
          </div>
        </div>

        {v.sample_rows?.length ? (
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              Esempio partite considerate (ultime {v.sample_rows.length})
            </p>
            <div className="mt-2 overflow-x-auto rounded-2xl border border-slate-200">
              <table className="min-w-[900px] w-full text-left text-xs">
                <thead className="bg-slate-50">
                  <tr className="text-slate-600">
                    <th className="px-3 py-2">Data</th>
                    <th className="px-3 py-2">Partita</th>
                    <th className="px-3 py-2">Team</th>
                    <th className="px-3 py-2">Lato</th>
                    <th className="px-3 py-2">Avversario</th>
                    <th className="px-3 py-2">SOT</th>
                    <th className="px-3 py-2">Tiri</th>
                    <th className="px-3 py-2">GF</th>
                    <th className="px-3 py-2">GS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {v.sample_rows.map((r) => (
                    <tr key={r.fixture_id} className="text-slate-700">
                      <td className="px-3 py-2">{new Date(r.date).toLocaleString('it-IT')}</td>
                      <td className="px-3 py-2">
                        {r.home_team} vs {r.away_team}
                      </td>
                      <td className="px-3 py-2">{r.team}</td>
                      <td className="px-3 py-2">{r.side}</td>
                      <td className="px-3 py-2">{r.opponent}</td>
                      <td className="px-3 py-2">{r.shots_on_target ?? '—'}</td>
                      <td className="px-3 py-2">{r.total_shots ?? '—'}</td>
                      <td className="px-3 py-2">{r.goals_for ?? '—'}</td>
                      <td className="px-3 py-2">{r.goals_against ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-xs text-slate-600">Nessun sample rows disponibile per questa variabile.</p>
        )}
      </div>
    </details>
  )
}

