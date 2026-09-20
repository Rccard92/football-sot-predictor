import { useId, useState, type ReactNode } from 'react'
import { todayCard, todaySectionTitle } from '../cecchino/cecchinoTodayStyles'

type Props = {
  index: number
  title: string
  sentence?: string | null
  defaultOpen?: boolean
  children?: ReactNode
}

/** Blocco del Ragionamento come una sezione di Cecchino Today: titolo, frase a 14 px, poi i dati. */
export function V4ReasoningBlock({ index, title, sentence, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyId = useId()
  return (
    <section className={todayCard} data-testid={`v4-block-${index}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 sm:px-5"
      >
        <span className={todaySectionTitle}>{title}</span>
        <span className="text-xs text-slate-500" aria-hidden>
          {open ? 'Chiudi' : 'Apri'}
        </span>
      </button>
      {open ? (
        <div id={bodyId} className="space-y-3 border-t border-slate-100 px-4 py-4 sm:px-5">
          {sentence ? <p className="text-sm leading-relaxed text-slate-800">{sentence}</p> : null}
          {children}
        </div>
      ) : null}
    </section>
  )
}
