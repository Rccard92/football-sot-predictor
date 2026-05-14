import type { ApiFootballDirectField } from '../../lib/api'

const LS_KEY = 'apiFootballDirectCatalogSelected'

export function loadSelectedDirectFields(): Set<string> {
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

export function persistSelectedDirectFields(ids: Set<string>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify([...ids]))
  } catch {
    /* ignore */
  }
}

type Props = {
  selectedIds: Set<string>
  fieldsByStable: Map<string, ApiFootballDirectField>
  onClear: () => void
}

export function DirectSelectedFieldsPanel({ selectedIds, fieldsByStable, onClear }: Props) {
  const rows = [...selectedIds].map((id) => {
    const f = fieldsByStable.get(id)
    return {
      stable_id: id,
      json_path: f?.json_path ?? id,
      endpoint: f?.endpoint ?? '—',
      name_it: f?.name_it ?? id,
      area_id: f?.area_id ?? '—',
    }
  })

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
      <h2 className="text-sm font-semibold text-slate-900">Campi API selezionati</h2>
      <p className="mt-1 text-xs text-slate-500">
        Salvati nel browser (chiave <span className="font-mono">{LS_KEY}</span>). Solo campi diretti dallo scan API.
      </p>
      <p className="mt-2 text-sm font-medium text-slate-800">{selectedIds.size} selezionat{selectedIds.size === 1 ? 'o' : 'i'}</p>
      {rows.length > 0 ? (
        <ul className="mt-3 max-h-52 space-y-2 overflow-y-auto text-sm">
          {rows.map((r) => (
            <li key={r.stable_id} className="rounded-lg border border-slate-100 bg-slate-50/80 px-2 py-2">
              <div className="font-medium text-slate-900">{r.name_it}</div>
              <div className="font-mono text-[11px] text-slate-600">{r.json_path}</div>
              <div className="text-[11px] text-slate-500">
                {r.area_id} · <span className="font-mono">{r.endpoint}</span>
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
          title="Funzione pianificata: genererà variabili derivate da questi campi API, senza modificare il modello in questa versione."
          className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white opacity-40"
        >
          Crea variabili derivate da questi campi
        </button>
      </div>
    </div>
  )
}
