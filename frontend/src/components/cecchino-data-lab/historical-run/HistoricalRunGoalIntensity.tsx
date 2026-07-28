import type { HistoricalRunGoalIntensityAnalytics } from '../../../lib/cecchinoLabApi'

type Props = { data: HistoricalRunGoalIntensityAnalytics }

export function HistoricalRunGoalIntensity({ data }: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Intensità Goal Lab</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        {data.note ??
          'Record parziali visibili. Dati mancanti non azzerati. Modulo osservazionale.'}
      </p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {data.components.map((c) => (
          <div
            key={String(c.key)}
            className="rounded-xl border p-3"
            style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
          >
            <div className="font-medium">{String(c.label ?? c.key)}</div>
            <div className="mt-2 text-[11px]">
              Completi {String(c.complete_count)} · Parziali {String(c.partial_count)} · N/D{' '}
              {String(c.unavailable_count)} · Missing {String(c.missing_count)}
            </div>
            <div className="mt-2 text-xs text-[var(--lab-muted)]">
              Over/Under legati ai mercati goal nella tabella sottostante.
            </div>
            <div className="mt-2 space-y-1 text-[11px]">
              {Object.entries((c.goal_markets as Record<string, { hit_rate?: number; sample_size?: number }>) || {})
                .slice(0, 4)
                .map(([mk, v]) => (
                  <div key={mk}>
                    {mk}: N {v.sample_size ?? 0} · hit{' '}
                    {v.hit_rate != null ? `${(v.hit_rate * 100).toFixed(0)}%` : '—'}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
