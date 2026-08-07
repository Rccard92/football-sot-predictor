import { useId, useState } from 'react'
import { SignalMinBookOddsPanel } from '../SignalMinBookOddsPanel'
import type { SignalMinBookOddsBacktestSummary } from '../../../lib/cecchinoSignalsApi'

type Props = {
  dateFrom: string
  dateTo: string
  onBacktestComplete?: (summary: SignalMinBookOddsBacktestSummary | null) => void | Promise<void>
}

export function SignalsMinBookOddsAccordion({
  dateFrom,
  dateTo,
  onBacktestComplete,
}: Props) {
  const [open, setOpen] = useState(false)
  const panelId = useId()

  return (
    <section
      className="rounded-lg border border-slate-200 bg-white"
      data-testid="min-book-odds-accordion"
    >
      <h2 className="sr-only">Soglie quota book</h2>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        data-testid="min-book-odds-accordion-toggle"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-[44px] w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500 motion-reduce:transition-none"
      >
        <span>
          <span className="block text-sm font-semibold text-slate-800">Soglie quota book</span>
          <span className="mt-0.5 block text-xs text-slate-500">
            Configura i minimi per mercato
          </span>
        </span>
        <span
          className={`text-slate-500 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>
      <div
        id={panelId}
        hidden={!open}
        className={open ? 'border-t border-slate-100 px-4 pb-4 pt-3' : undefined}
      >
        {open && (
          <SignalMinBookOddsPanel
            dateFrom={dateFrom}
            dateTo={dateTo}
            hideTitle
            embedded
            onBacktestComplete={onBacktestComplete}
          />
        )}
      </div>
    </section>
  )
}
