import type { ReactNode } from 'react'
import type { PatternLabModuleInsights } from '../../../lib/patternLabApi'
import { formatNum, formatPct } from '../../../lib/patternLabApi'

type Props = { insights: PatternLabModuleInsights }

function DistroBars({ items, maxBars = 8 }: { items: Array<{ key: string; count: number }>; maxBars?: number }) {
  const rows = items.slice(0, maxBars)
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div className="mt-2 space-y-1.5">
      {rows.map((r) => (
        <div key={r.key} className="grid grid-cols-[88px_1fr_36px] items-center gap-2 text-xs">
          <span className="truncate" style={{ color: 'var(--lab-muted)' }}>
            {r.key}
          </span>
          <div className="h-2 overflow-hidden rounded" style={{ background: 'rgba(46,230,255,0.08)' }}>
            <div
              className="h-full rounded"
              style={{
                width: `${(r.count / max) * 100}%`,
                background: 'var(--lab-cyan)',
              }}
            />
          </div>
          <span className="tabular-nums text-right">{r.count}</span>
        </div>
      ))}
      {!rows.length ? (
        <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
          Nessun dato
        </p>
      ) : null}
    </div>
  )
}

function InsightCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="lab-card rounded-xl p-4">
      <h3 className="text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

export function PatternLabModuleInsights({ insights }: Props) {
  const excel = insights.signals.excel_column_frequency || {}
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Insight moduli
      </h2>
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <InsightCard title="KPI · Rating / Value / Edge">
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Value+ {insights.kpi.value_positive_count} · Value− {insights.kpi.value_negative_count} ·
            Edge medio {formatNum(insights.kpi.avg_edge_pct, 1)}%
          </p>
          <DistroBars items={insights.kpi.rating_bands} />
        </InsightCard>

        <InsightCard title="Cecchino Signals">
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Active {insights.signals.active_count} ({formatPct(insights.signals.active_rate)}) · D:{' '}
            {excel.D ?? 0} E:{excel.E ?? 0} F:{excel.F ?? 0} G:{excel.G ?? 0}
          </p>
          <DistroBars items={insights.signals.count_distribution} />
        </InsightCard>

        <InsightCard title="Equilibrio vs Squilibrio">
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Geometry media {formatNum(insights.balance.avg_geometry, 1)}
          </p>
          <DistroBars items={insights.balance.structural_class_distribution} />
        </InsightCard>

        <InsightCard title="Goal V4-compat">
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Composite medio {formatNum(insights.goal_v4_compat.avg_composite, 1)}
          </p>
          <DistroBars items={insights.goal_v4_compat.final_class_distribution} />
        </InsightCard>

        <InsightCard title="Acquistabilità V3.6">
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Distribuzione score / class
          </p>
          <DistroBars items={insights.purchasability_v36.score_bands} />
          <DistroBars items={insights.purchasability_v36.class_distribution} maxBars={6} />
        </InsightCard>
      </div>
    </section>
  )
}
