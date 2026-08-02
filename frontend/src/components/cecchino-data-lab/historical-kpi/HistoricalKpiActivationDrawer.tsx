import type { HistoricalKpiActivationRow } from '../../../lib/cecchinoLabApi'
import { formatOdds, formatProfit, roiColorClass } from './historicalKpiUtils'

type Props = {
  row: HistoricalKpiActivationRow | null
  onClose: () => void
}

function evaluationLabel(status: string | null): string {
  switch (status) {
    case 'won':
      return 'Vinto'
    case 'lost':
      return 'Perso'
    case 'settled':
      return 'Regolato'
    case 'pending':
      return 'In attesa'
    case 'void':
      return 'Void'
    default:
      return status ?? '—'
  }
}

function DetailRow({
  label,
  value,
  valueClassName,
}: {
  label: string
  value: string
  valueClassName?: string
}) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-[var(--lab-muted)]">{label}</dt>
      <dd className={`text-right font-medium ${valueClassName ?? ''}`}>{value}</dd>
    </div>
  )
}

export function HistoricalKpiActivationDrawer({ row, onClose }: Props) {
  if (row == null) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/45" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-lg flex-col overflow-y-auto border-l shadow-2xl"
        style={{
          background: 'var(--lab-bg-elevated)',
          borderColor: 'var(--lab-border)',
          color: 'var(--lab-text)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="sticky top-0 z-10 flex items-center justify-between border-b px-5 py-4"
          style={{ background: 'var(--lab-surface)', borderColor: 'var(--lab-border)' }}
        >
          <div>
            <div className="text-xs uppercase tracking-wider text-[var(--lab-muted)]">
              Dettaglio attivazione KPI
            </div>
            <div className="text-lg font-semibold">
              {row.home_team ?? '—'} — {row.away_team ?? '—'}
            </div>
          </div>
          <button type="button" className="lab-btn-ghost" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="space-y-5 p-5">
          <section>
            <h3 className="mb-3 text-sm font-semibold text-[var(--lab-cyan)]">Partita</h3>
            <dl className="space-y-2">
              <DetailRow label="Kickoff" value={row.kickoff_at?.replace('T', ' ') ?? '—'} />
              <DetailRow label="Giornata" value={row.matchday_label ?? '—'} />
              <DetailRow label="Campionato" value={row.competition_name ?? '—'} />
              <DetailRow label="Match ID lab" value={String(row.lab_match_id)} />
              <DetailRow label="Snapshot ID" value={String(row.source_snapshot_id)} />
            </dl>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-semibold text-[var(--lab-cyan)]">Segnale</h3>
            <dl className="space-y-2">
              <DetailRow label="Mercato" value={row.market_label || row.market_key} />
              <DetailRow label="Chiave mercato" value={row.market_key} />
              <DetailRow label="Rating" value={row.rating != null ? String(row.rating) : '—'} />
              <DetailRow label="Fascia rating" value={row.rating_bucket ?? '—'} />
              <DetailRow
                label="Tipo quota"
                value={row.quote_type === 'real' ? 'Reale Bet365' : 'Derivata / sintetica'}
              />
              <DetailRow label="Quota book" value={formatOdds(row.quota_book)} />
            </dl>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-semibold text-[var(--lab-cyan)]">Performance</h3>
            <dl className="space-y-2">
              <DetailRow label="Valutazione" value={evaluationLabel(row.evaluation_status)} />
              <DetailRow
                label="Esito binario"
                value={row.won == null ? '—' : row.won ? 'Vinto' : 'Perso'}
              />
              <DetailRow
                label="Profitto (1u)"
                value={formatProfit(row.profit_units)}
                valueClassName={roiColorClass(row.profit_units)}
              />
              {row.result_reason ? (
                <DetailRow label="Motivo esito" value={row.result_reason} />
              ) : null}
            </dl>
          </section>
        </div>
      </aside>
    </div>
  )
}
