import type { ApiFootballDirectField } from '../../lib/api'
import { labelApiFound, labelDbStatus, labelModelV04, labelSampleType } from './directCatalogLabels'

type Props = {
  field: ApiFootballDirectField
  selected: boolean
  onToggle: (stableId: string) => void
}

function Badge({ children, tone }: { children: React.ReactNode; tone: 'emerald' | 'slate' | 'amber' | 'violet' }) {
  const tones = {
    emerald: 'bg-emerald-50 text-emerald-900 border-emerald-200',
    slate: 'bg-slate-100 text-slate-800 border-slate-200',
    amber: 'bg-amber-50 text-amber-900 border-amber-200',
    violet: 'bg-violet-50 text-violet-900 border-violet-200',
  }
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function DirectCatalogParameterCard({ field, selected, onToggle }: Props) {
  const autoTag = field.name_it_auto ? (
    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">Traduzione automatica</span>
  ) : null

  return (
    <div className="flex gap-3 rounded-xl border border-slate-200/90 bg-slate-50/40 p-3 sm:p-4">
      <div className="pt-0.5">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(field.stable_id)}
          className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
          aria-label={`Seleziona ${field.name_it}`}
        />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">{field.name_it}</h4>
            <p className="font-mono text-xs text-slate-500">{field.json_path}</p>
            {autoTag ? <div className="mt-1">{autoTag}</div> : null}
          </div>
          {field.tooltip_it ? (
            <span
              className="inline-flex h-6 w-6 shrink-0 cursor-help items-center justify-center rounded-full border border-slate-200 bg-white text-xs font-bold text-slate-600"
              title={field.tooltip_it}
            >
              ?
            </span>
          ) : null}
        </div>
        <p className="text-sm text-slate-600">{field.description_it}</p>
        <p className="text-xs text-slate-500">
          <span className="font-medium text-slate-600">Endpoint:</span>{' '}
          <span className="font-mono">{field.endpoint}</span>
        </p>
        <p className="text-xs text-slate-500">
          <span className="font-medium text-slate-600">Esempio:</span>{' '}
          <span className="font-mono break-all">{String(field.sample_value)}</span> ({labelSampleType(field.sample_type)})
          {field.examples_count > 1 ? ` · occorrenze: ${field.examples_count}` : null}
        </p>
        {field.db_location_hint ? (
          <p className="text-xs text-slate-500">
            <span className="font-medium text-slate-600">DB:</span>{' '}
            <span className="font-mono">{field.db_location_hint}</span>
          </p>
        ) : null}
        {field.note_it ? <p className="text-xs font-medium text-indigo-800">{field.note_it}</p> : null}
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="emerald">{labelApiFound()}</Badge>
          <Badge tone="slate">{labelDbStatus(field.db_status)}</Badge>
          <Badge tone={field.model_v04_status === 'used_v04' ? 'violet' : 'amber'}>{labelModelV04(field.model_v04_status)}</Badge>
          <Badge tone="slate">Tipo: {labelSampleType(field.sample_type)}</Badge>
          {field.appeared_in_raw_json ? <Badge tone="amber">Visto anche in raw_json DB</Badge> : null}
        </div>
      </div>
    </div>
  )
}
