import type { ReactNode } from 'react'

/** Tema locale Pattern Insights — pannello scuro isolato dal tema chiaro
 * dell'app, come fa Cecchino Lab. Nessuna dipendenza dal suo shell: questa
 * e' una sezione separata e deve poter vivere da sola. */
export function PatternInsightsShell({ children }: { children: ReactNode }) {
  return (
    <div className="pi-root">
      <style>{`
        .pi-root {
          --pi-bg: #080d19;
          --pi-panel: #0e1526;
          --pi-panel-2: #131c31;
          --pi-border: #1e2a44;
          --pi-text: #e8eef9;
          --pi-muted: #8494b0;
          --pi-accent: #35e0c4;
          --pi-accent-2: #7c8cff;
          --pi-pos: #34d399;
          --pi-neg: #f87171;
          --pi-warn: #fbbf24;
          background:
            radial-gradient(1200px 400px at 15% -10%, rgba(53,224,196,0.10), transparent 60%),
            radial-gradient(900px 380px at 85% -5%, rgba(124,140,255,0.10), transparent 60%),
            var(--pi-bg);
          color: var(--pi-text);
          border: 1px solid var(--pi-border);
          border-radius: 18px;
          padding: 24px;
          min-height: calc(100vh - 90px);
        }
        .pi-section {
          background: var(--pi-panel);
          border: 1px solid var(--pi-border);
          border-radius: 14px;
          padding: 18px;
        }
        .pi-section-title {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--pi-accent);
        }
        .pi-kpi {
          position: relative;
          overflow: hidden;
          background: var(--pi-panel-2);
          border: 1px solid var(--pi-border);
          border-radius: 14px;
          padding: 14px 16px;
        }
        .pi-kpi::after {
          content: '';
          position: absolute;
          top: -40px; right: -40px;
          width: 120px; height: 120px;
          border-radius: 999px;
          background: radial-gradient(circle, rgba(53,224,196,0.16), transparent 70%);
          pointer-events: none;
        }
        .pi-tile {
          background: var(--pi-panel-2);
          border: 1px solid var(--pi-border);
          border-radius: 12px;
          padding: 12px 14px;
        }
        .pi-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
        .pi-table th {
          text-align: left;
          font-size: 10px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--pi-muted);
          padding: 8px 10px;
          border-bottom: 1px solid var(--pi-border);
          position: sticky; top: 0;
          background: var(--pi-panel);
          z-index: 1;
        }
        .pi-table td {
          padding: 9px 10px;
          border-bottom: 1px solid rgba(30,42,68,0.6);
          color: var(--pi-text);
          vertical-align: top;
        }
        .pi-table tbody tr:hover td { background: rgba(53,224,196,0.05); }
        .pi-input, .pi-select {
          background: var(--pi-panel-2);
          border: 1px solid var(--pi-border);
          color: var(--pi-text);
          border-radius: 9px;
          padding: 7px 10px;
          font-size: 13px;
        }
        .pi-btn {
          background: var(--pi-panel-2);
          border: 1px solid var(--pi-border);
          color: var(--pi-text);
          border-radius: 9px;
          padding: 7px 12px;
          font-size: 12px;
          cursor: pointer;
        }
        .pi-btn:disabled { opacity: 0.35; cursor: default; }
        .pi-chip {
          display: inline-flex; align-items: center; gap: 6px;
          background: rgba(53,224,196,0.10);
          border: 1px solid rgba(53,224,196,0.30);
          color: var(--pi-accent);
          border-radius: 999px;
          padding: 3px 10px;
          font-size: 11px;
          font-weight: 600;
        }
        .pi-scroll { overflow: auto; max-height: 460px; }
        .pi-scroll::-webkit-scrollbar { width: 10px; height: 10px; }
        .pi-scroll::-webkit-scrollbar-thumb { background: #1f2b45; border-radius: 8px; }
      `}</style>
      {children}
    </div>
  )
}

export function Section({
  title,
  note,
  children,
  className = '',
}: {
  title: string
  note?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`pi-section ${className}`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="pi-section-title">{title}</h2>
        {note ? <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>{note}</div> : null}
      </div>
      {children}
    </section>
  )
}

export function Kpi({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'pos' | 'neg' | 'warn' | 'accent'
}) {
  const color =
    tone === 'pos'
      ? 'var(--pi-pos)'
      : tone === 'neg'
        ? 'var(--pi-neg)'
        : tone === 'warn'
          ? 'var(--pi-warn)'
          : tone === 'accent'
            ? 'var(--pi-accent)'
            : 'var(--pi-text)'
  return (
    <div className="pi-kpi">
      <div
        className="text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: 'var(--pi-muted)' }}
      >
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color }}>
        {value}
      </div>
      {hint ? (
        <div className="mt-0.5 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          {hint}
        </div>
      ) : null}
    </div>
  )
}

/** Sfondo a intensita' per le celle numeriche delle tabelle "heatmap". */
export function heatBg(value: number | null | undefined, max: number, positive = true): string {
  if (value == null || max <= 0) return 'transparent'
  const ratio = Math.min(1, Math.abs(value) / max)
  const rgb = positive ? '53,224,196' : '248,113,113'
  return `rgba(${rgb},${(ratio * 0.28).toFixed(3)})`
}
