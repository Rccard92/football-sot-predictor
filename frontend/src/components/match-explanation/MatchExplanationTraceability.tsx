import type {
  AppliedVariableTraceRow,
  ComponentTreeNode,
  FrameworkConsistencyPayload,
} from '../../types/sotExplanation'

function roleLabel(role: string): string {
  if (role === 'direct_formula_component') return 'Formula finale'
  if (role === 'component_input') return 'Input componente'
  if (role === 'context_risk') return 'Contesto / rischio'
  if (role === 'quality_control') return 'Qualità dati'
  if (role === 'debug_only') return 'Solo debug'
  return role
}

export function FrameworkConsistencyCard({ fc }: { fc: FrameworkConsistencyPayload }) {
  const rows = [
    { side: 'Casa' as const, d: fc.home },
    { side: 'Trasferta' as const, d: fc.away },
  ]
  return (
    <div className="space-y-4">
      {rows.map(({ side, d }) => (
        <div
          key={side}
          className={`rounded-xl border p-3 ${d.is_consistent ? 'border-emerald-200 bg-emerald-50/40' : 'border-amber-200 bg-amber-50/50'}`}
        >
          <p className="text-xs font-semibold text-slate-900">{side}</p>
          <p className="mt-1 text-[11px] text-slate-700">
            Variabili applicate (manifest): <span className="font-mono font-semibold">{d.framework_applied_count}</span> ·
            Tracciate nello spaccato: <span className="font-mono font-semibold">{d.debug_trace_count}</span>
          </p>
          <p className="mt-1 text-xs font-semibold text-slate-900">Stato: {d.is_consistent ? 'OK' : 'Da controllare'}</p>
          {d.missing_data_keys?.length ? (
            <p className="mt-2 text-[11px] text-amber-900">Dati mancanti: {d.missing_data_keys.join(', ')}</p>
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
              <ul className="mt-1 space-y-0.5 border-l border-slate-100 pl-2 text-[11px] text-slate-600">
                {n.variables.map((v) => (
                  <li key={v.key}>
                    {v.label}: <span className="tabular-nums">{v.value ?? '—'}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function AppliedVariableTraceTable({ rows }: { rows: AppliedVariableTraceRow[] }) {
  if (!rows.length) return null
  return (
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
          {rows.map((r) => (
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
          ))}
        </tbody>
      </table>
    </div>
  )
}
