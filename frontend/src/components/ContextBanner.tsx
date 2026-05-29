import type { ReactNode } from 'react'
import { useCompetition } from '../contexts/CompetitionContext'
import { useModelSelection } from '../contexts/ModelSelectionContext'
import { labelForModelVersion } from '../lib/modelVersions'

function competitionLabel(c: { name: string; season: number; country?: string | null }) {
  return `${c.name} · ${c.country ?? '?'} · ${c.season}`
}

type ContextBannerProps = {
  showModelSelector?: boolean
  extra?: ReactNode
}

export function ContextBanner({ showModelSelector = true, extra }: ContextBannerProps) {
  const { selectedCompetition } = useCompetition()
  const { selectedModelVersion, setSelectedModelVersion, uiModelOptions } = useModelSelection()

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Campionato attivo
          </p>
          <p className="mt-0.5 text-sm font-medium text-slate-900">
            {selectedCompetition ? competitionLabel(selectedCompetition) : 'Nessun campionato selezionato'}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Modello selezionato
          </p>
          {showModelSelector ? (
            <select
              value={selectedModelVersion}
              onChange={(e) => setSelectedModelVersion(e.target.value as typeof selectedModelVersion)}
              className="mt-1 w-full max-w-xs rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 shadow-sm"
            >
              {uiModelOptions.map((mv) => (
                <option key={mv} value={mv}>
                  {labelForModelVersion(mv)}
                </option>
              ))}
            </select>
          ) : (
            <p className="mt-0.5 text-sm font-medium text-slate-900">
              {labelForModelVersion(selectedModelVersion)}
            </p>
          )}
        </div>
      </div>
      {extra ? <div className="space-y-1 text-xs text-slate-600">{extra}</div> : null}
    </div>
  )
}
