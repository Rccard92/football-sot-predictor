import { useState } from 'react'
import { CHECKLIST_LABELS, type Checklist, type ChecklistValue } from '../../lib/analystJournalApi'

const VALUES: ChecklistValue[] = ['favorevole', 'neutro', 'contrario']
const ACTIVE: Record<ChecklistValue, string> = {
  favorevole: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  neutro: 'border-slate-300 bg-slate-100 text-slate-700',
  contrario: 'border-rose-300 bg-rose-50 text-rose-800',
}

/** Scheda pronostico (16 voci del foglio Excel): per ogni voce favorevole / neutro / contrario e una nota.
 *  Sotto le voci per cui il tool ha dati compare il suggerimento: la scelta resta all'analista. */
export function ChecklistEditor({
  items,
  value,
  hints,
  disabled,
  onChange,
}: {
  items: { key: string; label: string }[]
  value: Checklist
  hints?: Record<string, string>
  disabled?: boolean
  onChange: (next: Checklist) => void
}) {
  const [openNotes, setOpenNotes] = useState<Record<string, boolean>>({})
  const set = (key: string, patch: Partial<{ value: ChecklistValue | null; note: string | null }>) => {
    const current = value[key] ?? { value: null, note: null }
    onChange({ ...value, [key]: { ...current, ...patch } })
  }
  const filled = items.filter((i) => value[i.key]?.value).length

  return (
    <div className="space-y-2">
      <p className="text-[13px] text-slate-500">
        {filled}/{items.length} voci valutate · i dati del tool sono un aiuto, non una risposta
      </p>
      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        {items.map((item) => {
          const current = value[item.key]
          const hint = hints?.[item.key]
          return (
            <li key={item.key} className="space-y-1.5 p-2.5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="min-w-0 flex-1 text-sm text-slate-800">{item.label}</p>
                <div className="flex gap-1" role="group" aria-label={item.label}>
                  {VALUES.map((v) => (
                    <button
                      key={v}
                      type="button"
                      disabled={disabled}
                      aria-pressed={current?.value === v}
                      onClick={() => set(item.key, { value: current?.value === v ? null : v })}
                      className={`rounded-md border px-2 py-1 text-[12px] font-medium transition disabled:opacity-60 ${
                        current?.value === v ? ACTIVE[v] : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                      }`}
                    >
                      {CHECKLIST_LABELS[v]}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setOpenNotes((o) => ({ ...o, [item.key]: !o[item.key] }))}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[12px] text-slate-500 hover:bg-slate-50"
                    aria-label={`Nota: ${item.label}`}
                  >
                    {current?.note ? '✎ nota' : '+ nota'}
                  </button>
                </div>
              </div>
              {hint ? <p className="text-[13px] text-indigo-700">Dal tool: {hint}</p> : null}
              {openNotes[item.key] || current?.note ? (
                <input
                  className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-[13px] focus:border-slate-400 focus:outline-none"
                  placeholder="Nota"
                  value={current?.note ?? ''}
                  disabled={disabled}
                  onChange={(e) => set(item.key, { note: e.target.value })}
                />
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
