import type { AuditVariable } from './types'
import { fmtNum } from './mapping'
import { VariableDetailDrawer } from './VariableDetailDrawer'

function badgeForStatus(v: AuditVariable) {
  if (v.status === 'missing') return 'bg-slate-100 text-slate-600 ring-slate-200'
  if (v.implementation_status === 'todo') return 'bg-slate-50 text-slate-600 ring-slate-200'
  if (v.implementation_status === 'debug_only') return 'bg-amber-50 text-amber-900 ring-amber-200'
  if (v.applied_to_model) return 'bg-emerald-50 text-emerald-900 ring-emerald-200'
  return 'bg-slate-100 text-slate-700 ring-slate-200'
}

function labelForStatus(v: AuditVariable) {
  if (v.implementation_status === 'todo') return 'Da implementare'
  if (v.status === 'missing') return 'Mancante'
  if (v.implementation_status === 'debug_only') return 'Solo debug'
  if (v.applied_to_model) return 'Applicata al modello'
  return 'Disponibile'
}

export function AuditVariableCard({ v }: { v: AuditVariable }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{v.label}</p>
          {v.team_name ? <p className="mt-1 text-xs text-slate-500">{v.team_name}</p> : null}
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${badgeForStatus(v)}`}>
          {labelForStatus(v)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-2xl font-semibold tracking-tight text-slate-900">
            {fmtNum(v.value)} {v.unit ? <span className="text-base font-medium text-slate-600">{v.unit}</span> : null}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
            {v.applied_to_model ? (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-900 ring-1 ring-emerald-200">
                Applicata
              </span>
            ) : null}
            {v.weight_label ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
                Peso {v.weight_label}
              </span>
            ) : null}
            {v.source_table ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
                Fonte {v.source_table}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      <VariableDetailDrawer v={v} />
    </article>
  )
}

