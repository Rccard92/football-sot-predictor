type Props = {
  market: {
    cecchino: Record<string, unknown>
    book: Record<string, unknown>
    comparison: Record<string, unknown>
    roi: Record<string, unknown>
  }
}

export function DrawCredibilityMarketAnalysisPanel({ market }: Props) {
  const roi = market.roi
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Analisi mercato (coorte Market)</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-100 p-3 text-xs">
          <p className="font-medium text-slate-700">Cecchino X</p>
          <p>Brier: {String(market.cecchino.brier_score ?? '—')}</p>
          <p>AUC: {String(market.cecchino.auc ?? '—')}</p>
        </div>
        <div className="rounded-lg border border-slate-100 p-3 text-xs">
          <p className="font-medium text-slate-700">Book X</p>
          <p>Brier: {String(market.book.brier_score ?? '—')}</p>
          <p>AUC: {String(market.book.auc ?? '—')}</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-600">
        Δ Brier Cecchino−Book: {String(market.comparison.delta_brier ?? '—')}
      </p>
      <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs text-amber-900">
        <p className="font-medium">ROI teorico flat stake su quota Book X</p>
        <p>
          Scommesse: {String(roi.bets ?? 0)} · ROI:{' '}
          {typeof roi.roi_pct === 'number' ? `${roi.roi_pct.toFixed(2)}%` : '—'}
        </p>
        {(roi.warnings as string[] | undefined)?.map((w) => (
          <p key={w} className="mt-1 text-amber-800">
            {w}
          </p>
        ))}
      </div>
    </section>
  )
}
