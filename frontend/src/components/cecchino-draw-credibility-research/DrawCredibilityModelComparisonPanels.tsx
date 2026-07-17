function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Number.isFinite(v) ? v.toFixed(4) : '—'
  return String(v)
}

type Props = { analysis: Record<string, unknown> | null | undefined }

export function DrawCredibilityTemporalStructurePanel({ analysis }: Props) {
  const split = (analysis?.split_definition ?? {}) as Record<string, unknown>
  const checks = (analysis?.split_consistency_checks ?? {}) as Record<string, unknown>
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Struttura temporale</h3>
      <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
        <p>Development: {fmt(split.development_date_from)} → {fmt(split.development_date_to)}</p>
        <p>Holdout: {fmt(split.holdout_date_from)} → {fmt(split.holdout_date_to)}</p>
        <p>Dev rows / draws: {fmt(split.development_rows)} / {fmt(split.development_draws)}</p>
        <p>Holdout rows / draws: {fmt(split.holdout_rows)} / {fmt(split.holdout_draws)}</p>
        <p>Actual holdout %: {fmt(split.actual_holdout_pct)}</p>
        <p>Same-date split: {String(checks.same_date_split ?? '—')}</p>
        <p>Date overlap: {fmt(checks.date_overlap_count)}</p>
        <p>Holdout untouched until CV: {String(checks.holdout_untouched_until_after_cv ?? '—')}</p>
      </div>
    </section>
  )
}

export function DrawCredibilityModelLeaderboardTable({
  rows,
}: {
  rows: Array<Record<string, unknown>> | undefined
}) {
  if (!rows?.length) return null
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm overflow-x-auto">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Model leaderboard</h3>
      <p className="mb-2 text-xs text-slate-500">Ordinata per holdout Brier; nessun vincitore automatico.</p>
      <table className="min-w-full text-left text-xs">
        <thead className="border-b text-slate-500">
          <tr>
            <th className="py-1 pr-2">Model</th>
            <th className="py-1 pr-2">Eligibility</th>
            <th className="py-1 pr-2">C</th>
            <th className="py-1 pr-2">Dev Brier</th>
            <th className="py-1 pr-2">Hold Brier</th>
            <th className="py-1 pr-2">BSS</th>
            <th className="py-1 pr-2">AUC</th>
            <th className="py-1 pr-2">LogLoss</th>
            <th className="py-1 pr-2">ECE</th>
            <th className="py-1 pr-2">Complexity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.model_key)} className="border-b border-slate-100">
              <td className="py-1 pr-2 font-medium">{String(r.model_label ?? r.model_key)}</td>
              <td className="py-1 pr-2">{String(r.eligibility)}</td>
              <td className="py-1 pr-2">{fmt(r.selected_C)}</td>
              <td className="py-1 pr-2">{fmt(r.development_mean_brier)}</td>
              <td className="py-1 pr-2">{fmt(r.holdout_brier)}</td>
              <td className="py-1 pr-2">{fmt(r.holdout_brier_skill)}</td>
              <td className="py-1 pr-2">{fmt(r.holdout_auc)}</td>
              <td className="py-1 pr-2">{fmt(r.holdout_log_loss)}</td>
              <td className="py-1 pr-2">{fmt(r.holdout_ece)}</td>
              <td className="py-1 pr-2">
                {fmt((r.complexity as Record<string, unknown> | undefined)?.effective_complexity)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function DrawCredibilityModelDetailPanel({
  analysis,
  selectedKey,
  onSelect,
}: {
  analysis: Record<string, unknown> | null | undefined
  selectedKey: string
  onSelect: (k: string) => void
}) {
  const defs = (analysis?.model_definitions as Array<Record<string, unknown>>) ?? []
  const hold = ((analysis?.final_holdout_results as Array<Record<string, unknown>>) ?? []).find(
    (r) => r.model_key === selectedKey,
  )
  const stab = ((analysis?.coefficient_stability as Record<string, Array<Record<string, unknown>>>) ??
    {})[selectedKey]
  const def = defs.find((d) => d.model_key === selectedKey)
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Dettaglio modello</h3>
      <select
        className="mb-3 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
        value={selectedKey}
        onChange={(e) => onSelect(e.target.value)}
      >
        {defs.map((d) => (
          <option key={String(d.model_key)} value={String(d.model_key)}>
            {String(d.model_label ?? d.model_key)}
          </option>
        ))}
      </select>
      <div className="space-y-2 text-xs text-slate-700">
        <p>Features: {(def?.features as string[] | undefined)?.join(', ') ?? '—'}</p>
        <p>Interactions: {(def?.interactions as string[] | undefined)?.join(', ') || '—'}</p>
        <p>C: {fmt(hold?.C)}</p>
        <p>Control only: {String(def?.control_only ?? false)}</p>
        {stab?.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead>
                <tr className="text-slate-500">
                  <th className="pr-2">Feature</th>
                  <th className="pr-2">Mean</th>
                  <th className="pr-2">Std</th>
                  <th className="pr-2">Sign Δ</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {stab.slice(0, 40).map((s) => (
                  <tr key={String(s.feature_encoded)}>
                    <td className="pr-2">{String(s.feature_encoded)}</td>
                    <td className="pr-2">{fmt(s.mean)}</td>
                    <td className="pr-2">{fmt(s.std)}</td>
                    <td className="pr-2">{fmt(s.sign_changes)}</td>
                    <td>{String(s.stability_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500">Nessun coefficiente (baseline/raw).</p>
        )}
      </div>
    </section>
  )
}

export function DrawCredibilityModelCalibrationPanel({
  analysis,
}: {
  analysis: Record<string, unknown> | null | undefined
}) {
  const cal = (analysis?.calibration_analysis ?? {}) as Record<string, Record<string, unknown>>
  const keys = Object.keys(cal)
  if (!keys.length) return null
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm overflow-x-auto">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Calibrazione</h3>
      <table className="min-w-full text-left text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="pr-2">Model</th>
            <th className="pr-2">Slope</th>
            <th className="pr-2">Intercept</th>
            <th className="pr-2">ECE</th>
            <th>Pred mean</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className="border-b border-slate-100">
              <td className="pr-2 py-1">{k}</td>
              <td className="pr-2">{fmt(cal[k].calibration_slope)}</td>
              <td className="pr-2">{fmt(cal[k].calibration_intercept)}</td>
              <td className="pr-2">{fmt(cal[k].ece)}</td>
              <td>{fmt(cal[k].holdout_prediction_mean)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function DrawCredibilityMarginalContributionsPanel({
  rows,
}: {
  rows: Array<Record<string, unknown>> | undefined
}) {
  if (!rows?.length) return null
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Contributi marginali</h3>
      <ul className="space-y-1 text-xs text-slate-700">
        {rows.map((r) => (
          <li key={`${r.from_model}-${r.to_model}`}>
            {String(r.comparison)}: Δ Brier holdout = {fmt(r.holdout_brier_delta)} ({String(r.from_model)} →{' '}
            {String(r.to_model)})
          </li>
        ))}
      </ul>
    </section>
  )
}

export function DrawCredibilityTemporalFoldsPanel({
  rows,
}: {
  rows: Array<Record<string, unknown>> | undefined
}) {
  if (!rows?.length) return null
  const sample = rows.filter((r) => r.model_key === rows[0]?.model_key)
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm overflow-x-auto">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Temporal folds (es. {String(rows[0]?.model_key)})</h3>
      <table className="min-w-full text-left text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="pr-2">Fold</th>
            <th className="pr-2">Train dates</th>
            <th className="pr-2">Val dates</th>
            <th className="pr-2">Brier</th>
            <th className="pr-2">BSS</th>
            <th>AUC</th>
          </tr>
        </thead>
        <tbody>
          {sample.map((r) => (
            <tr key={String(r.fold_id)} className="border-b border-slate-100">
              <td className="pr-2 py-1">{String(r.fold_id)}</td>
              <td className="pr-2">{Array.isArray(r.train_dates) ? r.train_dates.length : '—'}</td>
              <td className="pr-2">{Array.isArray(r.validation_dates) ? r.validation_dates.length : '—'}</td>
              <td className="pr-2">{fmt(r.brier_score)}</td>
              <td className="pr-2">{fmt(r.brier_skill_score)}</td>
              <td>{fmt(r.auc)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function DrawCredibilityMarketOofPanel({
  market,
}: {
  market: Record<string, unknown> | undefined
}) {
  if (!market) return null
  const breakdowns = (market.roi_breakdowns as Array<Record<string, unknown>>) ?? []
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">OOF Market</h3>
      <p className="mb-2 text-xs text-slate-600">
        Modello {String(market.model_key ?? '—')} · rows {fmt(market.market_oof_rows)} · mean edge{' '}
        {fmt(market.mean_edge)}
      </p>
      <ul className="space-y-1 text-xs">
        {breakdowns.map((b) => (
          <li key={String(b.label)}>
            {String(b.label)}: bets={fmt(b.bets)} ROI={fmt(b.roi)} status={String(b.profitable_status)}
          </li>
        ))}
      </ul>
      {(market.notes as string[] | undefined)?.map((n) => (
        <p key={n} className="mt-1 text-xs text-amber-700">
          {n}
        </p>
      ))}
    </section>
  )
}

export function DrawCredibilityReducedModelPanel({
  reduced,
}: {
  reduced: Record<string, unknown> | undefined
}) {
  if (!reduced) return null
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Modello ridotto</h3>
      <div className="space-y-1 text-xs text-slate-700">
        <p>Status: {String(reduced.status)}</p>
        <p>Source: {String(reduced.reduced_model_source ?? '—')}</p>
        <p>Reduced: {String(reduced.reduced_model_key ?? '—')}</p>
        <p>Retained: {((reduced.retained_features as string[]) ?? []).join(', ') || '—'}</p>
        <p>Removed: {((reduced.removed_features as string[]) ?? []).join(', ') || '—'}</p>
        <p>Selection on holdout: {String(reduced.selection_on_holdout ?? false)}</p>
      </div>
    </section>
  )
}

export function DrawCredibilityModelDecisionPanel({
  decision,
}: {
  decision: Record<string, unknown> | undefined
}) {
  if (!decision) return null
  return (
    <section className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-violet-950">Decisione Fase 1D</h3>
      <div className="space-y-1 text-xs text-violet-950">
        <p>Status: {String(decision.status)}</p>
        <p>Leading: {String(decision.leading_model ?? '—')}</p>
        <p>Reduced: {String(decision.reduced_model ?? '—')}</p>
        <p>Production change allowed: {String(decision.production_change_allowed)}</p>
        <p>Next history days: {fmt(decision.required_next_history_days)}</p>
        <p>Reasons: {((decision.reasons as string[]) ?? []).join('; ') || '—'}</p>
        <p>Limitations: {((decision.limitations as string[]) ?? []).join('; ') || '—'}</p>
      </div>
    </section>
  )
}
