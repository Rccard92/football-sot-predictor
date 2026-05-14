import type { ModelRelevantField } from '../../lib/api'
import { labelDbStatus, labelModelV04, labelSampleType } from './directCatalogLabels'
import { labelModelRelevantClassification } from './modelRelevantLabels'

type Props = {
  field: ModelRelevantField
  showCheckbox: boolean
  selected: boolean
  onToggle?: (key: string) => void
}

export function ModelRelevantFieldRow({ field, showCheckbox, selected, onToggle }: Props) {
  const markets = (field.recommended_markets || '').split(';').filter(Boolean).join(' · ')

  return (
    <div className="flex gap-3 rounded-xl border border-slate-200/90 bg-slate-50/40 p-3 sm:p-4">
      {showCheckbox ? (
        <div className="pt-0.5">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggle?.(field.key)}
            className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
            aria-label={`Seleziona ${field.name_it}`}
          />
        </div>
      ) : (
        <div className="w-4 shrink-0" aria-hidden />
      )}
      <div className="min-w-0 flex-1 space-y-2 text-sm">
        <div>
          <h4 className="font-semibold text-slate-900">{field.name_it}</h4>
          <p className="font-mono text-xs text-slate-500">{field.json_path}</p>
        </div>
        <dl className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
          <div>
            <dt className="font-medium text-slate-500">Endpoint</dt>
            <dd className="font-mono">{field.endpoint}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Stato v0.4</dt>
            <dd>{labelModelV04(field.model_v04_status)}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Categoria statistica</dt>
            <dd>{labelModelRelevantClassification(field.classification)}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Priorità</dt>
            <dd>{field.priority ?? '—'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="font-medium text-slate-500">Mercati utili</dt>
            <dd>{markets || '—'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="font-medium text-slate-500">Descrizione</dt>
            <dd className="text-slate-700">{field.reason ?? '—'}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">DB</dt>
            <dd>{labelDbStatus(field.db_status ?? 'unknown')}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Tipo esempio</dt>
            <dd>{labelSampleType(field.sample_type)}</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
