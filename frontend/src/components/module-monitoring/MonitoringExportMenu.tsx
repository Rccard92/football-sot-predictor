import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  downloadModuleAnalysisPack,
  downloadModuleSummaryJson,
  type MonitoringModuleKeyApi,
} from '../../lib/cecchinoModuleMonitoringApi'
import { MOTION_FAST } from './moduleMonitoringUi'

type Props = {
  moduleKey: MonitoringModuleKeyApi
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  marketKey?: string
  includeRows?: boolean
}

export function MonitoringExportMenu({
  moduleKey,
  dateFrom,
  dateTo,
  competitionId,
  marketKey,
  includeRows = true,
}: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const filters = {
    date_from: dateFrom,
    date_to: dateTo,
    competition_id: competitionId ?? undefined,
    market_key: marketKey || undefined,
    include_rows: includeRows,
  }

  async function runPack() {
    setBusy(true)
    toast.message('Preparazione pacchetto…')
    try {
      await downloadModuleAnalysisPack(moduleKey, filters)
      toast.success('Download pronto')
      setOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export fallito')
    } finally {
      setBusy(false)
    }
  }

  async function runSummary() {
    setBusy(true)
    toast.message('Preparazione riepilogo…')
    try {
      await downloadModuleSummaryJson(moduleKey, filters)
      toast.success('Download pronto')
      setOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export fallito')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Scarica analisi"
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
      >
        Scarica analisi
      </button>
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={MOTION_FAST}
            className="absolute right-0 z-30 mt-2 w-72 rounded-2xl border border-slate-200/80 bg-white p-3 shadow-lg"
          >
            <p className="text-xs text-slate-500">
              Periodo {dateFrom} → {dateTo}
              {competitionId != null ? ` · competition ${competitionId}` : ''}
            </p>
            <ul className="mt-3 space-y-1.5">
              <li>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void runPack()}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  Scarica pacchetto per ChatGPT (.zip)
                </button>
              </li>
              <li>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void runSummary()}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  Scarica riepilogo JSON
                </button>
              </li>
            </ul>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
