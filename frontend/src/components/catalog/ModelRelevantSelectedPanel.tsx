import type { ModelRelevantField } from '../../lib/api'

const LS_KEY = 'apiFootballModelRelevantSelected'

export function loadModelRelevantSelected(): Set<string> {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return new Set()
    const arr = JSON.parse(raw) as unknown
    if (!Array.isArray(arr)) return new Set()
    return new Set(arr.filter((x): x is string => typeof x === 'string'))
  } catch {
    return new Set()
  }
}

export function persistModelRelevantSelected(ids: Set<string>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify([...ids]))
  } catch {
    /* ignore */
  }
}

type Props = {
  selectedIds: Set<string>
  fieldsByKey: Map<string, ModelRelevantField>
  onClear: () => void
}

export function ModelRelevantSelectedPanel({ selectedIds, fieldsByKey, onClear }: Props) {
  const rows = [...selectedIds].map((key) => {
    const f = fieldsByKey.get(key)
    return {
      key,
      name_it: f?.name_it ?? key,
      json_path: f?.json_path ?? '—',
      endpoint: f?.endpoint ?? '—',
      area: f?.area ?? '—',
    }
  })

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
      <h2 className="text-sm font-semibold text-slate-900">Campi selezionati (catalogo modello)</h2>
      <p className="mt-1 text-xs text-slate-500">
        Salvati nel browser (<span className="font-mono">{LS_KEY}</span>). Solo variabili selezionabili del catalogo
        model-relevant.
      </p>
      <p className="mt-2 text-sm font-medium text-slate-800">{selectedIds.size} selezionat{selectedIds.size === 1 ? 'o' : 'i'}</p>
      {rows.length > 0 ? (
        <ul className="mt-3 max-h-52 space-y-2 overflow-y-auto text-sm">
          {rows.map((r) => (
            <li key={r.key} className="rounded-lg border border-slate-100 bg-slate-50/80 px-2 py-2">
              <div className="font-medium text-slate-900">{r.name_it}</div>
              <div className="font-mono text-[11px] text-slate-600">{r.json_path}</div>
              <div className="text-[11px] text-slate-500">
                {r.area} · <span className="font-mono">{r.endpoint}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-500">Nessun campo selezionato.</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onClear}
          disabled={selectedIds.size === 0}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm disabled:opacity-50"
        >
          Svuota selezione
        </button>
        <button
          type="button"
          disabled
          title="Funzione pianificata: genererà variabili derivate da questi campi, senza modificare il modello in questa versione."
          className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white opacity-40"
        >
          Crea variabili derivate da questi campi
        </button>
      </div>
    </div>
  )
}
