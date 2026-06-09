import type { CecchinoIcmAnalysis } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  icmAnalysis?: CecchinoIcmAnalysis
}

function severityStyles(severity?: string | null): string {
  switch (severity) {
    case 'negative':
      return 'border-red-200 bg-red-50 text-red-900'
    case 'warning':
      return 'border-amber-200 bg-amber-50 text-amber-900'
    case 'positive':
      return 'border-teal-200 bg-teal-50 text-teal-900'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-800'
  }
}

function driverSymbolClass(symbol?: string): string {
  switch (symbol) {
    case '✓':
      return 'text-emerald-700'
    case '~':
      return 'text-amber-700'
    case '✗':
      return 'text-red-700'
    default:
      return 'text-slate-500'
  }
}

export function CecchinoIcmAnalysisPanel({ icmAnalysis }: Props) {
  if (!icmAnalysis || icmAnalysis.status !== 'available') {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Indice di Convergenza Match</h3>
        <p className={todaySectionSubtitle}>
          Misura quanto gli indicatori Cecchino convergono verso una lettura univoca del match.
        </p>
        <p className="mt-3 text-sm text-slate-500">
          ICM non disponibile: dati balance o KPI insufficienti.
        </p>
      </section>
    )
  }

  const { score_pct, label, short_label, severity, dominant_narrative, drivers, composition, technical, candidate_narratives } =
    icmAnalysis

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Indice di Convergenza Match</h3>
        <p className={todaySectionSubtitle}>
          Misura quanto gli indicatori Cecchino convergono verso una lettura univoca del match.
        </p>
      </div>

      <div className={`rounded-lg border px-4 py-4 ${severityStyles(severity)}`}>
        <div className="flex flex-wrap items-baseline gap-3">
          <p className="text-3xl font-bold tabular-nums">{score_pct ?? '—'}%</p>
          <div>
            <p className="text-base font-semibold">{label ?? '—'}</p>
            {short_label && <p className="text-xs opacity-80">{short_label}</p>}
          </div>
        </div>
        {dominant_narrative && (
          <div className="mt-3">
            <p className="text-sm font-semibold">{dominant_narrative.label}</p>
            <p className="mt-1 text-sm opacity-90">{dominant_narrative.description}</p>
          </div>
        )}
      </div>

      {drivers && drivers.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Driver della decisione
          </p>
          <ul className="mt-2 space-y-1.5 text-sm">
            {drivers.map((driver, idx) => (
              <li key={driver.key ?? idx} className="flex gap-2">
                <span className={`shrink-0 font-semibold ${driverSymbolClass(driver.symbol)}`}>
                  {driver.symbol ?? '•'}
                </span>
                <span className="text-slate-800">{driver.plain_text ?? '—'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="rounded-lg border border-slate-200 bg-white text-sm">
        <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
          Come viene composto l&apos;ICM
        </summary>
        <div className="border-t border-slate-200 px-4 py-3 space-y-3">
          <p className="text-xs text-slate-600">
            L&apos;ICM valuta cinque pilastri del modello Cecchino e sceglie la narrativa dominante
            con il punteggio più alto. Una penalità di ambiguità riduce il punteggio quando più
            scenari sono vicini.
          </p>
          <ul className="space-y-2 text-xs">
            {(composition ?? []).map((item) => (
              <li key={item.key} className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
                <p className="font-medium text-slate-800">{item.label}</p>
                <p className="text-slate-500">{item.source}</p>
                <p className="mt-1 text-slate-700">{item.plain_text}</p>
              </li>
            ))}
          </ul>
        </div>
      </details>

      {technical && (
        <details className="rounded-lg border border-slate-200 bg-white text-sm">
          <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
            Dettaglio tecnico ICM
          </summary>
          <div className="border-t border-slate-200 px-4 py-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs tabular-nums sm:grid-cols-3">
              <dt className="text-slate-500">Narrativa vincente</dt>
              <dd className="col-span-1 sm:col-span-2">{technical.best_narrative ?? '—'}</dd>
              <dt className="text-slate-500">Score narrativa</dt>
              <dd>{technical.best_score ?? '—'}</dd>
              <dt className="text-slate-500">Secondo score</dt>
              <dd>{technical.second_score ?? '—'}</dd>
              <dt className="text-slate-500">Gap</dt>
              <dd>{technical.gap ?? '—'}</dd>
              <dt className="text-slate-500">Penalità ambiguità</dt>
              <dd>{technical.ambiguity_penalty ?? '—'}</dd>
              <dt className="text-slate-500">Score finale</dt>
              <dd>{technical.final_score ?? '—'}</dd>
            </dl>
            {candidate_narratives && candidate_narratives.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-100 text-slate-600">
                    <tr>
                      <th className="px-2 py-2 text-left">Narrativa</th>
                      <th className="px-2 py-2 text-left">Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {candidate_narratives.map((c) => (
                      <tr key={c.key}>
                        <td className="px-2 py-2 text-slate-800">{c.label ?? c.key}</td>
                        <td className="px-2 py-2 tabular-nums">{c.score ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>
      )}
    </section>
  )
}
