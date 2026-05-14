import { useId } from 'react'
import type { ModelRelevantField } from '../../lib/api'
import { ModelRelevantFieldRow } from './ModelRelevantFieldRow'

type Props = {
  title: string
  fields: ModelRelevantField[]
  open: boolean
  onToggle: () => void
}

export function ModelRelevantTechnicalSection({ title, fields, open, onToggle }: Props) {
  const panelId = useId()
  const btnId = useId()

  return (
    <section className="overflow-hidden rounded-2xl border border-amber-200/90 bg-amber-50/30 shadow-sm">
      <button
        type="button"
        id={btnId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-amber-50/80 sm:flex-row sm:items-center sm:justify-between sm:px-5 sm:py-4"
      >
        <h3 className="text-base font-semibold text-amber-950">{title}</h3>
        <span className="flex flex-wrap items-center gap-2 rounded-lg bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900">
          <span>{fields.length} campi</span>
          <span className="text-amber-800">· non selezionabili</span>
          <span>{open ? '▼' : '▶'}</span>
        </span>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="space-y-3 border-t border-amber-200/60 px-4 py-4 sm:px-5">
          <p className="text-xs text-amber-900">
            Queste sorgenti servono a costruire variabili derivate o join tecnici; non sono candidati diretti da
            selezionare come feature statistiche.
          </p>
          {fields.length === 0 ? (
            <p className="text-sm text-slate-600">Nessun campo con i filtri attuali.</p>
          ) : (
            fields.map((p) => <ModelRelevantFieldRow key={p.key} field={p} showCheckbox={false} selected={false} />)
          )}
        </div>
      ) : null}
    </section>
  )
}
