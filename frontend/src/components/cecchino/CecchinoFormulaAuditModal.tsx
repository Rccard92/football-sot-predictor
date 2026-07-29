import { useEffect, useId, useRef } from 'react'
import type { CecchinoKpiExplanation } from '../../lib/cecchinoTodayApi'
import { CecchinoPurchasabilityV3AuditView } from './CecchinoPurchasabilityV3AuditView'

type Props = {
  explanation: CecchinoKpiExplanation
  onClose: () => void
}

function statusBadgeClass(status: string): string {
  if (status === 'available' || status === 'ok' || status === 'match') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-800'
  }
  if (status === 'partial' || status === 'rounding_match' || status === 'insufficient_data') {
    return 'border-amber-200 bg-amber-50 text-amber-900'
  }
  if (status === 'mismatch') {
    return 'border-rose-200 bg-rose-50 text-rose-800'
  }
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

export function CecchinoFormulaAuditModal({ explanation, onClose }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const isV3 = explanation.metric_key === 'purchasability_v3'

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const warnings = explanation.warnings ?? []
  const consistency = explanation.consistency?.status ?? '—'

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
                Analisi formula
              </p>
              <p className="mt-1 text-xs text-slate-200">
                Mercato: <span className="font-semibold text-white">{explanation.market_label}</span>
                {' · '}
                Metrica:{' '}
                <span className="font-semibold text-white">{explanation.metric_label}</span>
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusBadgeClass(
                    explanation.status,
                  )}`}
                >
                  {explanation.status}
                </span>
                {explanation.formula_version ? (
                  <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                    {explanation.formula_version}
                  </span>
                ) : null}
                {(
                  (explanation as CecchinoKpiExplanation & { audit_badges?: string[] })
                    .audit_badges ?? ['Snapshot persistito']
                ).map((badge) => (
                  <span
                    key={badge}
                    className="rounded border border-sky-300/40 bg-sky-500/20 px-1.5 py-0.5 text-[10px] text-sky-100"
                  >
                    {badge}
                  </span>
                ))}
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
          {isV3 ? (
            <CecchinoPurchasabilityV3AuditView explanation={explanation} />
          ) : (
            <>
              <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Cosa rappresenta
                </h4>
                <p className="mt-1.5 text-sm text-slate-800">{explanation.description}</p>
                <p className="mt-2 text-sm text-slate-600">{explanation.purpose}</p>
                {explanation.unavailable_reason ? (
                  <p className="mt-2 text-sm font-medium text-amber-800">
                    Motivo: {explanation.unavailable_reason}
                  </p>
                ) : null}
              </section>

              {explanation.metric_key === 'purchasability_v2' &&
              explanation.normalization_profile &&
              typeof explanation.normalization_profile === 'object' ? (
                <section className="rounded-lg border border-slate-200 px-3 py-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Profilo di normalizzazione
                  </h4>
                  <dl className="mt-2 grid grid-cols-1 gap-1 text-xs text-slate-700 sm:grid-cols-2">
                    <div>
                      Version:{' '}
                      <span className="font-mono">
                        {String(
                          (explanation.normalization_profile as Record<string, unknown>).version ??
                            '—',
                        )}
                      </span>
                    </div>
                    <div>
                      Cutoff:{' '}
                      <span className="font-mono">
                        {String(
                          (explanation.normalization_profile as Record<string, unknown>).cutoff ??
                            '—',
                        )}
                      </span>
                    </div>
                    <div className="sm:col-span-2">
                      Hash:{' '}
                      <span className="break-all font-mono text-[10px]">
                        {String(
                          (explanation.normalization_profile as Record<string, unknown>).hash ??
                            '—',
                        )}
                      </span>
                    </div>
                  </dl>
                </section>
              ) : null}

              {explanation.metric_key === 'purchasability_v2' &&
              explanation.positive_value_gate &&
              typeof explanation.positive_value_gate === 'object' ? (
                <section className="rounded-lg border border-slate-200 px-3 py-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Gate valore positivo
                  </h4>
                  <p className="mt-1.5 text-sm text-slate-800">
                    Status:{' '}
                    <strong>
                      {String(
                        (explanation.positive_value_gate as Record<string, unknown>).status ??
                          '—',
                      )}
                    </strong>
                  </p>
                  {explanation.raw_pre_gate_score != null ? (
                    <p className="mt-1 text-xs text-slate-600">
                      Raw pre-gate: {String(explanation.raw_pre_gate_score)} — se il gate fallisce
                      lo score ufficiale è 0.
                    </p>
                  ) : null}
                </section>
              ) : null}

              {explanation.metric_key === 'purchasability_delta' ? (
                <section className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-800">
                    Nota diagnostica
                  </h4>
                  <p className="mt-1.5 text-sm text-amber-900">
                    Il delta è un confronto numerico tra due architetture. Non stabilisce quale
                    modello sia empiricamente migliore.
                  </p>
                </section>
              ) : null}

              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Formula utilizzata
                </h4>
                <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-[#0f2847] px-3 py-3 font-mono text-[12px] leading-relaxed text-amber-100 whitespace-pre-wrap">
                  {explanation.formula_symbolic}
                </pre>
              </section>

              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Calcolo con i dati della partita
                </h4>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-800">
                  {(explanation.formula_applied || []).map((step, i) => (
                    <li key={`${i}-${step}`} className="font-mono text-[12px] leading-relaxed">
                      {step}
                    </li>
                  ))}
                </ol>

                {(explanation.inputs || []).length > 0 ? (
                  <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full min-w-[420px] border-collapse text-left text-xs">
                      <thead className="bg-slate-100 text-slate-600">
                        <tr>
                          <th className="px-2 py-1.5 font-semibold">Input</th>
                          <th className="px-2 py-1.5 font-semibold">Valore</th>
                          <th className="px-2 py-1.5 font-semibold">Fonte</th>
                        </tr>
                      </thead>
                      <tbody>
                        {explanation.inputs.map((inp) => (
                          <tr key={inp.key} className="border-t border-slate-100">
                            <td className="px-2 py-1.5 text-slate-800">{inp.label}</td>
                            <td className="px-2 py-1.5 tabular-nums text-slate-900">
                              {inp.display_value ?? '—'}
                            </td>
                            <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">
                              {inp.source_path}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}

                <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                  <div className="rounded-md border border-slate-200 px-2.5 py-2">
                    <dt className="text-[10px] uppercase text-slate-500">Risultato persistito</dt>
                    <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                      {explanation.stored_result_display ??
                        String(explanation.stored_result ?? '—')}
                    </dd>
                  </div>
                  <div className="rounded-md border border-slate-200 px-2.5 py-2">
                    <dt className="text-[10px] uppercase text-slate-500">Risultato audit</dt>
                    <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                      {explanation.audit_result == null
                        ? '—'
                        : typeof explanation.audit_result === 'number'
                          ? String(explanation.audit_result)
                          : String(explanation.audit_result)}
                    </dd>
                  </div>
                  <div className="rounded-md border border-slate-200 px-2.5 py-2">
                    <dt className="text-[10px] uppercase text-slate-500">Consistency</dt>
                    <dd className="mt-0.5">
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold ${statusBadgeClass(
                          consistency,
                        )}`}
                      >
                        {consistency}
                      </span>
                      {explanation.consistency?.delta != null ? (
                        <span className="ml-2 text-xs text-slate-500">
                          Δ {explanation.consistency.delta}
                        </span>
                      ) : null}
                    </dd>
                  </div>
                  <div className="rounded-md border border-slate-200 px-2.5 py-2">
                    <dt className="text-[10px] uppercase text-slate-500">Arrotondamento</dt>
                    <dd className="mt-0.5 text-xs text-slate-700">
                      {explanation.rounding?.policy ?? '—'}
                      {explanation.rounding?.precision != null
                        ? ` · prec. ${explanation.rounding.precision}`
                        : ''}
                      {explanation.rounding?.display_precision != null
                        ? ` · display ${explanation.rounding.display_precision}`
                        : ''}
                    </dd>
                  </div>
                </dl>
              </section>

              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Origine dei dati
                </h4>
                <ul className="mt-2 space-y-1.5 text-xs text-slate-700">
                  {(explanation.inputs || []).map((inp) => (
                    <li
                      key={`src-${inp.key}`}
                      className="rounded border border-slate-100 px-2 py-1.5"
                    >
                      <span className="font-medium text-slate-900">{inp.label}</span>
                      {': '}
                      <span className="tabular-nums">{inp.display_value ?? '—'}</span>
                      <span className="mt-0.5 block font-mono text-[10px] text-slate-500">
                        {inp.source_path}
                        {inp.source_type ? ` · ${inp.source_type}` : ''}
                        {inp.timestamp ? ` · ${inp.timestamp}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              {warnings.length > 0 ? (
                <section className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <h4 className="font-semibold">Avvisi</h4>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">
                    {warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
