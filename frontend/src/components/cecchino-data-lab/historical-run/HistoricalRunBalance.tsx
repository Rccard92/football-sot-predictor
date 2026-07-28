import type { HistoricalRunBalanceAnalytics } from '../../../lib/cecchinoLabApi'

type Props = { data: HistoricalRunBalanceAnalytics }

export function HistoricalRunBalance({ data }: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Balance Lab</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        {data.note ??
          'Quattro pilastri osservazionali. Nessun consiglio gioca/non giocare.'}
      </p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {data.pillars.map((p) => (
          <div
            key={String(p.key)}
            className="rounded-xl border p-3"
            style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
          >
            <div className="font-medium">{String(p.label ?? p.key)}</div>
            <div className="mt-1 text-xs text-[var(--lab-muted)]">
              {String(p.observation_status)} · N {String(p.sample_size)}
            </div>
            <div className="mt-2 text-[11px]">
              C {String(p.complete_count)} · P {String(p.partial_count)} · N/D{' '}
              {String(p.unavailable_count)}
            </div>
            <div className="mt-2 max-h-24 overflow-auto text-[11px] text-[var(--lab-muted)]">
              {Object.entries((p.class_distribution as Record<string, number>) || {}).map(
                ([k, v]) => (
                  <div key={k}>
                    {k}: {v}
                  </div>
                ),
              )}
            </div>
          </div>
        ))}
      </div>
      {data.combinations.length > 0 ? (
        <div className="mt-4">
          <h4 className="mb-2 text-sm font-medium">Combinazioni (sample sufficiente)</h4>
          <div className="lab-table-wrap overflow-x-auto">
            <table className="lab-table w-full text-xs">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>N</th>
                  <th>Hit</th>
                  <th>ROI reale</th>
                </tr>
              </thead>
              <tbody>
                {data.combinations.slice(0, 20).map((c) => (
                  <tr key={`${c.combination_id}-${JSON.stringify(c.conditions)}`}>
                    <td>{String(c.combination_id)}</td>
                    <td>{String(c.sample_size)}</td>
                    <td>
                      {c.hit_rate != null
                        ? `${(Number(c.hit_rate) * 100).toFixed(1)}%`
                        : '—'}
                    </td>
                    <td>{c.real_roi != null ? `${c.real_roi}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}
