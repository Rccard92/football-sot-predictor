import type { CecchinoBalanceAnalysis } from '../../lib/cecchinoTodayApi'
import { CecchinoBalanceLegend } from './CecchinoBalanceLegend'
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

function deltaForceCardStyles(severity?: string): string {
  switch (severity) {
    case 'positive':
      return 'border-emerald-200 bg-emerald-50/70'
    case 'warning':
      return 'border-amber-200 bg-amber-50/70'
    case 'negative':
      return 'border-violet-300 bg-violet-50/70'
    default:
      return 'border-slate-200 bg-slate-50/70'
  }
}

function dominanceCardStyles(effect?: string): string {
  switch (effect) {
    case 'reinforces_balance':
      return 'border-emerald-200 bg-emerald-50/70'
    case 'weakens_balance':
      return 'border-amber-200 bg-amber-50/70'
    case 'confirms_imbalance':
      return 'border-violet-300 bg-violet-50/70'
    default:
      return 'border-indigo-200 bg-indigo-50/60'
  }
}

function sideLabel(side?: string, label?: string): string {
  if (label) return label
  if (side === 'HOME') return '1'
  if (side === 'DRAW') return 'X'
  if (side === 'AWAY') return '2'
  return side ?? '—'
}

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

  const {
    f36,
    side_probability_gap,
    dominance,
    dominance_context: domCtx,
    draw,
    operational,
    summary,
    cross_reading,
    inputs,
    technical,
    delta_force: deltaForce,
  } = balanceAnalysis
  const deltaMatch = deltaForce?.match
  const ruleId = technical?.rule_id
  const effect = domCtx?.effect_on_balance

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio</h3>
        <p className={todaySectionSubtitle}>
          Lettura del bilanciamento della partita basata su quota 1/2 Cecchino, dominanza del
          modello e quota X.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <article className="rounded-lg border border-sky-200 bg-sky-50/60 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-800">F36</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(f36?.abs)}
          </p>
          <p className="mt-1 font-medium text-slate-800">{f36?.label ?? '—'}</p>
          <p className="mt-1 text-xs text-slate-600">Score {f36?.score ?? '—'}/100</p>
          {f36?.direction_note && (
            <p className="mt-2 text-xs text-slate-600">{f36.direction_note}</p>
          )}
        </article>

        <article className={`rounded-lg border p-3 text-sm ${dominanceCardStyles(effect)}`}>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-700">
            Dominanza
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(dominance?.value ?? domCtx?.dominance_value)} p.p.
          </p>
          <p className="mt-1 font-medium text-slate-800">{domCtx?.label ?? '—'}</p>
          <p className="mt-2 text-xs tabular-nums text-slate-700">
            Domina: {sideLabel(dominance?.best_side, dominance?.best_side_label)}{' '}
            {fmtNum(dominance?.best_probability ?? domCtx?.best_probability, 1)}%
            <br />
            Secondo: {sideLabel(dominance?.second_side, dominance?.second_side_label)}{' '}
            {fmtNum(dominance?.second_probability ?? domCtx?.second_probability, 1)}%
          </p>
          {domCtx?.interpretation && (
            <p className="mt-2 text-xs text-slate-600">{domCtx.interpretation}</p>
          )}
          {effect === 'reinforces_balance' && (
            <p className="mt-1 text-xs font-medium text-emerald-800">Rafforza equilibrio</p>
          )}
          {effect === 'weakens_balance' && (
            <p className="mt-1 text-xs font-medium text-amber-800">Indebolisce equilibrio</p>
          )}
          {effect === 'confirms_imbalance' && (
            <p className="mt-1 text-xs font-medium text-violet-800">Conferma squilibrio</p>
          )}
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

        <article className="rounded-lg border border-teal-200 bg-teal-50/60 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">
            Gap 1/2 Prob.
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {fmtNum(side_probability_gap?.value)} p.p.
          </p>
          <p className="mt-1 font-medium text-slate-800">
            {side_probability_gap?.label ?? '—'}
          </p>
        </article>

        <article className={`rounded-lg border p-3 text-sm ${deltaForceCardStyles(deltaMatch?.severity)}`}>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-700">
            Delta Forza
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {deltaMatch?.delta_forza_abs != null ? `${fmtNum(deltaMatch.delta_forza_abs, 1)}%` : '—'}
          </p>
          <p className="mt-1 font-medium text-slate-800">{deltaMatch?.label ?? '—'}</p>
          {deltaMatch?.responsible_side_label && (
            <p className="mt-2 text-xs text-slate-700">
              Segno responsabile: {deltaMatch.responsible_side_label}
            </p>
          )}
          {deltaMatch?.responsible_direction_label && (
            <p className="mt-1 text-xs text-slate-600">{deltaMatch.responsible_direction_label}</p>
          )}
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
            <dt className="text-xs text-slate-500">X dominante</dt>
            <dd>{summary?.is_x_dominance ? 'Sì' : 'No'}</dd>
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
          <div>
            <dt className="text-xs text-slate-500">Partita lineare</dt>
            <dd>{summary?.is_linear_match ? 'Sì' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Partita non lineare</dt>
            <dd>{summary?.is_non_linear_match ? 'Sì' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Forte distorsione</dt>
            <dd>{summary?.has_strong_delta_distortion ? 'Sì' : 'No'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs text-slate-500">Delta Forza</dt>
            <dd className="text-slate-800">{summary?.delta_force_label ?? '—'}</dd>
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
            <dt className="text-slate-500">best_side</dt>
            <dd>{dominance?.best_side ?? domCtx?.best_side ?? '—'}</dd>
            <dt className="text-slate-500">effect_on_balance</dt>
            <dd>{technical?.effect_on_balance ?? domCtx?.effect_on_balance ?? '—'}</dd>
          </dl>
          <div className="mt-3 space-y-1 text-xs text-slate-600">
            <p>{technical?.f36_formula}</p>
            <p>{technical?.dominance_formula}</p>
            <p>{technical?.side_gap_formula}</p>
            <p>{technical?.x_dominance_note}</p>
            <p>{technical?.lateral_dominance_note}</p>
            <p>Regola applicata: #{ruleId ?? '—'}</p>
            {technical?.legend_version && (
              <p>Legenda: {technical.legend_version}</p>
            )}
          </div>
          {deltaForce?.rows && deltaForce.rows.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Delta Forza 1X2
              </p>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-100 text-slate-600">
                    <tr>
                      <th className="px-2 py-2 text-left">Segno</th>
                      <th className="px-2 py-2 text-left">Quota Betfair</th>
                      <th className="px-2 py-2 text-left">Quota Cecchino</th>
                      <th className="px-2 py-2 text-left">Edge %</th>
                      <th className="px-2 py-2 text-left">Delta Forza</th>
                      <th className="px-2 py-2 text-left">Lettura</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {deltaForce.rows.map((row) => (
                      <tr key={row.segno ?? row.market_key}>
                        <td className="px-2 py-2 font-medium text-slate-800">{row.segno}</td>
                        <td className="px-2 py-2 tabular-nums">{fmtNum(row.quota_book)}</td>
                        <td className="px-2 py-2 tabular-nums">{fmtNum(row.quota_cecchino)}</td>
                        <td className="px-2 py-2 tabular-nums">
                          {row.edge_pct != null ? `${fmtNum(row.edge_pct, 1)}%` : '—'}
                        </td>
                        <td className="px-2 py-2 tabular-nums">
                          {row.delta_forza_abs != null ? `${fmtNum(row.delta_forza_abs, 1)}%` : '—'}
                        </td>
                        <td className="px-2 py-2 text-slate-800">{row.label ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-600">
                Il Delta Forza è il valore assoluto dell&apos;Edge %. L&apos;Edge indica la direzione
                del valore; il Delta indica la distanza tra quota matematica e quota Betfair.
              </p>
            </div>
          )}
        </div>
      </details>

      <CecchinoBalanceLegend />
    </section>
  )
}
