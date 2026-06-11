import type { CecchinoGoalIntensityAnalysis } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  goalIntensityAnalysis?: CecchinoGoalIntensityAnalysis
}

const INTENSITY_SCALE: Array<{
  key: string
  range: string
  label: string
  note: string
}> = [
  {
    key: 'very_defensive',
    range: '< 0.5 goal attesi',
    label: 'Molto Difensiva',
    note: 'Nessuna soglia Over accesa.',
  },
  {
    key: 'defensive',
    range: '0.5 – <1.5 goal attesi',
    label: 'Difensiva',
    note: 'Si accende solo Over 0.5.',
  },
  {
    key: 'balanced',
    range: '1.5 – <2.5 goal attesi',
    label: 'Equilibrata',
    note: 'Si accendono Over 0.5 e Over 1.5.',
  },
  {
    key: 'offensive',
    range: '2.5 – <3.5 goal attesi',
    label: 'Offensiva',
    note: 'Si accendono Over 0.5, Over 1.5 e Over 2.5.',
  },
  {
    key: 'very_offensive',
    range: '>= 3.5 goal attesi',
    label: 'Molto Offensiva',
    note: 'Si accendono tutte le soglie fino a Over 3.5.',
  },
]

const THRESHOLD_ORDER = ['over_0_5', 'over_1_5', 'over_2_5', 'over_3_5'] as const

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Math.round(v * 100)}%`
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

function thresholdRowStyles(key: string, active: boolean): string {
  if (!active) return 'border-slate-200 bg-slate-50 text-slate-500'
  if (key === 'over_3_5') return 'border-red-200 bg-red-50 text-red-900'
  if (key === 'over_2_5') return 'border-orange-200 bg-orange-50 text-orange-900'
  return 'border-teal-200 bg-teal-50 text-teal-900'
}

function SectionHeader({ badge }: { badge: string }) {
  const subtitle =
    "Misura l'intensità goal partendo dai Goal Attesi Cecchino interni e dalle soglie Over progressive."
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className={todaySectionTitle}>INTENSITÀ GOAL</h3>
        <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
          {badge}
        </span>
      </div>
      <p className={todaySectionSubtitle}>{subtitle}</p>
    </>
  )
}

function TechnicalAccordion({ analysis }: { analysis: CecchinoGoalIntensityAnalysis }) {
  const { debug, warnings } = analysis
  return (
    <details className="rounded-lg border border-slate-200 bg-white text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
        Dettaglio tecnico Intensità Goal v4
      </summary>
      <div className="space-y-3 border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
        <div className="space-y-1">
          <p className="font-medium text-slate-700">Metodo</p>
          <p>
            La versione v4 usa i Goal Attesi Cecchino interni e li traduce in soglie Over progressive.
          </p>
        </div>
        <div className="space-y-1">
          <p className="font-medium text-slate-700">Formula logica</p>
          <p>Goal Attesi Cecchino &lt; 0.5 → nessuna soglia Over accesa → Molto Difensiva</p>
          <p>0.5 &lt;= Goal Attesi &lt; 1.5 → Over 0.5 acceso → Difensiva</p>
          <p>1.5 &lt;= Goal Attesi &lt; 2.5 → Over 0.5 + Over 1.5 accesi → Equilibrata</p>
          <p>2.5 &lt;= Goal Attesi &lt; 3.5 → Over 0.5 + Over 1.5 + Over 2.5 accesi → Offensiva</p>
          <p>Goal Attesi &gt;= 3.5 → tutte le soglie accese → Molto Offensiva</p>
        </div>
        {debug?.source && (
          <p>
            <span className="font-medium text-slate-700">Fonte interna: </span>
            {debug.source}
          </p>
        )}
        {debug?.note && (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
            {debug.note}
          </p>
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
  if (!goalIntensityAnalysis) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <SectionHeader badge="v4 Goal Attesi" />
        <p className="mt-3 text-sm text-slate-500">Dati non disponibili.</p>
      </section>
    )
  }

  const { status, expected_goals_total, thresholds, final_label, final_class_key, plain_summary } =
    goalIntensityAnalysis

  if (status === 'insufficient_data') {
    return (
      <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
        <SectionHeader badge="v4 Goal Attesi" />
        <p className="text-sm font-medium text-slate-600">Dati insufficienti</p>
        <p className="text-sm text-slate-500">
          Il modulo non riesce a recuperare i Goal Attesi Cecchino interni necessari per classificare
          l'intensità goal.
        </p>
        <TechnicalAccordion analysis={goalIntensityAnalysis} />
      </section>
    )
  }

  if (status !== 'available' || expected_goals_total == null || !thresholds) {
    return null
  }

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <SectionHeader badge="v4 Goal Attesi" />

      <div className={`rounded-lg border px-4 py-4 ${finalClassStyles(final_class_key)}`}>
        <p className="text-2xl font-bold">{final_label ?? '—'}</p>
        <p className="mt-1 text-lg font-semibold tabular-nums opacity-95">
          Goal Attesi Cecchino: {fmtNum(expected_goals_total)}
        </p>
        {plain_summary && <p className="mt-2 text-sm opacity-90">{plain_summary}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Soglie Over
        </p>
        <ul className="mt-2 space-y-1.5 text-sm">
          {THRESHOLD_ORDER.map((key) => {
            const row = thresholds[key]
            if (!row) return null
            const active = Boolean(row.active)
            return (
              <li
                key={key}
                className={`flex items-center justify-between rounded-md border px-3 py-2 ${thresholdRowStyles(key, active)}`}
              >
                <span className="font-medium">{row.label ?? key}</span>
                <span className="flex items-center gap-3 tabular-nums text-xs">
                  <span className="font-semibold uppercase">{active ? 'Acceso' : 'Spento'}</span>
                  {row.probability != null && <span>{fmtPct(row.probability)}</span>}
                </span>
              </li>
            )
          })}
        </ul>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Scala Intensità Goal
        </p>
        <ul className="mt-2 space-y-1.5 text-sm">
          {INTENSITY_SCALE.map((row) => (
            <li
              key={row.key}
              className={`rounded-md border px-3 py-2 ${scaleRowStyles(
                final_class_key === row.key,
                row.key,
              )}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="tabular-nums text-xs">{row.range}</span>
                <span className="font-medium">{row.label}</span>
              </div>
              <p className="mt-0.5 text-xs opacity-80">{row.note}</p>
            </li>
          ))}
        </ul>
      </div>

      <TechnicalAccordion analysis={goalIntensityAnalysis} />
    </section>
  )
}
