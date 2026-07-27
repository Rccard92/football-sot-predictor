import { motion } from 'framer-motion'
import type { CecchinoLabInsight } from '../../../lib/cecchinoLabApi'

type Props = { insights: CecchinoLabInsight[] }

const TONE: Record<string, string> = {
  positive: 'var(--lab-ok)',
  neutral: 'var(--lab-muted)',
  warning: 'var(--lab-warn)',
  accent: 'var(--lab-cyan)',
}

export function BettingInsights({ insights }: Props) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Betting Insights
      </h2>
      <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
        Insight deterministici sul campione storico. Non sono raccomandazioni future.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {insights.map((ins, i) => (
          <motion.article
            key={ins.key}
            className="rounded-2xl p-4"
            style={{
              background: 'linear-gradient(150deg, rgba(26,47,71,0.9), rgba(15,28,44,0.95))',
              border: `1px solid ${TONE[ins.tone] || 'var(--lab-border)'}44`,
            }}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04, duration: 0.25 }}
          >
            <div className="text-[11px] uppercase tracking-wider" style={{ color: TONE[ins.tone] }}>
              {ins.title}
            </div>
            <div className="mt-2 text-xl font-semibold tabular-nums" style={{ color: 'var(--lab-text)' }}>
              {ins.value}
            </div>
            <p className="mt-2 text-xs leading-relaxed" style={{ color: 'var(--lab-muted)' }}>
              {ins.description}
            </p>
            <div className="mt-2 text-[10px]" style={{ color: 'var(--lab-muted)' }}>
              n={ins.sample_size.toLocaleString('it-IT')}
              {ins.competition_name ? ` · ${ins.competition_name}` : ''}
            </div>
          </motion.article>
        ))}
        {insights.length === 0 ? (
          <div className="col-span-full py-8 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
            Nessun insight (serve campione sufficiente, tipicamente ≥100 partite per campionato).
          </div>
        ) : null}
      </div>
    </section>
  )
}
