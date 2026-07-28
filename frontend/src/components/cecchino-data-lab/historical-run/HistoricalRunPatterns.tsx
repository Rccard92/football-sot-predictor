import type { HistoricalRunPattern } from '../../../lib/cecchinoLabApi'

type Props = {
  positive: HistoricalRunPattern[]
  negative: HistoricalRunPattern[]
  watchlist: HistoricalRunPattern[]
  unstable: HistoricalRunPattern[]
}

export function HistoricalRunPatterns({ positive, negative, watchlist, unstable }: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Pattern Radar</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Pattern candidato da verificare. Nessuna modifica automatica alle formule.
      </p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Group title="Positivi" items={positive} tone="ok" />
        <Group title="Negativi" items={negative} tone="err" />
        <Group title="Da osservare" items={watchlist} tone="warn" />
        <Group title="Instabili" items={unstable} tone="muted" />
      </div>
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
      <ul className="max-h-64 space-y-2 overflow-auto text-xs">
        {items.slice(0, 12).map((p) => (
          <li key={p.pattern_id} className="border-b border-white/5 pb-2">
            <div className="font-medium">{p.title ?? p.pattern_id}</div>
            <div className="text-[var(--lab-muted)]">
              N {p.sample_size} · hit{' '}
              {p.hit_rate != null ? `${(p.hit_rate * 100).toFixed(1)}%` : '—'} · ROI{' '}
              {p.real_roi ?? '—'}% · {p.status}
            </div>
          </li>
        ))}
        {items.length === 0 ? (
          <li className="text-[var(--lab-muted)]">Nessun pattern in questo gruppo</li>
        ) : null}
      </ul>
    </div>
  )
}
