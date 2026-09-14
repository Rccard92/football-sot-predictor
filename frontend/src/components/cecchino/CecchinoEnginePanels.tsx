export { CecchinoV25Panel } from './CecchinoV25Panel'
export { CecchinoV3Panel } from './CecchinoV3Panel'

export type EngineTab = 'V2' | 'V2.5' | 'V3'

const TABS: { key: EngineTab; label: string; hint: string }[] = [
  { key: 'V2', label: 'V2', hint: 'Cecchino attuale' },
  { key: 'V2.5', label: 'V2.5', hint: 'Moduli corretti' },
  { key: 'V3', label: 'V3', hint: 'Estesa · campionati con statistiche' },
]

export function EngineTabBar({ value, onChange }: { value: EngineTab; onChange: (t: EngineTab) => void }) {
  return (
    <div role="tablist" aria-label="Motore di analisi" className="flex gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
      {TABS.map((t) => {
        const selected = t.key === value
        return (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(t.key)}
            className={`flex-1 rounded-lg px-3 py-2 text-left transition ${
              selected ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-white/60'
            }`}
          >
            <div className={`text-sm font-semibold ${selected ? 'text-slate-900' : 'text-slate-600'}`}>{t.label}</div>
            <div className="text-[11px] text-slate-500">{t.hint}</div>
          </button>
        )
      })}
    </div>
  )
}
