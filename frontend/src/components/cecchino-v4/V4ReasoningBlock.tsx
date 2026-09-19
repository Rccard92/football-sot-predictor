import { useId, useState, type ReactNode } from 'react'

type Props = {
  index: number
  title: string
  sentence?: string | null
  defaultOpen?: boolean
  children?: ReactNode
}

/** Blocco del Ragionamento: numero, titolo, frase in parole a 16 px, poi i dati. */
export function V4ReasoningBlock({ index, title, sentence, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyId = useId()
  return (
    <section
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
      data-testid={`v4-block-${index}`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
      >
        <span className="flex items-center gap-3">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-base font-bold text-white">
            {index}
          </span>
          <span className="text-xl font-semibold text-slate-900">{title}</span>
        </span>
        <span className="text-base text-slate-500" aria-hidden>
          {open ? 'Chiudi' : 'Apri'}
        </span>
      </button>
      {open ? (
        <div id={bodyId} className="space-y-4 border-t border-slate-100 px-4 py-4">
          {sentence ? <p className="text-base leading-relaxed text-slate-800">{sentence}</p> : null}
          {children}
        </div>
      ) : null}
    </section>
  )
}
