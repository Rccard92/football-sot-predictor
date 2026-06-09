import { useEffect, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import type { SignalActivationRow } from '../../lib/cecchinoSignalsApi'
import type { HeatmapCellSelection } from './SignalsHeatmapLab'
import {
  formatOdds,
  formatSignalLabel,
  formatSuccessRate,
  formatTakenProfit,
  formatTargetLabel,
  statusBadgeClass,
  statusLabel,
} from './signalsLabUtils'

export type DrawerState =
  | { type: 'heatmap'; cell: HeatmapCellSelection; activations: SignalActivationRow[] }
  | { type: 'activation'; row: SignalActivationRow }
  | null

type Props = {
  state: DrawerState
  onClose: () => void
}

export function SignalsDetailDrawer({ state, onClose }: Props) {
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
              <h3 className="text-sm font-semibold text-slate-900">Dettaglio</h3>
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
  cell: HeatmapCellSelection
  activations: SignalActivationRow[]
}) {
  const b = cell.bucket
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Segnale × Colonna</p>
        <h4 className="mt-1 text-lg font-semibold text-slate-900">
          {cell.signalLabel} · {cell.sourceColumn.replace('EXCEL_', 'Excel ')}
        </h4>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Attivazioni" value={String(b.activations)} />
        <Stat label="Win Rate" value={formatSuccessRate(b.success_rate)} />
        <Stat label="Quota prese" value={formatOdds(b.avg_won_book_odds)} />
        <Stat label="Quota void" value={formatOdds(b.quota_void)} />
        <Stat label="Rendimento" value={formatTakenProfit(b.taken_profit_indicator)} />
        <Stat label="W / L" value={`${b.won} / ${b.lost}`} />
      </dl>
      {activations.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Ultime partite ({activations.length})
          </p>
          <ul className="space-y-2">
            {activations.slice(0, 12).map((row) => (
              <li key={row.id} className="rounded-lg border border-slate-100 p-2 text-sm">
                <p className="font-medium text-slate-800">{row.match}</p>
                <p className="text-xs text-slate-500">
                  {row.scan_date} · {statusLabel(row.evaluation_status)}
                  {row.ft_score ? ` · FT ${row.ft_score}` : ''}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ActivationDrawerContent({ row }: { row: SignalActivationRow }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Partita</p>
        <h4 className="mt-1 text-lg font-semibold text-slate-900">{row.match}</h4>
        <p className="text-sm text-slate-500">{row.league_name ?? '—'} · {row.scan_date}</p>
      </div>
      <dl className="space-y-2 text-sm">
        <StatRow label="Segnale" value={formatSignalLabel(row.signal_group, row.signal_label)} />
        <StatRow label="Colonna" value={row.source_column.replace('EXCEL_', 'Excel ')} />
        <StatRow label="Target" value={formatTargetLabel(row)} />
        <StatRow label="Modello" value={row.model_label ?? row.model_key ?? '—'} />
        <StatRow
          label="Esito"
          value={
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(row.evaluation_status)}`}>
              {statusLabel(row.evaluation_status)}
            </span>
          }
        />
        <StatRow label="Quota book" value={formatOdds(row.quota_book)} />
        <StatRow
          label="Quota presa"
          value={row.counts_in_avg_won_odds ? 'Sì — entra in media prese' : 'No'}
        />
        <StatRow label="Risultato FT" value={row.ft_score ?? '—'} />
        {row.evaluation_reason && (
          <StatRow label="Motivo" value={row.evaluation_reason} />
        )}
      </dl>
      <Link
        to={`/cecchino-today?fixture=${row.today_fixture_id}&date=${row.scan_date}`}
        className="inline-flex rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Apri analisi Cecchino
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
