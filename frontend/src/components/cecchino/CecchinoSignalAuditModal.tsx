import { useEffect, useId, useRef } from 'react'
import type {
  CecchinoSignalCellExplanation,
  CecchinoSignalConditionLeaf,
  CecchinoSignalLogicGroup,
} from '../../lib/cecchinoTodayApi'

type Props = {
  explanation: CecchinoSignalCellExplanation
  onClose: () => void
}

function resultBadgeClass(result: string | null | undefined): string {
  if (result === 'SI') return 'border-emerald-200 bg-emerald-50 text-emerald-800'
  if (result === 'NO') return 'border-rose-200 bg-rose-50 text-rose-800'
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

function consistencyClass(status: string): string {
  if (status === 'match') return 'border-emerald-200 bg-emerald-50 text-emerald-800'
  if (status === 'mismatch' || status === 'trace_mismatch') {
    return 'border-rose-200 bg-rose-50 text-rose-800'
  }
  return 'border-amber-200 bg-amber-50 text-amber-900'
}

function collectLeaves(logic: CecchinoSignalLogicGroup | undefined): CecchinoSignalConditionLeaf[] {
  if (!logic) return []
  const out: CecchinoSignalConditionLeaf[] = []
  const walk = (node: CecchinoSignalLogicGroup) => {
    for (const c of node.conditions || []) {
      if (c && typeof c.passed === 'boolean' && c.expression) out.push(c)
    }
    for (const b of node.branches || []) walk(b)
  }
  walk(logic)
  return out
}

export function CecchinoSignalAuditModal({ explanation, onClose }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const result = explanation.stored_result
  const leaves =
    explanation.passed_conditions.length || explanation.failed_conditions.length
      ? [...explanation.passed_conditions, ...explanation.failed_conditions]
      : collectLeaves(explanation.logic)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-3 sm:items-center sm:p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-full max-w-[780px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="shrink-0 border-b border-slate-200 bg-[#1e3a5f] px-4 py-3 text-white sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p id={titleId} className="text-sm font-bold tracking-wide sm:text-base">
                Analisi segnale
              </p>
              <p className="mt-1 text-xs text-slate-200">
                Mercato:{' '}
                <span className="font-semibold text-white">{explanation.row_label}</span>
                {' · '}
                Colonna:{' '}
                <span className="font-semibold text-white">{explanation.column_label}</span>
                {' · '}
                Cella Excel:{' '}
                <span className="font-semibold text-white">{explanation.source_cell}</span>
              </p>
              <p className="mt-1 text-xs text-slate-200">
                Risultato:{' '}
                <span className="font-semibold text-white">{result ?? '—'}</span>
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${resultBadgeClass(
                    result,
                  )}`}
                >
                  {result ?? '—'}
                </span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${consistencyClass(
                    explanation.consistency?.status || '',
                  )}`}
                >
                  {explanation.consistency?.status || '—'}
                </span>
                <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                  {explanation.source_cell}
                </span>
                <span className="rounded border border-sky-300/40 bg-sky-500/20 px-1.5 py-0.5 text-[10px] text-sky-100">
                  Snapshot persistito
                </span>
              </div>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className="rounded-md border border-white/40 bg-white/10 px-2.5 py-1 text-xs font-medium text-white hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
            >
              Chiudi
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-5">
          <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Cosa controlla questo segnale
            </h4>
            <p className="mt-1.5 text-sm text-slate-800">{explanation.description}</p>
            <p className="mt-2 text-sm text-slate-600">{explanation.purpose}</p>
            {explanation.target_market ? (
              <p className="mt-2 text-xs text-slate-500">
                Mercato target: {explanation.target_market}
              </p>
            ) : null}
            {explanation.si_meaning ? (
              <p className="mt-2 text-xs text-emerald-800">{explanation.si_meaning}</p>
            ) : null}
            {explanation.no_meaning ? (
              <p className="mt-1 text-xs text-rose-800">{explanation.no_meaning}</p>
            ) : null}
          </section>

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Formula utilizzata
            </h4>
            <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-[#0f2847] px-3 py-3 font-mono text-[11px] leading-relaxed text-amber-100 whitespace-pre-wrap">
              {explanation.excel_formula}
            </pre>
            <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-[12px] leading-relaxed text-slate-800 whitespace-pre-wrap">
              {explanation.formula_symbolic}
            </pre>
          </section>

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Valutazione con i dati della partita
            </h4>
            <ul className="mt-2 space-y-1.5">
              {leaves.map((leaf) => {
                const ok = leaf.passed
                return (
                  <li
                    key={`${leaf.condition_key}-${leaf.expression}`}
                    className={`rounded-md border px-2.5 py-1.5 font-mono text-[12px] ${
                      ok
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                        : 'border-rose-200 bg-rose-50 text-rose-900'
                    }`}
                  >
                    {ok ? '✓' : '✗'} {leaf.expression}
                    <span className="mt-0.5 block font-sans text-[10px] opacity-80">
                      {leaf.label}
                    </span>
                  </li>
                )
              })}
            </ul>
            <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Risultato persistito</dt>
                <dd className="mt-0.5 font-semibold">{explanation.stored_result ?? '—'}</dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Risultato audit canonico</dt>
                <dd className="mt-0.5 font-semibold">
                  {explanation.canonical_audit_result ?? '—'}
                </dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Risultato trace</dt>
                <dd className="mt-0.5 font-semibold">
                  {explanation.condition_trace_result ?? '—'}
                </dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Consistency</dt>
                <dd className="mt-0.5">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold ${consistencyClass(
                      explanation.consistency?.status || '',
                    )}`}
                  >
                    {explanation.consistency?.status || '—'}
                  </span>
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Perché il risultato è {result ?? '—'}
            </h4>
            <p className="mt-1.5 text-sm text-slate-800">{explanation.reason_summary}</p>
            {explanation.failed_conditions.length > 0 ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-rose-800">
                {explanation.failed_conditions.map((f) => (
                  <li key={`fail-${f.condition_key}-${f.expression}`}>
                    {f.left_label} = {f.left_display} non soddisfa {f.operator} {f.right_label} ={' '}
                    {f.right_display}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Origine dei dati
            </h4>
            <ul className="mt-2 space-y-1.5 text-xs text-slate-700">
              {(explanation.inputs || []).map((inp) => (
                <li key={inp.key} className="rounded border border-slate-100 px-2 py-1.5">
                  <span className="font-medium text-slate-900">
                    {inp.excel_name || inp.label}
                  </span>
                  {': '}
                  <span className="tabular-nums">{inp.display_value ?? '—'}</span>
                  {inp.derivation ? (
                    <span className="mt-0.5 block text-[10px] text-slate-500">
                      Formula: {inp.derivation}
                    </span>
                  ) : null}
                  <span className="mt-0.5 block font-mono text-[10px] text-slate-500">
                    {inp.source_path}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {(explanation.warnings ?? []).length > 0 ? (
            <section className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <h4 className="font-semibold">Avvisi</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {(explanation.warnings ?? []).map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}
