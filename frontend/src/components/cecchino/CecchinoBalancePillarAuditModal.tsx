import { useEffect, useId, useRef } from 'react'
import type { CecchinoBalancePillarExplanation } from '../../lib/cecchinoTodayApi'
import { CecchinoOverlayPortal } from './CecchinoOverlayPortal'

type Props = {
  explanation: CecchinoBalancePillarExplanation
  sourceMode?: string | null
  onClose: () => void
}

function statusBadgeClass(status: string): string {
  if (status === 'available' || status === 'ok' || status === 'match') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-800'
  }
  if (status === 'partial' || status === 'rounding_match') {
    return 'border-amber-200 bg-amber-50 text-amber-900'
  }
  if (status === 'mismatch' || status === 'unavailable') {
    return status === 'mismatch'
      ? 'border-rose-200 bg-rose-50 text-rose-800'
      : 'border-slate-200 bg-slate-50 text-slate-700'
  }
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

function whyTitle(explanation: CecchinoBalancePillarExplanation): string {
  const klass = explanation.displayed_result?.class || explanation.canonical_audit_result?.class
  if (!klass) return 'Perché questa conclusione'
  if (explanation.pillar_key === 'conviction') {
    return `Perché lo scenario è ${klass}`
  }
  if (explanation.pillar_key === 'draw_credibility') {
    return `Perché il pareggio è ${klass.replace(/^Pareggio\s+/i, '').toLowerCase()}`
  }
  if (explanation.pillar_key === 'coherence_1_2') {
    return `Perché la coerenza è ${klass.toLowerCase()}`
  }
  return `Perché la classe è ${klass}`
}

function hasWeights(components: CecchinoBalancePillarExplanation['components']): boolean {
  return Boolean(components?.some((c) => c.weight != null))
}

function hasContributions(components: CecchinoBalancePillarExplanation['components']): boolean {
  return Boolean(components?.some((c) => c.contribution != null))
}

export function CecchinoBalancePillarAuditModal({ explanation, sourceMode, onClose }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const warnings = explanation.warnings ?? []
  const consistency = explanation.consistency?.status ?? '—'
  const disp = explanation.displayed_result
  const can = explanation.canonical_audit_result
  const components = explanation.components ?? []
  const showWeight = hasWeights(components)
  const showContribution = hasContributions(components)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <CecchinoOverlayPortal>
      <div
        className="flex h-full w-full items-end justify-center bg-black/40 p-3 sm:items-center sm:p-4"
        role="presentation"
        onClick={onClose}
      >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-full max-w-[840px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="shrink-0 border-b border-slate-200 bg-[#1e3a5f] px-4 py-3 text-white sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p id={titleId} className="text-sm font-bold tracking-wide sm:text-base">
                Analisi pilastro Balance v5
              </p>
              <p className="mt-1 text-xs text-slate-200">
                Pilastro {explanation.pillar_number}
                {' · '}
                <span className="font-semibold text-white">{explanation.title}</span>
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {explanation.badge ? (
                  <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-100">
                    {explanation.badge}
                  </span>
                ) : null}
                <span className="rounded border border-sky-300/40 bg-sky-500/20 px-1.5 py-0.5 text-[10px] text-sky-100">
                  valore {disp?.display_value ?? disp?.value ?? '—'}
                </span>
                {disp?.class ? (
                  <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                    {disp.class}
                  </span>
                ) : null}
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusBadgeClass(
                    consistency,
                  )}`}
                >
                  {consistency}
                </span>
                {sourceMode ? (
                  <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                    {sourceMode}
                  </span>
                ) : null}
                {explanation.formula_version ? (
                  <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                    {explanation.formula_version}
                  </span>
                ) : null}
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
              Cosa misura questo pilastro
            </h4>
            <p className="mt-1.5 text-sm text-slate-800">{explanation.description}</p>
            {explanation.purpose ? (
              <p className="mt-2 text-sm text-slate-600">{explanation.purpose}</p>
            ) : null}
            {explanation.interpretation ? (
              <p className="mt-2 text-sm text-slate-700">{explanation.interpretation}</p>
            ) : null}
            {explanation.methodological_caution ? (
              <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
                {explanation.methodological_caution}
              </p>
            ) : null}
          </section>

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Formula utilizzata
            </h4>
            <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-[#0f2847] px-3 py-3 font-mono text-[12px] leading-relaxed text-amber-100 whitespace-pre-wrap">
              {explanation.formula_symbolic}
            </pre>
            {(explanation.classification_trace || []).length > 0 ? (
              <ul className="mt-2 space-y-1 text-xs text-slate-700">
                {explanation.classification_trace!.map((t) => (
                  <li
                    key={`${t.class}-${t.condition}`}
                    className={`rounded border px-2 py-1 ${
                      t.matched
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                        : 'border-slate-100 bg-slate-50'
                    }`}
                  >
                    <span className="font-medium">{t.class}</span>
                    {': '}
                    <span className="font-mono text-[11px]">{t.condition}</span>
                    {t.matched ? ' · matched' : ''}
                  </li>
                ))}
              </ul>
            ) : null}
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
          </section>

          <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {whyTitle(explanation)}
            </h4>
            <p className="mt-1.5 text-sm text-slate-800">{explanation.reason_summary}</p>
          </section>

          {components.length > 0 ? (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Componenti
              </h4>
              <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[360px] border-collapse text-left text-xs">
                  <thead className="bg-slate-100 text-slate-600">
                    <tr>
                      <th className="px-2 py-1.5 font-semibold">Componente</th>
                      <th className="px-2 py-1.5 font-semibold">Valore</th>
                      {showWeight ? (
                        <th className="px-2 py-1.5 font-semibold">Peso</th>
                      ) : null}
                      {showContribution ? (
                        <th className="px-2 py-1.5 font-semibold">Contributo</th>
                      ) : null}
                      <th className="px-2 py-1.5 font-semibold">Fonte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {components.map((c, i) => (
                      <tr key={c.key ?? `c-${i}`} className="border-t border-slate-100">
                        <td className="px-2 py-1.5 text-slate-800">{c.label ?? c.key ?? '—'}</td>
                        <td className="px-2 py-1.5 tabular-nums text-slate-900">
                          {c.value == null || c.value === '' ? '—' : String(c.value)}
                        </td>
                        {showWeight ? (
                          <td className="px-2 py-1.5 tabular-nums">
                            {c.weight == null ? '—' : String(c.weight)}
                          </td>
                        ) : null}
                        {showContribution ? (
                          <td className="px-2 py-1.5 tabular-nums">
                            {c.contribution == null ? '—' : String(c.contribution)}
                          </td>
                        ) : null}
                        <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">
                          {c.source ?? c.unit ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Origine dati e consistenza
            </h4>
            <dl className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Risultato mostrato</dt>
                <dd className="mt-0.5 font-semibold text-slate-900">
                  {disp?.display_value ?? disp?.value ?? '—'}
                  {disp?.class ? ` · ${disp.class}` : ''}
                  {disp?.direction ? ` · ${disp.direction}` : ''}
                </dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Risultato audit</dt>
                <dd className="mt-0.5 font-semibold text-slate-900">
                  {can?.value ?? '—'}
                  {can?.class ? ` · ${can.class}` : ''}
                  {can?.direction ? ` · ${can.direction}` : ''}
                </dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Delta</dt>
                <dd className="mt-0.5 tabular-nums text-slate-800">
                  {explanation.consistency?.delta ?? '—'}
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
                </dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Source mode</dt>
                <dd className="mt-0.5 text-xs text-slate-700">{sourceMode ?? '—'}</dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-[10px] uppercase text-slate-500">Formula version</dt>
                <dd className="mt-0.5 text-xs text-slate-700">
                  {explanation.formula_version ?? '—'}
                </dd>
              </div>
            </dl>
            {(explanation.inputs || []).length > 0 ? (
              <ul className="mt-3 space-y-1.5 text-xs text-slate-700">
                {explanation.inputs!.map((inp) => (
                  <li key={inp.key} className="rounded border border-slate-100 px-2 py-1.5">
                    <span className="font-medium text-slate-900">{inp.label}</span>
                    {': '}
                    <span className="tabular-nums">{inp.display_value ?? '—'}</span>
                    <span className="mt-0.5 block font-mono text-[10px] text-slate-500">
                      {inp.source_path}
                      {inp.source_type ? ` · ${inp.source_type}` : ''}
                      {inp.derivation ? ` · ${inp.derivation}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
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
        </div>
      </div>
      </div>
    </CecchinoOverlayPortal>
  )
}
