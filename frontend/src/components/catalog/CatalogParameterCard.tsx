import type { ApiFootballCatalogParameter } from '../../lib/api'
import {
  labelApiStatus,
  labelDbStatus,
  labelDifficulty,
  labelImplementation,
  labelModelV04,
  labelMarket,
} from './statusLabels'

type CatalogParameterCardProps = {
  param: ApiFootballCatalogParameter
  selected: boolean
  onToggleSelect: (key: string) => void
}

function Badge({ children, tone }: { children: React.ReactNode; tone: 'slate' | 'emerald' | 'amber' | 'rose' | 'violet' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-800 border-slate-200',
    emerald: 'bg-emerald-50 text-emerald-900 border-emerald-200',
    amber: 'bg-amber-50 text-amber-900 border-amber-200',
    rose: 'bg-rose-50 text-rose-900 border-rose-200',
    violet: 'bg-violet-50 text-violet-900 border-violet-200',
  }
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

function apiTone(s: string): 'slate' | 'emerald' | 'amber' | 'rose' | 'violet' {
  if (s === 'available') return 'emerald'
  if (s === 'verify') return 'amber'
  if (s === 'not_in_provider' || s === 'external_provider') return 'rose'
  return 'slate'
}

function dbTone(s: string): 'slate' | 'emerald' | 'amber' | 'rose' {
  if (s === 'saved') return 'emerald'
  if (s === 'raw_json_only') return 'amber'
  if (s === 'not_imported') return 'amber'
  if (s === 'not_available') return 'rose'
  return 'slate'
}

function modelTone(s: string): 'slate' | 'emerald' | 'amber' | 'violet' | 'rose' {
  if (s === 'used' || s === 'indirect') return 'emerald'
  if (s === 'implemented_not_used') return 'violet'
  if (s === 'to_implement' || s === 'verify') return 'amber'
  if (s === 'not_available') return 'rose'
  return 'slate'
}

export function CatalogParameterCard({ param, selected, onToggleSelect }: CatalogParameterCardProps) {
  return (
    <div className="flex gap-3 rounded-xl border border-slate-200/90 bg-slate-50/40 p-3 sm:p-4">
      <div className="pt-0.5">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(param.key)}
          className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
          aria-label={`Seleziona ${param.name_it}`}
        />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">{param.name_it}</h4>
            <p className="font-mono text-xs text-slate-500">{param.key}</p>
          </div>
          {param.tooltip_it ? (
            <span
              className="inline-flex h-6 w-6 shrink-0 cursor-help items-center justify-center rounded-full border border-slate-200 bg-white text-xs font-bold text-slate-600"
              title={param.tooltip_it}
            >
              ?
            </span>
          ) : null}
        </div>
        <p className="text-sm text-slate-600">{param.description_it}</p>
        <p className="text-xs text-slate-500">
          <span className="font-medium text-slate-600">Endpoint:</span> <span className="font-mono">{param.endpoint}</span>
        </p>
        <p className="text-xs text-slate-500">
          <span className="font-medium text-slate-600">DB:</span> <span className="font-mono">{param.db_location}</span>
        </p>
        {param.framework_keys.length > 0 ? (
          <p className="text-xs text-slate-500">
            <span className="font-medium text-slate-600">Manifest v0.4:</span>{' '}
            <span className="font-mono">{param.framework_keys.join(', ')}</span>
            {param.in_v04_manifest ? (
              <span className="ml-1 text-emerald-700">(presente)</span>
            ) : (
              <span className="ml-1 text-amber-700">(non mappato)</span>
            )}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={apiTone(param.api_status)}>{labelApiStatus(param.api_status)}</Badge>
          <Badge tone={dbTone(param.db_status)}>{labelDbStatus(param.db_status)}</Badge>
          <Badge tone={modelTone(param.model_v04_status)}>{labelModelV04(param.model_v04_status)}</Badge>
          <Badge tone="slate">{labelImplementation(param.implementation_status)}</Badge>
          <Badge tone="slate">Difficoltà: {labelDifficulty(param.difficulty)}</Badge>
        </div>
        <div className="flex flex-wrap gap-1">
          {param.useful_markets.map((m) => (
            <span key={m} className="rounded bg-white px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200/80">
              {labelMarket(m)}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
