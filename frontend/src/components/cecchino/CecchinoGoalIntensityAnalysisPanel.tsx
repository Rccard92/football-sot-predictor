import type { CecchinoGoalIntensityAnalysis } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  goalIntensityAnalysis?: CecchinoGoalIntensityAnalysis
}

const PERCENTILE_SCALE: Array<{
  key: string
  range: string
  label: string
}> = [
  { key: 'very_defensive', range: '< 20°', label: 'Molto Difensiva' },
  { key: 'defensive', range: '20° – <40°', label: 'Difensiva' },
  { key: 'balanced', range: '40° – 60°', label: 'Equilibrata' },
  { key: 'offensive', range: '> 60° – 80°', label: 'Offensiva' },
  { key: 'very_offensive', range: '> 80°', label: 'Molto Offensiva' },
]

const BASELINE_SOURCE_LABELS: Record<string, string> = {
  league: 'Stesso campionato',
  country: 'Stessa nazione',
  global: 'Globale Cecchino',
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

function fmtPercentile(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(1)}°`
}

function finalClassStyles(classKey?: string | null): string {
  switch (classKey) {
    case 'very_defensive':
      return 'border-indigo-300 bg-indigo-50 text-indigo-950'
    case 'defensive':
      return 'border-sky-200 bg-sky-50 text-sky-950'
    case 'balanced':
      return 'border-slate-300 bg-slate-50 text-slate-800'
    case 'offensive':
      return 'border-orange-200 bg-orange-50 text-orange-950'
    case 'very_offensive':
      return 'border-red-200 bg-red-50 text-red-950'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-800'
  }
}

function scaleRowStyles(active: boolean, classKey: string): string {
  if (!active) return 'border-slate-100 bg-white text-slate-600'
  switch (classKey) {
    case 'very_defensive':
      return 'border-indigo-300 bg-indigo-50 font-semibold text-indigo-900'
    case 'defensive':
      return 'border-sky-200 bg-sky-50 font-semibold text-sky-900'
    case 'balanced':
      return 'border-slate-300 bg-slate-100 font-semibold text-slate-800'
    case 'offensive':
      return 'border-orange-200 bg-orange-50 font-semibold text-orange-900'
    case 'very_offensive':
      return 'border-red-200 bg-red-50 font-semibold text-red-900'
    default:
      return 'border-slate-200 bg-slate-50 font-semibold text-slate-800'
  }
}

function MetricCard({
  label,
  value,
  sub,
  tooltip,
}: {
  label: string
  value: string
  sub?: string
  tooltip?: string
}) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-3 py-2.5"
      title={tooltip}
    >
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p>}
    </div>
  )
}

function TechnicalAccordion({ analysis }: { analysis: CecchinoGoalIntensityAnalysis }) {
  const { debug, sources, warnings, raw } = analysis
  return (
    <details className="rounded-lg border border-slate-200 bg-white text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
        Dettaglio tecnico Intensità Goal v3
      </summary>
      <div className="space-y-3 border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
        <div className="space-y-1">
          <p className="font-medium text-slate-700">Formula OVER Q44</p>
          <p>{debug?.over_formula ?? 'OVER Q44 = (Q39+R39)/2 + (Q42+R42)/2'}</p>
        </div>
        <div className="space-y-1">
          <p className="font-medium text-slate-700">Metodo classificazione</p>
          <p>{debug?.classification_method ?? 'OVER Q44 percentile rank'}</p>
          <p>Soglie percentile: 20 / 40 / 60 / 80</p>
        </div>
        {debug?.note && (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
            {debug.note}
          </p>
        )}
        {raw?.under_q44_deprecated != null && (
          <div>
            <p className="font-medium text-slate-700">UNDER Q44 (deprecato, solo debug)</p>
            <p className="tabular-nums">{fmtNum(raw.under_q44_deprecated)}</p>
          </div>
        )}

        {sources?.over && (
          <div>
            <p className="font-medium text-slate-700">OVER — sorgenti Q39/R39/Q42/R42</p>
            <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 tabular-nums sm:grid-cols-4">
              <dt>Q39</dt>
              <dd>{fmtNum(sources.over.q39, 4)}</dd>
              <dt>R39</dt>
              <dd>{fmtNum(sources.over.r39, 4)}</dd>
              <dt>Q42</dt>
              <dd>{fmtNum(sources.over.q42, 4)}</dd>
              <dt>R42</dt>
              <dd>{fmtNum(sources.over.r42, 4)}</dd>
            </dl>
          </div>
        )}

        {warnings && warnings.length > 0 && (
          <ul className="list-disc space-y-1 pl-4">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}

export function CecchinoGoalIntensityAnalysisPanel({ goalIntensityAnalysis }: Props) {
  const subtitle =
    'Misura la pressione goal (OVER Q44) rispetto allo storico Cecchino. ' +
    'La lettura equilibrio/squilibrio resta nella sezione precedente.'

  if (!goalIntensityAnalysis) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            v3 OVER-only
          </span>
        </div>
        <p className={todaySectionSubtitle}>{subtitle}</p>
        <p className="mt-3 text-sm text-slate-500">Dati non disponibili.</p>
      </section>
    )
  }

  const { status, raw, baseline, over_analysis, final_label, final_class_key, plain_summary } =
    goalIntensityAnalysis

  if (status === 'insufficient_data') {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            v3 OVER-only
          </span>
        </div>
        <p className={todaySectionSubtitle}>{subtitle}</p>
        <p className="mt-3 text-sm font-medium text-slate-600">Dati insufficienti</p>
        <p className="mt-1 text-sm text-slate-500">
          Non sono disponibili tutti i valori interni necessari per calcolare OVER Q44.
        </p>
        <TechnicalAccordion analysis={goalIntensityAnalysis} />
      </section>
    )
  }

  if (status === 'insufficient_baseline') {
    return (
      <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            v3 OVER-only
          </span>
        </div>
        <p className={todaySectionSubtitle}>{subtitle}</p>
        <p className="text-sm font-medium text-amber-800">Baseline insufficiente</p>
        <p className="text-sm text-slate-600">
          Il modulo ha calcolato OVER Q44, ma non ha abbastanza storico per il percentile.
        </p>
        {raw && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetricCard label="Pressione Goal (OVER Q44)" value={fmtNum(raw.over_q44)} />
          </div>
        )}
        <TechnicalAccordion analysis={goalIntensityAnalysis} />
      </section>
    )
  }

  if (status !== 'available' || !over_analysis) {
    return null
  }

  const baselineSourceLabel =
    (baseline?.source && BASELINE_SOURCE_LABELS[baseline.source]) ?? baseline?.source ?? '—'

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            v3 OVER-only
          </span>
        </div>
        <p className={todaySectionSubtitle}>{subtitle}</p>
      </div>

      <div className={`rounded-lg border px-4 py-4 ${finalClassStyles(final_class_key)}`}>
        <p className="text-2xl font-bold">{final_label ?? '—'}</p>
        <p className="mt-1 text-sm tabular-nums opacity-90">
          Percentile OVER: {fmtPercentile(over_analysis.over_percentile)}
        </p>
        {plain_summary && <p className="mt-2 text-sm opacity-90">{plain_summary}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Pressione Goal"
          value={fmtNum(raw?.over_q44)}
          sub="OVER Q44 grezzo"
        />
        <MetricCard
          label="Percentile OVER"
          value={fmtPercentile(over_analysis.over_percentile)}
          sub="rispetto allo storico Cecchino"
        />
        <MetricCard
          label="Indice vs Mediana"
          value={fmtNum(over_analysis.over_index_vs_median)}
          sub="OVER Q44 / mediana storica"
        />
        <MetricCard
          label="Baseline Mediana"
          value={fmtNum(baseline?.median_over_q44)}
          sub={baselineSourceLabel}
        />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Scala percentile OVER
        </p>
        <ul className="mt-2 space-y-1.5 text-sm">
          {PERCENTILE_SCALE.map((row) => (
            <li
              key={row.key}
              className={`flex items-center justify-between rounded-md border px-3 py-1.5 ${scaleRowStyles(
                final_class_key === row.key,
                row.key,
              )}`}
            >
              <span className="tabular-nums text-xs">{row.range}</span>
              <span>{row.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Baseline usata
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm tabular-nums sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500">Fonte</dt>
            <dd className="font-medium">{baselineSourceLabel}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Campione</dt>
            <dd className="font-medium">{baseline?.sample_size ?? '—'} partite</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Mediana</dt>
            <dd className="font-medium">{fmtNum(baseline?.median_over_q44)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">P20</dt>
            <dd className="font-medium">{fmtNum(baseline?.p20_over_q44)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">P40</dt>
            <dd className="font-medium">{fmtNum(baseline?.p40_over_q44)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">P60</dt>
            <dd className="font-medium">{fmtNum(baseline?.p60_over_q44)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">P80</dt>
            <dd className="font-medium">{fmtNum(baseline?.p80_over_q44)}</dd>
          </div>
        </dl>
      </div>

      <TechnicalAccordion analysis={goalIntensityAnalysis} />
    </section>
  )
}
