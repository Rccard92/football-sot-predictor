import type {
  HistoricalKpiHeatmapCell,
  HistoricalKpiSignalsFilters,
  HistoricalKpiSignalsSummary,
} from '../../../lib/cecchinoLabApi'
import {
  formatProfit,
  formatRoi,
  marketLabel,
  quoteTypeMatchesFilter,
  roiBgColor,
  sampleClassBorder,
  sampleClassOpacity,
} from './historicalKpiUtils'

type Props = {
  heatmap: HistoricalKpiSignalsSummary['heatmap']
  quoteType: HistoricalKpiSignalsFilters['quote_type']
  activeRatingBucket?: string
  activeSelectionKey?: string
  onCellClick: (ratingBucket: string, selectionKey: string) => void
}

export function HistoricalKpiHeatmap({
  heatmap,
  quoteType,
  activeRatingBucket,
  activeSelectionKey,
  onCellClick,
}: Props) {
  const { rating_buckets, selection_keys, cells } = heatmap

  function cellAt(bucket: string, selectionKey: string): HistoricalKpiHeatmapCell | undefined {
    return cells.find(
      (c) =>
        c.rating_bucket === bucket &&
        c.selection_key === selectionKey &&
        quoteTypeMatchesFilter(c.quote_type, quoteType),
    )
  }

  return (
    <section data-testid="historical-kpi-heatmap">
      <h3 className="mb-2 text-lg font-semibold">Heatmap rating × mercato</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Colore = ROI · opacità/bordo = dimensione campione. Clic per filtrare attivazioni.
      </p>
      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Mercato</th>
              {rating_buckets.map((b) => (
                <th key={b} className="text-center">
                  {b}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {selection_keys.map((sk) => (
              <tr key={sk}>
                <td className="font-medium">{marketLabel(sk)}</td>
                {rating_buckets.map((bucket) => {
                  const cell = cellAt(bucket, sk)
                  const active =
                    activeRatingBucket === bucket && activeSelectionKey === sk
                  if (!cell) {
                    return (
                      <td key={bucket} className="text-center text-[var(--lab-muted)]">
                        —
                      </td>
                    )
                  }
                  const opacity = sampleClassOpacity(cell.sample_class)
                  const bg = roiBgColor(cell.roi_pct)
                  return (
                    <td key={bucket} className="p-1">
                      <button
                        type="button"
                        onClick={() => onCellClick(bucket, sk)}
                        className="w-full rounded-lg px-2 py-2 text-center text-xs transition hover:brightness-110"
                        style={{
                          background: bg,
                          opacity,
                          border: sampleClassBorder(cell.sample_class),
                          outline: active ? '2px solid var(--lab-cyan)' : undefined,
                        }}
                        title={`${sk} · ${bucket} · N=${cell.signals_count} · ROI ${formatRoi(cell.roi_pct)}`}
                      >
                        <div className="font-semibold">{cell.signals_count}</div>
                        <div>{formatRoi(cell.roi_pct)}</div>
                        <div className="text-[10px] text-[var(--lab-muted)]">{formatProfit(cell.profit_units)}</div>
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
