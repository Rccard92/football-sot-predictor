import type { ModelRelevantField } from '../../lib/api'
import { labelDbStatus, labelSampleType } from './directCatalogLabels'
import { CATEGORY_STATISTICA_TOOLTIP, categoryBadgeShort } from './modelRelevantLabels'
import { badgeV04Display } from './modelRelevantV04Badge'

type Props = {
  field: ModelRelevantField
  showCheckbox: boolean
  selected: boolean
  onToggle?: (key: string) => void
}

function Badge({
  children,
  tone,
  className = '',
}: {
  children: React.ReactNode
  tone: 'emerald' | 'slate' | 'amber' | 'violet' | 'sky'
  className?: string
}) {
  const tones = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    slate: 'border-slate-200 bg-slate-100 text-slate-800',
    amber: 'border-amber-200 bg-amber-50 text-amber-950',
    violet: 'border-violet-200 bg-violet-50 text-violet-900',
    sky: 'border-sky-200 bg-sky-50 text-sky-900',
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold leading-tight ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

function v04BadgeTone(field: ModelRelevantField): 'emerald' | 'slate' | 'amber' | 'violet' | 'sky' {
  const t = badgeV04Display(field)
  if (t === 'Usato da v0.4') return 'emerald'
  if (t === 'Fonte tecnica') return 'violet'
  if (t === 'Candidata futura') return 'amber'
  if (t.startsWith('Implementato') || t.startsWith('Da implementare')) return 'sky'
  return 'slate'
}

function categoryBadgeTone(c: string): 'slate' | 'emerald' | 'amber' | 'violet' {
  if (c === 'TENERE_MODELLO_DIRETTO') return 'emerald'
  if (c === 'TENERE_FUTURO_MODELLO') return 'amber'
  if (c === 'SORGENTE_DERIVATA_TECNICA') return 'violet'
  return 'slate'
}

function CategoryBadgeWithTooltip({ classification }: { classification: string }) {
  return (
    <span className="group relative inline-flex shrink-0 items-center gap-0.5">
      <Badge tone={categoryBadgeTone(classification)} className="max-w-[10rem] text-center leading-tight">
        {categoryBadgeShort(classification)}
      </Badge>
      <span
        className="flex h-5 w-5 cursor-help items-center justify-center rounded-full border border-slate-300 bg-white text-[10px] font-bold text-slate-600 shadow-sm"
        tabIndex={0}
        aria-label="Legenda categorie statistiche"
      >
        ?
      </span>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute right-0 top-full z-20 mt-1.5 max-w-[min(22rem,calc(100vw-2rem))] whitespace-pre-line rounded-lg border border-slate-200 bg-white p-3 text-left text-xs font-normal leading-snug text-slate-700 shadow-lg opacity-0 transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        {CATEGORY_STATISTICA_TOOLTIP}
      </span>
    </span>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-slate-100 py-2 last:border-0">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-0.5 break-words text-sm text-slate-800">{children}</div>
    </div>
  )
}

export function ModelRelevantFieldRow({ field, showCheckbox, selected, onToggle }: Props) {
  const canSelect = showCheckbox && field.selectable !== false
  const markets = (field.recommended_markets || '').split(';').filter(Boolean).join(' · ')
  const v04Text = badgeV04Display(field)
  const pathLine = [field.json_path, field.key].filter(Boolean).join(' · ')

  return (
    <div className="rounded-lg border border-slate-200/90 bg-white px-3 py-2.5 shadow-sm sm:px-4 sm:py-3">
      <div className="flex gap-2.5 sm:gap-3">
        <div className="pt-0.5">
          <input
            type="checkbox"
            checked={canSelect && selected}
            disabled={!canSelect}
            onChange={() => canSelect && onToggle?.(field.key)}
            className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={canSelect ? `Seleziona ${field.name_it}` : `${field.name_it} non selezionabile`}
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <h4 className="text-sm font-semibold leading-snug text-slate-900">{field.name_it}</h4>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5 sm:max-w-[48%]">
              <Badge tone={v04BadgeTone(field)}>{v04Text}</Badge>
              <CategoryBadgeWithTooltip classification={field.classification} />
            </div>
          </div>
          <p className="mt-1 font-mono text-[11px] leading-snug text-slate-500 break-all">{pathLine}</p>
          {field.reason ? <p className="mt-1.5 text-sm leading-snug text-slate-700">{field.reason}</p> : null}

          <details className="group mt-2.5 rounded-md border border-slate-200/80 bg-slate-50/50 open:bg-slate-50">
            <summary className="cursor-pointer list-none px-2 py-1.5 text-xs font-medium text-slate-700 marker:hidden [&::-webkit-details-marker]:hidden hover:text-slate-900">
              <span className="inline-flex items-center gap-1.5">
                <span className="text-slate-400 group-open:hidden">▸</span>
                <span className="hidden text-slate-400 group-open:inline">▾</span>
                <span className="group-open:hidden">Apri dettagli tecnici</span>
                <span className="hidden group-open:inline">Chiudi dettagli tecnici</span>
              </span>
            </summary>
            <div className="border-t border-slate-200/80 px-2 pb-2 pt-1">
              {!canSelect ? (
                <p className="mb-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-950">
                  Non selezionabile: fonte tecnica o dato non destinato al modello.
                </p>
              ) : null}
              <div className="divide-y divide-slate-100 rounded-md border border-slate-100 bg-white px-2">
                <DetailRow label="Endpoint">
                  <span className="font-mono text-xs">{field.endpoint}</span>
                </DetailRow>
                <DetailRow label="Mercati utili">{markets || '—'}</DetailRow>
                <DetailRow label="DB">{labelDbStatus(field.db_status ?? 'unknown')}</DetailRow>
                <DetailRow label="Priorità">{field.priority ?? '—'}</DetailRow>
                <DetailRow label="Tipo esempio">{labelSampleType(field.sample_type)}</DetailRow>
                <DetailRow label="Sample value">
                  <span className="font-mono text-xs break-all">{formatSample(field.sample_value)}</span>
                </DetailRow>
                <DetailRow label="JSON path">
                  <span className="font-mono text-xs break-all">{field.json_path}</span>
                </DetailRow>
                <DetailRow label="Key">
                  <span className="font-mono text-xs break-all">{field.key}</span>
                </DetailRow>
                {field.original_json_path && field.original_json_path !== field.json_path ? (
                  <DetailRow label="JSON path originale">
                    <span className="font-mono text-xs break-all">{field.original_json_path}</span>
                  </DetailRow>
                ) : null}
                <DetailRow label="Stato API">N/D (catalogo statico)</DetailRow>
                <DetailRow label="Stato DB (raw)">{field.db_status ?? '—'}</DetailRow>
                {field.db_location_hint ? (
                  <DetailRow label="db_location_hint">
                    <span className="font-mono text-xs break-all">{field.db_location_hint}</span>
                  </DetailRow>
                ) : null}
                <DetailRow label="Stato modello v0.4 (raw)">{field.model_v04_status}</DetailRow>
                <DetailRow label="Classificazione (raw)">{field.classification}</DetailRow>
                {field.occurrences_collapsed != null ? (
                  <DetailRow label="Occorrenze (collapse)">{String(field.occurrences_collapsed)}</DetailRow>
                ) : null}
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>
  )
}

function formatSample(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}
