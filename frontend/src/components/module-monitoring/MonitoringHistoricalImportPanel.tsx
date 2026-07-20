import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  HISTORICAL_BACKFILL_CONFIRM,
  planHistoricalBackfill,
  runHistoricalBackfill,
  type HistoricalBackfillPlan,
  type MonitoringModuleKeyApi,
} from '../../lib/cecchinoModuleMonitoringApi'
import { MONITORING_MODULES } from './moduleMonitoringRegistry'
import { CARD_BASE, MOTION_FAST } from './moduleMonitoringUi'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

const DEFAULT_FROM = '2026-06-19'

export function MonitoringHistoricalImportPanel({
  dateFrom,
  dateTo,
  competitionId,
}: Props) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(dateFrom < DEFAULT_FROM ? dateFrom : DEFAULT_FROM)
  const [to, setTo] = useState(dateTo)
  const [comp, setComp] = useState(competitionId)
  const [modules, setModules] = useState<Record<string, boolean>>(
    Object.fromEntries(MONITORING_MODULES.map((m) => [m.key, true])),
  )
  const [includeDiag, setIncludeDiag] = useState(true)
  const [plan, setPlan] = useState<HistoricalBackfillPlan | null>(null)
  const [busy, setBusy] = useState<'plan' | 'run' | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const selected = Object.entries(modules)
    .filter(([, v]) => v)
    .map(([k]) => k as MonitoringModuleKeyApi)

  async function analyze() {
    if (!selected.length) {
      toast.error('Seleziona almeno un modulo')
      return
    }
    setBusy('plan')
    try {
      const payload = await planHistoricalBackfill({
        module_keys: selected,
        date_from: from,
        date_to: to,
        competition_id: comp ? Number(comp) : null,
        include_unverified_diagnostic: includeDiag,
      })
      setPlan(payload)
      toast.success('Analisi disponibilità completata')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Analisi fallita')
    } finally {
      setBusy(null)
    }
  }

  async function confirmRun() {
    setBusy('run')
    try {
      const payload = await runHistoricalBackfill({
        module_keys: selected,
        date_from: from,
        date_to: to,
        competition_id: comp ? Number(comp) : null,
        include_unverified_diagnostic: includeDiag,
        evaluate_after: true,
        confirm: HISTORICAL_BACKFILL_CONFIRM,
      })
      setPlan(payload)
      setConfirmOpen(false)
      toast.success('Importazione storica completata')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import fallito')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className={`${CARD_BASE} p-4`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Strumenti amministrazione</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Import storico controllato — non influenza la promozione prospettica.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          {open ? 'Chiudi' : 'Importa storico'}
        </button>
      </div>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={MOTION_FAST}
            className="mt-4 space-y-3 overflow-hidden border-t border-slate-100 pt-4"
          >
            <p className="text-xs text-slate-600">
              Nessun dato originale Cecchino Today viene cancellato. Le coorti storiche non
              sono promotion-eligible. Solo input salvati pre-match; risultati solo in
              evaluation.
            </p>
            <div className="flex flex-wrap gap-3">
              <label className="text-xs font-medium text-slate-600">
                Da
                <input
                  type="date"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                  className="mt-1 block rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                />
              </label>
              <label className="text-xs font-medium text-slate-600">
                A
                <input
                  type="date"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  className="mt-1 block rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                />
              </label>
              <label className="text-xs font-medium text-slate-600">
                Competition
                <input
                  value={comp}
                  onChange={(e) => setComp(e.target.value)}
                  placeholder="opzionale"
                  className="mt-1 block w-28 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-3">
              {MONITORING_MODULES.map((m) => (
                <label key={m.key} className="flex items-center gap-1.5 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={!!modules[m.key]}
                    onChange={(e) =>
                      setModules((prev) => ({ ...prev, [m.key]: e.target.checked }))
                    }
                  />
                  {m.label}
                </label>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={includeDiag}
                onChange={(e) => setIncludeDiag(e.target.checked)}
              />
              Includi dati diagnostici non pienamente verificati
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy != null}
                onClick={() => void analyze()}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
              >
                {busy === 'plan' ? 'Analisi…' : 'Analizza disponibilità'}
              </button>
              <button
                type="button"
                disabled={busy != null || !plan}
                onClick={() => setConfirmOpen(true)}
                className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-900 disabled:opacity-60"
              >
                Conferma importazione
              </button>
            </div>
            {plan ? (
              <pre className="max-h-64 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-700">
                {JSON.stringify(plan, null, 2)}
              </pre>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>

      {confirmOpen ? (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h4 className="text-base font-semibold text-slate-900">Conferma import storico</h4>
            <p className="mt-2 text-sm text-slate-600">
              Verrà eseguito il backfill con token di conferma. Le coorti storiche restano
              non promotion-eligible.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600"
                onClick={() => setConfirmOpen(false)}
              >
                Annulla
              </button>
              <button
                type="button"
                disabled={busy === 'run'}
                className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
                onClick={() => void confirmRun()}
              >
                {busy === 'run' ? 'Import…' : 'Conferma'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
