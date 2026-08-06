import { useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import type {
  KpiPurchasabilitySnapshot,
  KpiSignalActivationRow,
} from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'
import type { KpiHeatmapSelection } from './KpiSignalsHeatmapLab'
import {
  formatKpiProfit,
  formatKpiRoi,
  formatKpiWinRate,
  kpiStatusBadgeClass,
  kpiStatusLabel,
  profitTextClass,
} from './kpiSignalsLabUtils'
import { PurchasabilityBadge } from './PurchasabilityBadge'

export type KpiDrawerState =
  | { type: 'activation'; row: KpiSignalActivationRow }
  | { type: 'heatmap'; cell: KpiHeatmapSelection; activations: KpiSignalActivationRow[] }
  | null

type Props = {
  state: KpiDrawerState
  onClose: () => void
}

export function KpiSignalDetailDrawer({ state, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (state) {
      document.addEventListener('keydown', onKey)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [state, onClose])

  return (
    <AnimatePresence>
      {state && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-[2px]"
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl md:max-w-lg"
            role="dialog"
            aria-modal="true"
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-900">Dettaglio Segnale KPI</h3>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                aria-label="Chiudi"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {state.type === 'heatmap' ? (
                <HeatmapDrawerContent cell={state.cell} activations={state.activations} />
              ) : (
                <ActivationDrawerContent row={state.row} />
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function HeatmapDrawerContent({
  cell,
  activations,
}: {
  cell: KpiHeatmapSelection
  activations: KpiSignalActivationRow[]
}) {
  const b = cell.cell
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Pronostico × Rating</p>
        <h4 className="mt-1 text-lg font-semibold text-slate-900">
          {cell.selectionLabel} · {cell.ratingBucket}
        </h4>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Segnali" value={String(b.activations)} />
        <Stat label="Win Rate" value={formatKpiWinRate(b.win_rate)} />
        <Stat label="Profitto" value={formatKpiProfit(b.profit_units)} />
        <Stat label="ROI" value={formatKpiRoi(b.roi_pct)} />
        <Stat label="W / L" value={`${b.won} / ${b.lost}`} />
        <Stat label="Quota media" value={formatOdds(b.avg_book_odds_all)} />
      </dl>
      {activations.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Partite ({activations.length})
          </p>
          <ul className="space-y-2">
            {activations.slice(0, 12).map((row) => (
              <li key={row.id} className="rounded-lg border border-slate-100 p-2 text-sm">
                <p className="font-medium text-slate-800">
                  {row.home_team_name} vs {row.away_team_name}
                </p>
                <p className="text-xs text-slate-500">
                  {row.scan_date} · {kpiStatusLabel(row.evaluation_status)}
                  {row.result_home_ft != null ? ` · FT ${row.result_home_ft}:${row.result_away_ft}` : ''}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function purchasabilityMessage(snap: KpiPurchasabilitySnapshot | null | undefined): string | null {
  if (!snap || snap.status === 'snapshot_unavailable' || (!snap.snapshot_available && snap.status == null)) {
    return 'Snapshot Acquistabilità non disponibile per questa attivazione.'
  }
  if (snap.status === 'unsupported_market') {
    return 'Mercato non supportato dalla V3.'
  }
  return null
}

function PurchasabilityBlock({
  title,
  snap,
  isV3,
}: {
  title: string
  snap: KpiPurchasabilitySnapshot | null | undefined
  isV3?: boolean
}) {
  const message = purchasabilityMessage(snap)
  return (
    <div className="rounded-xl border border-slate-100 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
        <PurchasabilityBadge snap={snap} versionLabel={isV3 ? 'V3' : 'V3.1'} />
      </div>
      {message ? (
        <p className="text-sm text-slate-500">{message}</p>
      ) : (
        <dl className="space-y-1 text-sm">
          {!isV3 ? (
            <StatRow label="Candidate version" value={snap?.candidate_version ?? '—'} />
          ) : null}
          <StatRow label="Formula version" value={snap?.formula_version ?? '—'} />
          {!isV3 ? (
            <StatRow label="Registry status" value={snap?.registry_status ?? '—'} />
          ) : null}
          <StatRow label="Status" value={snap?.status ?? '—'} />
          <StatRow
            label="Score"
            value={snap?.score != null ? String(snap.score) : '—'}
          />
          <StatRow label="Classe" value={snap?.class_label ?? snap?.class_key ?? '—'} />
          <StatRow label="Qualità" value={snap?.calculation_quality ?? '—'} />
          {!isV3 ? (
            <>
              <StatRow
                label="Definitiva/Provvisoria"
                value={
                  snap?.status === 'score_provisional'
                    ? 'Provvisoria'
                    : snap?.status === 'score'
                      ? 'Definitiva'
                      : '—'
                }
              />
              <StatRow
                label="Historical evidence"
                value={snap?.historical_evidence_quality ?? '—'}
              />
            </>
          ) : null}
          <StatRow label="Timestamp" value={snap?.source_snapshot_at ?? '—'} />
          <StatRow
            label="Motivo sintetico"
            value={(snap?.reason_codes || []).join(', ') || '—'}
          />
        </dl>
      )}
    </div>
  )
}

function ActivationDrawerContent({ row }: { row: KpiSignalActivationRow }) {
  const [rawOpen, setRawOpen] = useState(false)
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Partita</p>
        <h4 className="mt-1 text-lg font-semibold text-slate-900">
          {row.home_team_name} vs {row.away_team_name}
        </h4>
        <p className="text-sm text-slate-500">
          {row.league_name ?? '—'} · {row.scan_date}
        </p>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Dati KPI</p>
        <dl className="space-y-2 text-sm">
          <StatRow label="Mercato" value={row.selection_label} />
          <StatRow label="Rating" value={String(row.rating_score)} />
          <StatRow label="Fascia Rating" value={row.rating_bucket} />
          <StatRow label="Quota Book" value={formatOdds(row.quota_book)} />
          <StatRow label="Quota Cecchino" value={formatOdds(row.quota_cecchino)} />
          <StatRow label="Edge %" value={row.edge_pct != null ? String(row.edge_pct) : '—'} />
          <StatRow label="Score KPI" value={row.score_pct != null ? String(row.score_pct) : '—'} />
          <StatRow
            label="Risultato PT"
            value={`${row.result_home_ht ?? '—'}:${row.result_away_ht ?? '—'}`}
          />
          <StatRow
            label="Risultato FT"
            value={`${row.result_home_ft ?? '—'}:${row.result_away_ft ?? '—'}`}
          />
          <StatRow
            label="Esito"
            value={
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${kpiStatusBadgeClass(row.evaluation_status)}`}
              >
                {kpiStatusLabel(row.evaluation_status)}
              </span>
            }
          />
          <StatRow
            label="Profitto (stake 1)"
            value={
              <span className={profitTextClass(row.profit_units)}>{formatKpiProfit(row.profit_units)}</span>
            }
          />
          {row.evaluation_reason ? <StatRow label="Motivo" value={row.evaluation_reason} /> : null}
        </dl>
      </div>

      <PurchasabilityBlock title="Acquistabilità V3" snap={row.purchasability_v3} isV3 />
      <PurchasabilityBlock title="Acquistabilità V3.1" snap={row.purchasability_v31} />

      <button
        type="button"
        onClick={() => setRawOpen((v) => !v)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:bg-slate-50"
      >
        Dati tecnici {rawOpen ? '▲' : '▼'}
      </button>
      {rawOpen ? (
        <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-[10px] text-slate-600">
          {JSON.stringify(
            {
              id: row.id,
              selection_key: row.selection_key,
              normalized_market: row.normalized_market,
              rating_label: row.rating_label,
              stake_units: row.stake_units,
            },
            null,
            2,
          )}
        </pre>
      ) : null}
      <Link
        to={`/cecchino-today?fixture=${row.today_fixture_id}&date=${row.scan_date}`}
        className="inline-flex rounded-lg bg-cyan-700 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-800"
      >
        Apri Cecchino Today
      </Link>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <dt className="text-[10px] font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-50 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{value}</dd>
    </div>
  )
}
