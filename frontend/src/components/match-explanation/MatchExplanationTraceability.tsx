import { useMemo, useState } from 'react'
import type {
  AppliedVariableTraceRow,
  ComponentTreeNode,
  FrameworkConsistencyPayload,
} from '../../types/sotExplanation'
import {
  deriveTraceabilityForSide,
  roleLabel,
  traceRowMatchesFilter,
  type TraceFilter,
} from '../../utils/explanationTraceability'

function statusBorderClass(label: string): string {
  if (label === 'OK') return 'border-emerald-200 bg-emerald-50/40'
  if (label === 'OK con avvisi') return 'border-amber-200 bg-amber-50/50'
  if (label === 'Errore formula') return 'border-rose-200 bg-rose-50/50'
  if (label === 'Parziale / fallback v1.1') return 'border-amber-200 bg-amber-50/60'
  if (label === 'Da controllare') return 'border-violet-200 bg-violet-50/40'
  return 'border-slate-200 bg-slate-50/40'
}

export function FrameworkConsistencyCard({
  fc,
  traceHome,
  traceAway,
}: {
  fc: FrameworkConsistencyPayload
  traceHome: AppliedVariableTraceRow[]
  traceAway: AppliedVariableTraceRow[]
}) {
  const homeM = useMemo(() => deriveTraceabilityForSide(traceHome, fc.home), [traceHome, fc.home])
  const awayM = useMemo(() => deriveTraceabilityForSide(traceAway, fc.away), [traceAway, fc.away])

  const blocks = [
    { side: 'Casa' as const, d: fc.home, m: homeM },
    { side: 'Trasferta' as const, d: fc.away, m: awayM },
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 text-[11px] leading-relaxed text-slate-700">
        <strong className="text-slate-900">Nota:</strong> le variabili dichiarate nel manifest non entrano tutte nella
        somma numerica finale. Alcune servono per contesto, qualità dati o controlli. La previsione numerica è costruita
        solo dalle voci indicate come «Formula finale» / «Input componente» nel trace, con dato disponibile.
      </div>
      {blocks.map(({ side, d, m }) => (
        <div key={side} className={`rounded-xl border p-3 ${statusBorderClass(m.statusLabel)}`}>
          <p className="text-xs font-semibold text-slate-900">{side}</p>
          <dl className="mt-2 grid gap-1 text-[11px] text-slate-800 sm:grid-cols-2">
            <div>
              <dt className="text-slate-500">Dichiarate dal modello (manifest)</dt>
              <dd className="font-mono font-semibold">{m.manifestDeclared}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Tracciate nello spaccato</dt>
              <dd className="font-mono font-semibold">{m.tracedCount}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Con valore disponibile</dt>
              <dd className="font-mono font-semibold">{m.withValueAvailable}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Usate nella formula finale</dt>
              <dd className="font-mono font-semibold">{m.formulaFinalCount}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Contesto / rischio</dt>
              <dd className="font-mono font-semibold">{m.contextRiskCount}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Qualità dati</dt>
              <dd className="font-mono font-semibold">{m.qualityDataCount}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Mancanti (dato)</dt>
              <dd className="font-mono font-semibold">{m.missingDataRowCount}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Mancanti nel trace</dt>
              <dd className="font-mono font-semibold">{m.notInTraceCount}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs font-semibold text-slate-900">Stato: {m.statusLabel}</p>
          {d.missing_data_keys?.length ? (
            <div className="mt-2">
              <p className="text-[11px] font-medium text-amber-900">Dati mancanti:</p>
              <ul className="mt-1 list-inside list-disc text-[11px] text-amber-950">
                {d.missing_data_keys.map((k) => (
                  <li key={k} className="font-mono">
                    {k}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {d.missing_trace_keys?.length ? (
            <div className="mt-2">
              <p className="text-[11px] font-medium text-rose-900">Chiavi manifest assenti dal trace:</p>
              <p className="mt-1 font-mono text-[10px] text-rose-950">{d.missing_trace_keys.join(', ')}</p>
            </div>
          ) : null}
          {d.extra_trace_keys?.length ? (
            <div className="mt-2">
              <p className="text-[11px] font-medium text-rose-900">Chiavi trace extra rispetto al manifest:</p>
              <p className="mt-1 font-mono text-[10px] text-rose-950">{d.extra_trace_keys.join(', ')}</p>
            </div>
          ) : null}
          {d.validation_warnings?.length ? (
            <ul className="mt-2 list-inside list-disc text-[11px] text-amber-950">
              {d.validation_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  )
}

export function ComponentTreeView({ nodes, teamName }: { nodes: ComponentTreeNode[]; teamName: string }) {
  if (!nodes.length) return <p className="text-xs text-slate-500">Nessun componente.</p>
  return (
    <div className="space-y-2 text-xs text-slate-800">
      <p className="font-semibold text-slate-900">{teamName}</p>
      <ul className="space-y-1 border-l border-slate-200 pl-3">
        {nodes.map((n) => (
          <li key={String(n.component_key)} className="leading-relaxed">
            <span className="font-medium">{n.component_label ?? n.component_key}</span>
            {n.value != null ? (
              <span className="ml-1 tabular-nums text-slate-600">
                · val {n.value}
                {n.weight != null ? ` · peso ${Math.round(Number(n.weight) * 100)}%` : ''}
                {n.contribution != null ? ` · contr. ${n.contribution}` : ''}
              </span>
            ) : null}
            {n.variables?.length ? (
              n.variables.some((v) => v.raw_value != null || v.normalized_value != null) ? (
                <div className="mt-2 overflow-x-auto rounded border border-slate-100">
                  <table className="min-w-full text-left text-[10px] text-slate-700">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                        <th className="px-1.5 py-1 font-medium">Input</th>
                        <th className="px-1.5 py-1 font-medium">Grezzo</th>
                        <th className="px-1.5 py-1 font-medium">Norm.</th>
                        <th className="px-1.5 py-1 font-medium">Peso</th>
                        <th className="px-1.5 py-1 font-medium">Contr.</th>
                        <th className="px-1.5 py-1 font-medium">Fonte</th>
                        <th className="px-1.5 py-1 font-medium">N</th>
                        <th className="px-1.5 py-1 font-medium">FB</th>
                      </tr>
                    </thead>
                    <tbody>
                      {n.variables.map((v) => (
                        <tr key={v.key} className="border-b border-slate-50">
                          <td className="px-1.5 py-1">{v.label}</td>
                          <td className="px-1.5 py-1 tabular-nums">{v.raw_value ?? v.value ?? '—'}</td>
                          <td className="px-1.5 py-1 tabular-nums">{v.normalized_value ?? v.value ?? '—'}</td>
                          <td className="px-1.5 py-1 tabular-nums">
                            {v.internal_weight != null
                              ? `${Math.round(Number(v.internal_weight) * 100)}%`
                              : v.weight_internal != null
                                ? `${Math.round(Number(v.weight_internal) * 100)}%`
                                : '—'}
                          </td>
                          <td className="px-1.5 py-1 tabular-nums">
                            {v.internal_contribution ?? v.contribution ?? '—'}
                          </td>
                          <td className="px-1.5 py-1 font-mono text-[9px] text-slate-500">{v.data_source ?? '—'}</td>
                          <td className="px-1.5 py-1 tabular-nums">{v.matches_count ?? '—'}</td>
                          <td className="px-1.5 py-1">{v.fallback_used ? 'sì' : 'no'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <ul className="mt-1 space-y-0.5 border-l border-slate-100 pl-2 text-[11px] text-slate-600">
                  {n.variables.map((v) => (
                    <li key={v.key}>
                      {v.label}: <span className="tabular-nums">{v.value ?? '—'}</span>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

const FILTER_OPTIONS: { id: TraceFilter; label: string }[] = [
  { id: 'all', label: 'Tutte' },
  { id: 'formula', label: 'Formula finale' },
  { id: 'context', label: 'Contesto/rischio' },
  { id: 'quality', label: 'Qualità dati' },
  { id: 'missing', label: 'Mancanti' },
]

export function AppliedVariableTraceTable({ rows }: { rows: AppliedVariableTraceRow[] }) {
  const [filter, setFilter] = useState<TraceFilter>('all')
  const filtered = useMemo(() => rows.filter((r) => traceRowMatchesFilter(r, filter)), [rows, filter])
  const counts = useMemo(() => {
    return {
      all: rows.length,
      formula: rows.filter((r) => traceRowMatchesFilter(r, 'formula')).length,
      context: rows.filter((r) => traceRowMatchesFilter(r, 'context')).length,
      quality: rows.filter((r) => traceRowMatchesFilter(r, 'quality')).length,
      missing: rows.filter((r) => traceRowMatchesFilter(r, 'missing')).length,
    }
  }, [rows])

  if (!rows.length) return null

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setFilter(opt.id)}
            className={`rounded-full border px-2.5 py-1 text-[10px] font-medium transition ${
              filter === opt.id
                ? 'border-slate-800 bg-slate-800 text-white'
                : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
            }`}
          >
            {opt.label}
            <span className="ml-1 tabular-nums opacity-80">
              (
              {opt.id === 'all'
                ? counts.all
                : opt.id === 'formula'
                  ? counts.formula
                  : opt.id === 'context'
                    ? counts.context
                    : opt.id === 'quality'
                      ? counts.quality
                      : counts.missing}
              )
            </span>
          </button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="min-w-full text-left text-[10px] text-slate-800">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
              <th className="px-2 py-1.5 font-medium">Area</th>
              <th className="px-2 py-1.5 font-medium">Variabile</th>
              <th className="px-2 py-1.5 font-medium">Ruolo</th>
              <th className="px-2 py-1.5 font-medium">Padre</th>
              <th className="px-2 py-1.5 font-medium">Valore</th>
              <th className="px-2 py-1.5 font-medium">Peso</th>
              <th className="px-2 py-1.5 font-medium">Contr.</th>
              <th className="px-2 py-1.5 font-medium">Stato</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-2 py-3 text-center text-slate-500">
                  Nessuna riga per questo filtro.
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.trace_key} className="border-b border-slate-100 align-top">
                  <td className="px-2 py-1.5 text-slate-600">{r.area}</td>
                  <td className="px-2 py-1.5 font-medium text-slate-900">{r.label}</td>
                  <td className="px-2 py-1.5">{roleLabel(r.application_role)}</td>
                  <td className="px-2 py-1.5 font-mono text-[9px] text-slate-500">{r.parent_component ?? '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{r.value != null ? String(r.value) : '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{r.weight != null ? String(r.weight) : '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{r.contribution != null ? String(r.contribution) : '—'}</td>
                  <td className="px-2 py-1.5">{r.status ?? '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
