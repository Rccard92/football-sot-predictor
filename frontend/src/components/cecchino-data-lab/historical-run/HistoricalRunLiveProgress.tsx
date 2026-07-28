import type { HistoricalRunDashboardOverview } from '../../../lib/cecchinoLabApi'

type Props = { overview: HistoricalRunDashboardOverview }

export function HistoricalRunLiveProgress({ overview }: Props) {
  const p = overview.progress
  const pct = Number(p.progress_pct ?? 0)
  const provisional = overview.is_provisional

  return (
    <section
      className="rounded-xl border p-4"
      style={{
        borderColor: provisional ? 'rgba(46,230,255,0.35)' : 'var(--lab-border)',
        background: provisional
          ? 'linear-gradient(160deg, rgba(46,230,255,0.08), transparent)'
          : 'var(--lab-surface)',
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">
          {provisional ? 'Progresso live' : 'Stato scansione'}
        </h3>
        <span
          className="rounded-full px-3 py-1 text-xs font-medium"
          style={{
            background: provisional ? 'rgba(46,230,255,0.15)' : 'rgba(61,214,140,0.15)',
            color: provisional ? 'var(--lab-cyan)' : 'var(--lab-ok)',
          }}
        >
          {provisional
            ? 'Dati provvisori — la scansione è ancora in corso'
            : 'Scansione completata — risultati congelati'}
        </span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full" style={{ background: 'rgba(0,0,0,0.35)' }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(100, Math.max(0, pct))}%`,
            background: 'linear-gradient(90deg, #1a8a9e, var(--lab-cyan))',
          }}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4 lg:grid-cols-6">
        <Stat label="Processate" value={`${p.matches_processed}/${p.matches_total}`} />
        <Stat label="Eleggibili" value={String(p.matches_eligible_core ?? '—')} />
        <Stat label="Escluse" value={String(p.matches_excluded ?? '—')} />
        <Stat label="Errori" value={String(p.matches_error ?? '—')} />
        <Stat label="Campionato" value={String(p.current_competition ?? '—')} />
        <Stat label="Data storica" value={String(p.historical_date_reached ?? '—')} />
      </div>
      {p.last_processed_match ? (
        <p className="mt-2 text-xs text-[var(--lab-muted)]">
          Ultima partita: {String(p.last_processed_match)}
          {p.last_processed_kickoff ? ` · ${String(p.last_processed_kickoff)}` : ''}
        </p>
      ) : null}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-[var(--lab-muted)]">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  )
}
