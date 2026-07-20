import type { BalanceAnalysisFiltersState } from './balanceAnalysisFilterTypes'

type Props = {
  value: BalanceAnalysisFiltersState
  onChange: (next: BalanceAnalysisFiltersState) => void
  showPillarClasses?: boolean
}

export function BalanceAnalysisFilters({
  value,
  onChange,
  showPillarClasses = true,
}: Props) {
  function set<K extends keyof BalanceAnalysisFiltersState>(
    key: K,
    v: BalanceAnalysisFiltersState[K],
  ) {
    onChange({ ...value, [key]: v })
  }

  return (
    <div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white/80 p-3">
      <label className="text-xs font-medium text-slate-600">
        Paese
        <input
          value={value.countryName}
          onChange={(e) => set('countryName', e.target.value)}
          placeholder="opzionale"
          className="mt-1 block w-28 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
        />
      </label>
      {showPillarClasses ? (
        <>
          <label className="text-xs font-medium text-slate-600">
            Classe F36
            <input
              value={value.f36Class}
              onChange={(e) => set('f36Class', e.target.value)}
              className="mt-1 block w-36 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Classe Dominanza
            <input
              value={value.dominanceClass}
              onChange={(e) => set('dominanceClass', e.target.value)}
              className="mt-1 block w-36 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Selezione
            <select
              value={value.dominanceSelection}
              onChange={(e) => set('dominanceSelection', e.target.value)}
              className="mt-1 block rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            >
              <option value="">Tutte</option>
              <option value="1">1</option>
              <option value="X">X</option>
              <option value="2">2</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Credibilità X
            <input
              value={value.drawCredibilityClass}
              onChange={(e) => set('drawCredibilityClass', e.target.value)}
              className="mt-1 block w-40 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Gap
            <input
              value={value.gapClass}
              onChange={(e) => set('gapClass', e.target.value)}
              className="mt-1 block w-36 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
        </>
      ) : null}
    </div>
  )
}
