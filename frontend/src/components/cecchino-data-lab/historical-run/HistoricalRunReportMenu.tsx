import { useState } from 'react'
import { toast } from 'sonner'
import {
  HISTORICAL_RUN_REPORT_MENU,
  downloadHistoricalScanReport,
  type HistoricalReportMode,
  type HistoricalReportModule,
} from '../../../lib/cecchinoLabApi'

type Props = {
  runId: number
  competitions?: string[]
  disabled?: boolean
}

export function HistoricalRunReportMenu({ runId, competitions = [], disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [competition, setCompetition] = useState(competitions[0] ?? '')

  async function onDownload(
    mode: HistoricalReportMode,
    module?: HistoricalReportModule,
    needsCompetition?: boolean,
  ) {
    if (needsCompetition && !competition) {
      toast.error('Seleziona un campionato')
      return
    }
    setBusy(true)
    try {
      await downloadHistoricalScanReport(runId, {
        mode,
        module,
        competition: needsCompetition ? competition : undefined,
      })
      toast.success('Download avviato')
      setOpen(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download fallito')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="lab-btn"
        disabled={disabled || busy}
        onClick={() => setOpen((v) => !v)}
      >
        Scarica report
      </button>
      {open ? (
        <div
          className="absolute right-0 z-30 mt-2 w-80 rounded-xl border p-3 shadow-xl"
          style={{
            background: 'var(--lab-bg-elevated)',
            borderColor: 'var(--lab-border)',
          }}
        >
          {competitions.length > 0 ? (
            <label className="mb-2 block text-xs text-[var(--lab-muted)]">
              Campionato (per report dedicato)
              <select
                className="lab-input mt-1 w-full"
                value={competition}
                onChange={(e) => setCompetition(e.target.value)}
              >
                {competitions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <ul className="space-y-1 text-sm">
            {HISTORICAL_RUN_REPORT_MENU.map((item) => (
              <li key={`${item.mode}-${item.module ?? 'x'}`}>
                <button
                  type="button"
                  className="w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
                  disabled={busy}
                  onClick={() =>
                    void onDownload(item.mode, item.module, item.needsCompetition)
                  }
                >
                  {item.label}
                  {item.recommended ? ' ★' : ''}
                  {item.sizeWarning ? (
                    <span className="mt-0.5 block text-[11px] text-amber-200">
                      Archivio tecnico — può essere molto grande.
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
