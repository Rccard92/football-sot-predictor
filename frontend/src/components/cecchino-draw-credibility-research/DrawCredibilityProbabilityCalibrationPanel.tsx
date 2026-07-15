type Props = {
  calibration: Record<string, unknown>
}

export function DrawCredibilityProbabilityCalibrationPanel({ calibration }: Props) {
  const bins = (calibration.calibration_bins as Array<Record<string, unknown>>) ?? []
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Calibrazione probabilità X</h3>
      <div className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
        {[
          ['Brier', calibration.brier_score],
          ['BSS', calibration.brier_skill_score],
          ['Log loss', calibration.log_loss],
          ['AUC', calibration.auc],
          ['ECE', calibration.ece],
        ].map(([label, val]) => (
          <div key={String(label)} className="rounded-lg border border-slate-100 px-2 py-2">
            <p className="text-[10px] uppercase text-slate-500">{String(label)}</p>
            <p className="font-semibold tabular-nums text-slate-900">
              {typeof val === 'number' ? val.toFixed(4) : '—'}
            </p>
          </div>
        ))}
      </div>
      <table className="min-w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-2 text-left">Predetto</th>
            <th className="py-1 pr-2 text-left">Osservato</th>
            <th className="py-1 pr-2 text-left">Gap</th>
            <th className="py-1 text-left">N</th>
          </tr>
        </thead>
        <tbody>
          {bins.map((b, i) => (
            <tr key={i} className="border-t border-slate-100">
              <td className="py-1 pr-2 tabular-nums">{String(b.predicted_mean ?? '—')}</td>
              <td className="py-1 pr-2 tabular-nums">{String(b.actual_rate ?? '—')}</td>
              <td className="py-1 pr-2 tabular-nums">{String(b.calibration_gap ?? '—')}</td>
              <td className="py-1 tabular-nums">{String(b.count ?? '—')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
