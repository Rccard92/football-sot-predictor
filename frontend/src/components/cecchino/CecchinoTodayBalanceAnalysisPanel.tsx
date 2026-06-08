import type { CecchinoBalanceAnalysis } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  balanceAnalysis?: CecchinoBalanceAnalysis
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

function severityStyles(severity?: string): string {
  switch (severity) {
    case 'positive':
      return 'border-emerald-200 bg-emerald-50 text-emerald-900'
    case 'warning':
      return 'border-amber-200 bg-amber-50 text-amber-900'
    case 'negative':
      return 'border-red-200 bg-red-50 text-red-900'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-800'
  }
}

function severityIcon(severity?: string): string {
  switch (severity) {
    case 'positive':
      return '✓'
    case 'warning':
      return '⚠'
    case 'negative':
      return '✗'
    default:
      return '•'
  }
}

function Stars({ count }: { count?: number }) {
  const n = count ?? 0
  return (
    <span className="text-amber-500" aria-label={`${n} stelle`}>
      {'★'.repeat(n)}
      {'☆'.repeat(Math.max(0, 5 - n))}
    </span>
  )
}

const OPERATIONAL_RULES: Array<{ id: number; condition: string; label: string }> = [
  { id: 1, condition: 'F36<0.75, dom≤5, X≤3.50', label: 'X molto forte' },
  { id: 2, condition: 'F36<0.75, dom≤5, 3.50<X≤4.20', label: 'X possibile / Under' },
  { id: 3, condition: 'F36<0.75, dom≤5, X>4.20', label: 'Equilibrio apparente' },
  { id: 4, condition: 'F36<0.75, 5<dom≤10, X≤3.50', label: 'X possibile' },
  { id: 5, condition: 'F36<0.75, 5<dom≤10, X>3.50', label: 'Equilibrio con tendenza' },
  { id: 6, condition: 'F36<0.75, dom>10', label: 'Falso equilibrio' },
  { id: 7, condition: '0.75≤F36≤1.50, dom≤5, X≤3.50', label: 'Equilibrata meno pulita' },
  { id: 8, condition: '0.75≤F36≤1.50, 5<dom≤10, X≤3.50', label: 'Zona grigia' },
  { id: 9, condition: '0.75≤F36≤1.50, dom>10', label: 'Tendenza verso 1 o 2' },
  { id: 10, condition: 'F36>1.50, dom≤5, X≤3.50', label: 'Partita anomala' },
  { id: 11, condition: 'F36>1.50, 5<dom≤10', label: 'Squilibrio moderato' },
  { id: 12, condition: 'F36>1.50, dom>10', label: 'Squilibrio confermato' },
]

export function CecchinoTodayBalanceAnalysisPanel({ balanceAnalysis }: Props) {
  if (!balanceAnalysis || balanceAnalysis.status !== 'available') {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio</h3>
        <p className={todaySectionSubtitle}>
          Lettura del bilanciamento della partita basata su quota 1/2 Cecchino, dominanza del
          modello e quota X.
        </p>
        <p className="mt-3 text-sm text-slate-500">
          Analisi non disponibile: quote o probabilità Cecchino 1/X/2 insufficienti.
        </p>
      </section>
    )
  }

  const { f36, dominance, draw, operational, summary, cross_reading, inputs, technical } =
    balanceAnalysis
  const ruleId = technical?.rule_id

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio</h3>
        <p className={todaySectionSubtitle}>
          Lettura del bilanciamento della partita basata su quota 1/2 Cecchino, dominanza del
          modello e quota X.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <article className="rounded-lg border border-sky-200 bg-sky-50/60 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-800">F36</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(f36?.abs)}
          </p>
          <p className="mt-1 font-medium text-slate-800">{f36?.label ?? '—'}</p>
          <p className="mt-1 text-xs text-slate-600">
            Score {f36?.score ?? '—'}/100
          </p>
          {f36?.direction_note && (
            <p className="mt-2 text-xs text-slate-600">{f36.direction_note}</p>
          )}
        </article>

        <article className="rounded-lg border border-indigo-200 bg-indigo-50/60 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-800">
            Dominanza
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(dominance?.value)} p.p.
          </p>
          <p className="mt-1 font-medium text-slate-800">{dominance?.label ?? '—'}</p>
          <p className="mt-1">
            <Stars count={dominance?.stars} />
          </p>
          <p className="mt-2 text-xs tabular-nums text-slate-600">
            1°: {dominance?.best_side ?? '—'} — {fmtNum(dominance?.best_probability, 1)}%
            <br />
            2°: {dominance?.second_side ?? '—'} — {fmtNum(dominance?.second_probability, 1)}%
          </p>
        </article>

        <article className="rounded-lg border border-violet-200 bg-violet-50/60 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">
            Quota X Cecchino
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(draw?.quota_x)}
          </p>
          <p className="mt-1 font-medium text-slate-800">{draw?.label ?? '—'}</p>
        </article>
      </div>

      <div className={`rounded-lg border px-4 py-3 ${severityStyles(operational?.severity)}`}>
        <p className="text-xs font-semibold uppercase tracking-wide opacity-80">
          Lettura operativa
        </p>
        <p className="mt-1 text-base font-semibold">
          <span className="mr-2">{severityIcon(operational?.severity)}</span>
          {operational?.label ?? '—'}
        </p>
        <p className="mt-1 text-sm opacity-90">{operational?.detail ?? '—'}</p>
        {cross_reading?.label && (
          <p className="mt-2 text-xs opacity-75">
            Incrocio: {cross_reading.label} — {cross_reading.description}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Sintesi modello
        </p>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-slate-500">Sintesi</dt>
            <dd className="font-medium text-slate-900">{summary?.main_label ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Direzione</dt>
            <dd className="font-medium text-slate-900">
              {summary?.favorite_direction ?? '—'}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs text-slate-500">Consiglio</dt>
            <dd className="text-slate-800">{summary?.short_advice ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Candidato X/Under</dt>
            <dd>{summary?.is_draw_under_candidate ? 'Sì' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Falso equilibrio</dt>
            <dd>{summary?.is_false_balance ? 'Sì' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Squilibrio confermato</dt>
            <dd>{summary?.is_confirmed_imbalance ? 'Sì' : 'No'}</dd>
          </div>
        </dl>
      </div>

      <details className="rounded-lg border border-slate-200 bg-white text-sm">
        <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
          Dettaglio tecnico equilibrio
        </summary>
        <div className="border-t border-slate-200 px-4 py-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs tabular-nums sm:grid-cols-3">
            <dt className="text-slate-500">quota_1</dt>
            <dd>{fmtNum(inputs?.quota_1)}</dd>
            <dt className="text-slate-500">quota_x</dt>
            <dd>{fmtNum(inputs?.quota_x)}</dd>
            <dt className="text-slate-500">quota_2</dt>
            <dd>{fmtNum(inputs?.quota_2)}</dd>
            <dt className="text-slate-500">prob_1 %</dt>
            <dd>{fmtNum(inputs?.prob_1, 1)}</dd>
            <dt className="text-slate-500">prob_x %</dt>
            <dd>{fmtNum(inputs?.prob_x, 1)}</dd>
            <dt className="text-slate-500">prob_2 %</dt>
            <dd>{fmtNum(inputs?.prob_2, 1)}</dd>
            <dt className="text-slate-500">F36 signed</dt>
            <dd>{fmtNum(f36?.signed)}</dd>
            <dt className="text-slate-500">F36 abs</dt>
            <dd>{fmtNum(f36?.abs)}</dd>
          </dl>
          <div className="mt-3 space-y-1 text-xs text-slate-600">
            <p>{technical?.f36_formula}</p>
            <p>{technical?.dominance_formula}</p>
            <p>Regola applicata: #{ruleId ?? '—'}</p>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-2 py-1 text-left font-medium">#</th>
                  <th className="px-2 py-1 text-left font-medium">Condizione</th>
                  <th className="px-2 py-1 text-left font-medium">Esito</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {OPERATIONAL_RULES.map((r) => (
                  <tr
                    key={r.id}
                    className={r.id === ruleId ? 'bg-sky-50 font-medium' : undefined}
                  >
                    <td className="px-2 py-1 tabular-nums">{r.id}</td>
                    <td className="px-2 py-1">{r.condition}</td>
                    <td className="px-2 py-1">{r.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
  )
}
