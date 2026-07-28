import type { ReactNode } from 'react'
import {
  patternSampleBadgeLabel,
  patternStabilityBadgeLabel,
  type HistoricalRunPattern,
} from '../../../lib/cecchinoLabApi'

type Props = {
  positive: HistoricalRunPattern[]
  negative: HistoricalRunPattern[]
  watchlist: HistoricalRunPattern[]
  unstable: HistoricalRunPattern[]
  diagnostics?: HistoricalRunPattern[]
}

export function HistoricalRunPatterns({
  positive,
  negative,
  watchlist,
  unstable,
  diagnostics = [],
}: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Pattern Radar</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Ogni pattern è legato a un mercato. Nessuna giocata automatica. Diagnostiche assenze dati
        separate dai candidati.
      </p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Group title="Positivi" items={positive} tone="ok" />
        <Group title="Negativi" items={negative} tone="err" />
        <Group title="Da osservare" items={watchlist} tone="warn" />
        <Group title="Instabili / concentrati" items={unstable} tone="muted" />
      </div>
      {diagnostics.length > 0 ? (
        <div className="mt-4">
          <Group title="Diagnostica copertura (assenze dati)" items={diagnostics} tone="muted" />
        </div>
      ) : null}
    </section>
  )
}

function Group({
  title,
  items,
  tone,
}: {
  title: string
  items: HistoricalRunPattern[]
  tone: 'ok' | 'err' | 'warn' | 'muted'
}) {
  const color =
    tone === 'ok'
      ? 'var(--lab-ok)'
      : tone === 'err'
        ? 'var(--lab-err)'
        : tone === 'warn'
          ? 'var(--lab-warn)'
          : 'var(--lab-muted)'
  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <div className="mb-2 font-medium" style={{ color }}>
        {title} ({items.length})
      </div>
      <ul className="max-h-72 space-y-2 overflow-auto text-xs">
        {items.slice(0, 12).map((p) => {
          const mk =
            p.market_key ||
            (typeof p.conditions?.market_key === 'string' ? p.conditions.market_key : null)
          const stabCat =
            p.cross_competition_stability ||
            (p.stability && typeof p.stability.cross_competition_stability === 'string'
              ? String(p.stability.cross_competition_stability)
              : null)
          const small = (p.real_quote_count ?? 0) < 30
          return (
            <li key={p.pattern_id} className="border-b border-white/5 pb-2">
              <div className="font-medium">
                {mk ? `[${mk}] ` : ''}
                {p.title ?? p.pattern_id}
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                <Badge>{patternSampleBadgeLabel(p.status)}</Badge>
                <Badge>{patternStabilityBadgeLabel(stabCat)}</Badge>
                {small ? <Badge warn>Campione piccolo</Badge> : null}
              </div>
              <div className="mt-1 text-[var(--lab-muted)]">
                N {p.sample_size} · reali {p.real_quote_count} · campionati {p.competitions_count}
                {p.main_competition_share != null
                  ? ` · conc. ${Math.round(p.main_competition_share * 100)}%`
                  : ''}{' '}
                · hit {p.hit_rate != null ? `${(p.hit_rate * 100).toFixed(1)}%` : '—'} · ROI{' '}
                {p.real_roi != null ? `${p.real_roi}%` : '—'}
              </div>
              {p.limitations?.length ? (
                <div className="mt-0.5 text-[10px] text-[var(--lab-muted)]">
                  {p.limitations.slice(0, 2).join(' · ')}
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Badge({ children, warn }: { children: ReactNode; warn?: boolean }) {
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px]"
      style={{
        background: warn ? 'rgba(255,180,60,0.15)' : 'rgba(46,230,255,0.1)',
        color: warn ? 'var(--lab-warn)' : 'var(--lab-cyan)',
      }}
    >
      {children}
    </span>
  )
}
