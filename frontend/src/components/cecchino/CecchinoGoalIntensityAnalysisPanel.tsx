import type { CecchinoGoalIntensityAnalysis } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  goalIntensityAnalysis?: CecchinoGoalIntensityAnalysis
}

const RATIO_SCALE: Array<{
  key: string
  range: string
  label: string
}> = [
  { key: 'very_defensive', range: '< 0.70', label: 'Molto Difensiva' },
  { key: 'defensive', range: '0.70 – <0.90', label: 'Difensiva' },
  { key: 'balanced', range: '0.90 – 1.05', label: 'Equilibrata' },
  { key: 'offensive', range: '> 1.05 – 1.20', label: 'Offensiva' },
  { key: 'very_offensive', range: '> 1.20', label: 'Molto Offensiva' },
]

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

function fmtDelta(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
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
  tooltip,
}: {
  label: string
  value: string
  tooltip: string
}) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-3 py-2.5"
      title={tooltip}
    >
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  )
}

export function CecchinoGoalIntensityAnalysisPanel({ goalIntensityAnalysis }: Props) {
  if (!goalIntensityAnalysis || goalIntensityAnalysis.status !== 'available') {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
        <p className={todaySectionSubtitle}>
          Misura la direzione goal della partita confrontando pressione offensiva e resistenza difensiva del modello Cecchino.
        </p>
        <p className="mt-3 text-sm font-medium text-slate-600">Dati insufficienti</p>
        <p className="mt-1 text-sm text-slate-500">
          Non sono disponibili tutti i valori interni necessari per calcolare OVER Q44 e UNDER Q44.
        </p>
        {goalIntensityAnalysis?.warnings && goalIntensityAnalysis.warnings.length > 0 && (
          <details className="mt-4 rounded-lg border border-slate-200 bg-white text-sm">
            <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
              Dettaglio tecnico Intensità Goal
            </summary>
            <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
              <ul className="list-disc space-y-1 pl-4">
                {goalIntensityAnalysis.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          </details>
        )}
      </section>
    )
  }

  const {
    offensive_index,
    defensive_index,
    intensity_ratio,
    intensity_delta,
    final_label,
    final_class_key,
    ratio_label,
    delta_label,
    plain_summary,
    components,
    debug,
    sources,
    warnings,
  } = goalIntensityAnalysis

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
        <p className={todaySectionSubtitle}>
          Misura la direzione goal della partita confrontando pressione offensiva e resistenza difensiva del modello Cecchino.
        </p>
      </div>

      <div className={`rounded-lg border px-4 py-4 ${finalClassStyles(final_class_key)}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-current/20 bg-white/60 px-2 py-0.5 text-xs font-medium">
            Rapporto Intensità
          </span>
        </div>
        <p className="mt-2 text-2xl font-bold">{final_label ?? '—'}</p>
        {plain_summary && <p className="mt-2 text-sm opacity-90">{plain_summary}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Indice Offensivo"
          value={fmtNum(offensive_index ?? components?.over_q44)}
          tooltip="Misura la pressione offensiva aggregata (OVER Q44)."
        />
        <MetricCard
          label="Indice Difensivo"
          value={fmtNum(defensive_index ?? components?.under_q44)}
          tooltip="Misura la resistenza difensiva aggregata (UNDER Q44)."
        />
        <MetricCard
          label="Rapporto Intensità"
          value={fmtNum(intensity_ratio ?? components?.ratio)}
          tooltip="È l'indicatore principale: confronta pressione offensiva e resistenza difensiva."
        />
        <MetricCard
          label="Delta Intensità"
          value={fmtDelta(intensity_delta ?? components?.delta)}
          tooltip="È un indicatore di conferma: misura lo scarto tra indice offensivo e difensivo."
        />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Scala Rapporto Intensità
        </p>
        <ul className="mt-2 space-y-1.5 text-sm">
          {RATIO_SCALE.map((row) => (
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
          Conferma Delta
        </p>
        <p className="mt-1 font-medium text-slate-800">
          {delta_label ?? '—'} ({fmtDelta(intensity_delta ?? components?.delta)})
        </p>
        <p className="mt-2 text-xs text-slate-600">
          Il delta non decide da solo la classificazione, ma conferma o indebolisce la lettura del rapporto.
        </p>
      </div>

      <details className="rounded-lg border border-slate-200 bg-white text-sm">
        <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
          Dettaglio tecnico Intensità Goal
        </summary>
        <div className="space-y-3 border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
          <div className="space-y-1">
            <p className="font-medium text-slate-700">Formule</p>
            <p>Indice Offensivo: OVER!Q44 = (Q39+R39)/2 + (Q42+R42)/2</p>
            <p>Indice Difensivo: UNDER!Q44 = (Q39+R39)/2 + (Q42+R42)/2</p>
            <p>Rapporto Intensità: {debug?.ratio_formula ?? 'OVER!Q44 / UNDER!Q44'}</p>
            <p>Delta Intensità: {debug?.delta_formula ?? 'OVER!Q44 - UNDER!Q44'}</p>
          </div>

          {sources?.over && (
            <div>
              <p className="font-medium text-slate-700">OVER — sorgenti</p>
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

          {sources?.under && (
            <div>
              <p className="font-medium text-slate-700">UNDER — sorgenti</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 tabular-nums sm:grid-cols-4">
                <dt>Q39</dt>
                <dd>{fmtNum(sources.under.q39, 4)}</dd>
                <dt>R39</dt>
                <dd>{fmtNum(sources.under.r39, 4)}</dd>
                <dt>Q42</dt>
                <dd>{fmtNum(sources.under.q42, 4)}</dd>
                <dt>R42</dt>
                <dd>{fmtNum(sources.under.r42, 4)}</dd>
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

          {ratio_label && (
            <p className="text-slate-500">
              Classificazione rapporto: {ratio_label} · Delta: {delta_label}
            </p>
          )}
        </div>
      </details>
    </section>
  )
}
