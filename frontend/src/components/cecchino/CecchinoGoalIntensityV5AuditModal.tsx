import { useEffect, useId, useRef } from 'react'
import type {
  CecchinoGiV5CalibrationBlock,
  CecchinoGiV5CandidateExplanation,
  CecchinoGiV5DimensionExplanation,
  CecchinoGiV5DimensionMetric,
  CecchinoGiV5EcdfNormalization,
} from '../../lib/cecchinoTodayApi'

type Props = {
  type: 'dimension' | 'candidate'
  explanation: CecchinoGiV5DimensionExplanation | CecchinoGiV5CandidateExplanation
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
  if (status === 'mismatch') {
    return 'border-rose-200 bg-rose-50 text-rose-800'
  }
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toLocaleString('it-IT', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  })
}

function isEcdfNorm(v: unknown): v is CecchinoGiV5EcdfNormalization {
  return Boolean(v && typeof v === 'object' && ('train_n' in (v as object) || 'percentile_result' in (v as object)))
}

function NormalizationBlock({ norm }: { norm: CecchinoGiV5EcdfNormalization }) {
  return (
    <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
      <div>
        <dt className="text-slate-500">Grezzo</dt>
        <dd className="font-mono tabular-nums">{fmt(norm.raw_value)}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Clip</dt>
        <dd className="font-mono tabular-nums">
          {fmt(norm.clipped_value)}
          {norm.clipping_applied ? ' · sì' : ''}
        </dd>
      </div>
      <div>
        <dt className="text-slate-500">train_n</dt>
        <dd className="font-mono tabular-nums">{norm.train_n ?? '—'}</dd>
      </div>
      <div>
        <dt className="text-slate-500">min / max</dt>
        <dd className="font-mono tabular-nums">
          {fmt(norm.train_min)} / {fmt(norm.train_max)}
        </dd>
      </div>
      <div>
        <dt className="text-slate-500">lower / equal</dt>
        <dd className="font-mono tabular-nums">
          {norm.lower_count ?? '—'} / {norm.equal_count ?? '—'}
        </dd>
      </div>
      <div>
        <dt className="text-slate-500">Percentile</dt>
        <dd className="font-mono tabular-nums font-semibold">{fmt(norm.percentile_result)}</dd>
      </div>
      {norm.distribution_hash ? (
        <div className="col-span-2 sm:col-span-3">
          <dt className="text-slate-500">distribution_hash</dt>
          <dd className="break-all font-mono text-[10px] text-slate-600">{norm.distribution_hash}</dd>
        </div>
      ) : null}
    </dl>
  )
}

function MetricSection({ metric }: { metric: CecchinoGiV5DimensionMetric }) {
  const norms: CecchinoGiV5EcdfNormalization[] = []
  const n = metric.normalization
  if (isEcdfNorm(n)) {
    norms.push(n)
  } else if (n && typeof n === 'object') {
    for (const v of Object.values(n)) {
      if (isEcdfNorm(v)) norms.push(v)
    }
  }

  return (
    <article className="rounded-lg border border-slate-200 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <h5 className="text-sm font-semibold text-slate-900">{metric.label}</h5>
        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
          {metric.metric_key}
        </span>
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusBadgeClass(
            metric.consistency?.status ?? '—',
          )}`}
        >
          {metric.consistency?.status ?? '—'}
        </span>
      </div>
      {metric.description ? <p className="mt-1.5 text-xs text-slate-600">{metric.description}</p> : null}
      {metric.formula_symbolic ? (
        <pre className="mt-2 overflow-x-auto rounded border border-slate-200 bg-[#0f2847] px-2.5 py-2 font-mono text-[11px] text-amber-100 whitespace-pre-wrap">
          {metric.formula_symbolic}
        </pre>
      ) : null}
      {(metric.formula_applied || []).length > 0 ? (
        <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-xs text-slate-800">
          {metric.formula_applied!.map((step, i) => (
            <li key={`${i}-${step}`} className="font-mono text-[11px]">
              {step}
            </li>
          ))}
        </ol>
      ) : null}
      {norms.map((norm, i) => (
        <div key={norm.feature_key ?? i} className="mt-2 rounded border border-slate-100 bg-slate-50 px-2 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Normalizzazione ECDF{norm.feature_key ? ` · ${norm.feature_key}` : ''}
          </p>
          <NormalizationBlock norm={norm} />
        </div>
      ))}
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Persistito</dt>
          <dd className="font-mono font-semibold">{fmt(metric.stored_result)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Audit</dt>
          <dd className="font-mono font-semibold">{fmt(metric.audit_result)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Delta</dt>
          <dd className="font-mono">{metric.consistency?.delta ?? '—'}</dd>
        </div>
      </dl>
      {(metric.used_by_candidates || []).length > 0 ? (
        <p className="mt-2 text-[11px] text-slate-600">
          Usato da:{' '}
          <span className="font-medium text-slate-800">{metric.used_by_candidates!.join(', ')}</span>
        </p>
      ) : (
        <p className="mt-2 text-[11px] text-slate-500">Non utilizzato direttamente dai candidati UI.</p>
      )}
      {(metric.warnings || []).map((w) => (
        <p key={w} className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900">
          {w}
        </p>
      ))}
    </article>
  )
}

function CalibrationSection({
  title,
  block,
}: {
  title: string
  block?: CecchinoGiV5CalibrationBlock
}) {
  if (!block) return null
  return (
    <article className="rounded-lg border border-slate-200 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <h5 className="text-sm font-semibold text-slate-900">{title}</h5>
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusBadgeClass(
            block.consistency?.status ?? '—',
          )}`}
        >
          {block.consistency?.status ?? '—'}
        </span>
      </div>
      {block.formula_symbolic ? (
        <pre className="mt-2 overflow-x-auto rounded border border-slate-200 bg-[#0f2847] px-2.5 py-2 font-mono text-[11px] text-amber-100 whitespace-pre-wrap">
          {block.formula_symbolic}
        </pre>
      ) : null}
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-slate-500">Score</dt>
          <dd className="font-mono">{fmt(block.score)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Intercept</dt>
          <dd className="font-mono">{fmt(block.intercept, 4)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Coefficiente</dt>
          <dd className="font-mono">{fmt(block.coefficient, 4)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">train_n</dt>
          <dd className="font-mono">{block.train_n ?? '—'}</dd>
        </div>
      </dl>
      {(block.formula_applied || []).length > 0 ? (
        <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-xs">
          {block.formula_applied!.map((step, i) => (
            <li key={`${i}-${step}`} className="font-mono text-[11px] text-slate-800">
              {step}
            </li>
          ))}
        </ol>
      ) : null}
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-slate-500">Persistito</dt>
          <dd className="font-mono font-semibold">{fmt(block.stored_result, 4)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Audit</dt>
          <dd className="font-mono font-semibold">{fmt(block.audit_result, 4)}</dd>
        </div>
      </dl>
    </article>
  )
}

function DimensionBody({
  explanation,
  sourceMode,
}: {
  explanation: CecchinoGiV5DimensionExplanation
  sourceMode?: string | null
}) {
  const warnings = explanation.warnings ?? []
  return (
    <>
      <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cosa misura</h4>
        <p className="mt-1.5 text-sm text-slate-800">{explanation.description}</p>
        {explanation.purpose ? <p className="mt-2 text-sm text-slate-600">{explanation.purpose}</p> : null}
        {explanation.direction ? <p className="mt-2 text-sm text-slate-700">{explanation.direction}</p> : null}
        {explanation.mandatory_message ? (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
            {explanation.mandatory_message}
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Metriche della dimensione
        </h4>
        {(explanation.metrics || []).map((m) => (
          <MetricSection key={m.metric_key} metric={m} />
        ))}
      </section>

      {(explanation.display_transformations || []).length > 0 ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Trasformazioni di display
          </h4>
          <ul className="mt-2 space-y-2">
            {explanation.display_transformations!.map((t) => (
              <li key={t.key} className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700">
                <p className="font-mono text-[11px] text-slate-900">{t.formula_symbolic}</p>
                <p className="mt-1">
                  Matematico ({t.mathematical_value_key}): {fmt(t.mathematical_value)} → display:{' '}
                  {fmt(t.display_value)}
                </p>
                {t.message ? <p className="mt-1 text-amber-900">{t.message}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Perché questo risultato</h4>
        <p className="mt-1.5 text-sm text-slate-800">{explanation.reason_summary}</p>
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Origine dati</h4>
        <dl className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Bundle id</dt>
            <dd className="font-mono">{String(explanation.data_origin?.bundle_id ?? '—')}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Source mode</dt>
            <dd className="break-all">{sourceMode ?? '—'}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2.5 py-2 sm:col-span-2">
            <dt className="text-slate-500">Source path</dt>
            <dd className="font-mono text-[10px]">
              {String(explanation.data_origin?.source_path ?? '—')}
            </dd>
          </div>
        </dl>
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
  )
}

function CandidateBody({
  explanation,
  sourceMode,
}: {
  explanation: CecchinoGiV5CandidateExplanation
  sourceMode?: string | null
}) {
  const warnings = explanation.warnings ?? []
  const cal = explanation.calibrated_predictions
  const labels = explanation.research_status?.labels ?? [
    'Preview monitorata',
    'Non collegato ai Segnali',
    'Nessuna formula produttiva',
  ]

  return (
    <>
      <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cosa rappresenta</h4>
        <p className="mt-1.5 text-sm text-slate-800">{explanation.description}</p>
        {explanation.purpose ? <p className="mt-2 text-sm text-slate-600">{explanation.purpose}</p> : null}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {labels.map((l) => (
            <span
              key={l}
              className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-900"
            >
              {l}
            </span>
          ))}
        </div>
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Costruzione dello score
        </h4>
        {explanation.formula_symbolic ? (
          <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-[#0f2847] px-3 py-3 font-mono text-[12px] text-amber-100 whitespace-pre-wrap">
            {explanation.formula_symbolic}
          </pre>
        ) : null}
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
          {(explanation.formula_applied || []).map((step, i) => (
            <li key={`${i}-${step}`} className="font-mono text-[12px] text-slate-800">
              {step}
            </li>
          ))}
        </ol>
        {(explanation.components || []).length > 0 ? (
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full min-w-[360px] border-collapse text-left text-xs">
              <thead className="bg-slate-100 text-slate-600">
                <tr>
                  <th className="px-2 py-1.5 font-semibold">Componente</th>
                  <th className="px-2 py-1.5 font-semibold">Valore</th>
                  <th className="px-2 py-1.5 font-semibold">Peso</th>
                  <th className="px-2 py-1.5 font-semibold">Ruolo</th>
                </tr>
              </thead>
              <tbody>
                {explanation.components!.map((c) => (
                  <tr key={c.key} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 font-mono text-[11px]">{c.key}</td>
                    <td className="px-2 py-1.5 tabular-nums">{fmt(c.value)}</td>
                    <td className="px-2 py-1.5 tabular-nums">{c.weight == null ? '—' : fmt(c.weight, 3)}</td>
                    <td className="px-2 py-1.5 text-slate-600">{c.role ?? c.label ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {(explanation.excluded_components || []).length > 0 ? (
          <p className="mt-2 text-xs text-slate-600">
            Esclusi: <span className="font-medium">{explanation.excluded_components!.join(', ')}</span>
          </p>
        ) : null}
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div className="rounded border border-slate-200 px-2 py-2">
            <dt className="text-slate-500">Score persistito</dt>
            <dd className="font-mono font-semibold">{fmt(explanation.stored_score)}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2 py-2">
            <dt className="text-slate-500">Score audit</dt>
            <dd className="font-mono font-semibold">{fmt(explanation.audit_score)}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2 py-2">
            <dt className="text-slate-500">Consistency</dt>
            <dd>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusBadgeClass(
                  explanation.consistency?.status ?? '—',
                )}`}
              >
                {explanation.consistency?.status ?? '—'}
              </span>
            </dd>
          </div>
          <div className="rounded border border-slate-200 px-2 py-2">
            <dt className="text-slate-500">Pesi</dt>
            <dd className="text-[11px]">{explanation.weight_status ?? '—'}</dd>
          </div>
        </dl>
      </section>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Calibrazioni</h4>
        <CalibrationSection title="xG totali (lineare)" block={cal?.expected_total_goals} />
        <CalibrationSection title="P(≥2) (logistica)" block={cal?.probability_goals_ge_2} />
        <CalibrationSection title="P(≥3) (logistica)" block={cal?.probability_goals_ge_3} />
        <CalibrationSection title="P(BTTS) (logistica)" block={cal?.probability_btts} />
      </section>

      <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Perché questo risultato</h4>
        <p className="mt-1.5 text-sm text-slate-800">{explanation.reason_summary}</p>
        {explanation.difference_vs_primary != null ? (
          <p className="mt-2 text-xs text-slate-600">
            Differenza vs Primary: {fmt(explanation.difference_vs_primary)}
          </p>
        ) : null}
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Qualità e origine</h4>
        <dl className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Bundle</dt>
            <dd className="font-mono">
              {String(explanation.quality?.bundle_id ?? '—')} · {String(explanation.quality?.bundle_version ?? '')}
            </dd>
          </div>
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Frozen at</dt>
            <dd>{String(explanation.quality?.bundle_frozen_at ?? '—')}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Source snapshot</dt>
            <dd>{String(explanation.quality?.source_snapshot_at ?? '—')}</dd>
          </div>
          <div className="rounded border border-slate-200 px-2.5 py-2">
            <dt className="text-slate-500">Source mode</dt>
            <dd className="break-all">{sourceMode ?? '—'}</dd>
          </div>
        </dl>
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
  )
}

export function CecchinoGoalIntensityV5AuditModal({
  type,
  explanation,
  sourceMode,
  onClose,
}: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const isDim = type === 'dimension'
  const dim = isDim ? (explanation as CecchinoGiV5DimensionExplanation) : null
  const cand = !isDim ? (explanation as CecchinoGiV5CandidateExplanation) : null

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
        className="flex max-h-[90vh] w-full max-w-[900px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="shrink-0 border-b border-slate-200 bg-[#1e3a5f] px-4 py-3 text-white sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p id={titleId} className="text-sm font-bold tracking-wide sm:text-base">
                {isDim
                  ? 'Analisi dimensione Goal Intensity v5'
                  : 'Analisi candidato Goal Intensity v5'}
              </p>
              <p className="mt-1 text-xs text-slate-200">
                {isDim ? (
                  <>
                    {dim!.dimension_number}.{' '}
                    <span className="font-semibold text-white">{dim!.title}</span>
                  </>
                ) : (
                  <>
                    <span className="font-semibold text-white">{cand!.candidate_id}</span>
                    {' · '}
                    {cand!.role}
                  </>
                )}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="rounded border border-violet-300/40 bg-violet-500/20 px-1.5 py-0.5 text-[10px] text-violet-100">
                  Preview monitorata
                </span>
                <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                  Non collegato ai Segnali
                </span>
                <span className="rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-100">
                  Nessuna formula produttiva
                </span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusBadgeClass(
                    isDim ? dim!.status : cand!.status,
                  )}`}
                >
                  {isDim ? dim!.status : cand!.status}
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
          {isDim ? (
            <DimensionBody explanation={dim!} sourceMode={sourceMode} />
          ) : (
            <CandidateBody explanation={cand!} sourceMode={sourceMode} />
          )}
        </div>
      </div>
    </div>
  )
}
