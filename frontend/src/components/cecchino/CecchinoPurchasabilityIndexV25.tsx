import { useId, useMemo, useState } from 'react'
import type { LiveIndexMarket, LiveModelPrediction } from '../../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import { bbOppTabIdle, bbOppTabScroll, bbOppTabSelected } from '../bet-builder/betBuilderStyles'
import { PatternRelationBadge } from './CecchinoPatternHero'
import { patternRelation } from './cecchinoPatternUtils'
import { v36BadgeClass } from './cecchinoPurchasabilityV36UiUtils'
import { PurchasabilityScoreRing } from './PurchasabilityScoreRing'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

/**
 * Indice di Acquistabilità V2.5 come orchestratore: le predizioni finali nascono dai moduli
 * (nessuna quota), i pattern accesi le confermano o no, la quota Bet365 dice solo se vale la pena.
 */

const SEGNO: Record<string, string> = {
  HOME: '1', DRAW: 'X', AWAY: '2', ONE_X: '1X', X_TWO: 'X2', ONE_TWO: '12',
  HOME_PT: '1 PT', DRAW_PT: 'X PT', AWAY_PT: '2 PT',
  OVER_0_5: 'Over 0.5', UNDER_0_5: 'Under 0.5', OVER_1_5: 'Over 1.5', UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5', UNDER_2_5: 'Under 2.5', OVER_3_5: 'Over 3.5', UNDER_3_5: 'Under 3.5',
}

export function indexClassLabel(score: number): string {
  if (score >= 80) return 'Molto Alta'
  if (score >= 70) return 'Alta'
  if (score >= 60) return 'Media'
  if (score >= 50) return 'Bassa'
  return 'Molto Bassa'
}

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${(v * 100).toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`
}

function num(v: number | null | undefined): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border border-slate-100 bg-white px-2 py-1.5">
      <p className="text-[10px] uppercase text-slate-500">{label}</p>
      <p className="font-semibold tabular-nums">{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  )
}

function label(key: string): string {
  return SEGNO[key] ?? MARKET_LABELS[key] ?? key
}

const MODULES_READ: Record<string, string> = {
  'V2.5': 'Picchetti, modello gol, Equilibrio, Intensità Goal e segnali',
  V3: 'La probabilità V3, che combina gli specialisti (forza, tiri, tiri in porta), la forma e il calendario,',
}

export function CecchinoPurchasabilityIndexV25({ p, model = 'V2.5' }: { p: LiveModelPrediction; model?: string }) {
  const panelId = useId()
  const index = p.modules?.purchasability_index
  const markets = index?.markets ?? {}
  const predictions = index?.predictions ?? []
  const minScore = index?.prediction_min_score ?? 70
  const minQuota = index?.playable_min_quota ?? 1.5
  // conferma solo dai pattern costruiti sui moduli (quelli che usano la quota restano a parte)
  const patternMarkets = useMemo(
    () => [...new Set((p.modules?.patterns?.active ?? []).filter((x) => x.target_type === 'market' && !x.uses_book).map((x) => x.target_key))],
    [p.modules?.patterns],
  )
  const others = useMemo(
    () => Object.entries(markets).filter(([k]) => !predictions.includes(k)).sort((a, b) => b[1].score - a[1].score),
    [markets, predictions],
  )
  const [selected, setSelected] = useState<string | null>(null)
  const current = selected && predictions.includes(selected) ? selected : predictions[0]
  const m: LiveIndexMarket | undefined = current ? markets[current] : undefined
  const relation = current ? patternRelation(current, patternMarkets) : null

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`} data-testid="purchasability-index-v25">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold tracking-wide text-slate-800">Indice di Acquistabilità {model}</h3>
          <span className="inline-flex items-center rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">{model}</span>
          <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900 ring-1 ring-amber-200">
            In osservazione
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Predizioni dei moduli {model}: il punteggio dice quanto la giocata è più probabile del normale per quel mercato. I pattern accesi le
          confermano o no; la quota Bet365 serve solo a capire se vale la pena (da {num(minQuota)} in su).
        </p>
      </div>

      {index?.status !== 'ok' ? (
        <p className="text-sm text-slate-600">Indice {model} non calcolabile per questa partita{index?.status === 'early_season' ? ': servono almeno 5 partite giocate per squadra.' : index?.error ? `: ${index.error}` : '.'}</p>
      ) : predictions.length === 0 ? (
        <p className="text-sm text-slate-600">Nessuna predizione forte: nessun mercato arriva a {minScore}/100 per i moduli {model}.</p>
      ) : (
        <>
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Predizioni dell&apos;indice</p>
            <div className={`${bbOppTabScroll} gap-1.5`} role="tablist" aria-label={`Predizioni indice ${model}`}>
              {predictions.map((k) => {
                const it = markets[k]
                const active = k === current
                const cls = indexClassLabel(it.score)
                return (
                  <button
                    key={k}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    aria-controls={`${panelId}-index-detail`}
                    className={active ? bbOppTabSelected : bbOppTabIdle}
                    onClick={() => setSelected(k)}
                  >
                    <span className="flex flex-col items-start gap-0.5 text-left">
                      <span className="text-[11px] font-medium">{label(k)}</span>
                      <span className="flex flex-wrap items-center gap-1">
                        <span className="text-sm font-bold tabular-nums">{Math.round(it.score)} / 100</span>
                        <span className={v36BadgeClass(cls)}>{cls}</span>
                      </span>
                      <span className="text-[10px] tabular-nums text-slate-500">quota {num(it.quota)}</span>
                      <PatternRelationBadge relation={patternRelation(k, patternMarkets)} />
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {m && current && (
            <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-3 sm:p-4" id={`${panelId}-index-detail`} role="tabpanel">
              <div className="flex flex-wrap items-center gap-4">
                <PurchasabilityScoreRing score={m.score} classLabel={indexClassLabel(m.score)} size="lg" title={`Indice ${model}`} testId="index-v25-ring" />
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Mercato</p>
                  <h4 className="text-base font-bold text-slate-900">{MARKET_LABELS[current] ?? label(current)}</h4>
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Vince (stima moduli)" value={pct(m.probability)} />
                <Metric label="Frequenza normale" value={pct(m.base_rate)} hint="quante volte esce questo mercato nello storico" />
                <Metric label="Quota minima" value={num(m.min_quota)} hint="sotto questa quota non rende" />
                <Metric label="Quota Bet365" value={num(m.quota)} hint={m.playable ? 'giocabile' : m.quota == null ? 'quota non disponibile' : `sotto ${num(minQuota)}: non giocabile`} />
              </div>

              <details open className="rounded-lg border border-slate-200 bg-slate-50/50 p-3">
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">Perché questo punteggio</summary>
                <dl className="mt-3 space-y-2 text-sm text-slate-700">
                  <div>
                    <dt className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Moduli</dt>
                    <dd>
                      {MODULES_READ[model] ?? 'I moduli'}, letti insieme, stimano che {label(current)} esca il{' '}
                      {pct(m.probability)} delle volte, contro il {pct(m.base_rate)} normale di questo mercato:{' '}
                      {((m.probability - m.base_rate) * 100).toLocaleString('it-IT', { maximumFractionDigits: 1, signDisplay: 'always' })} punti.
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Pattern</dt>
                    <dd>
                      {relation === 'confirmed'
                        ? `Confermata: un Pattern Master ${model} acceso indica lo stesso mercato.`
                        : relation === 'conflict'
                          ? `In contrasto: un Pattern Master ${model} acceso indica un esito opposto.`
                          : patternMarkets.length
                            ? 'I pattern accesi indicano altri mercati, compatibili con questa predizione.'
                            : 'Nessun pattern acceso su questa partita: vale la sola lettura dei moduli.'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Quota</dt>
                    <dd>
                      {m.quota == null
                        ? 'Quota Bet365 non disponibile per questo mercato.'
                        : m.playable
                          ? `Quota ${num(m.quota)}: da ${num(minQuota)} in su, vale la pena considerarla.`
                          : `Quota ${num(m.quota)}: sotto ${num(minQuota)}, non vale la pena investire.`}
                    </dd>
                  </div>
                </dl>
              </details>
            </div>
          )}
        </>
      )}

      {index?.status === 'ok' && others.length > 0 && (
        <details className="rounded-lg border border-slate-200 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">Altri mercati</summary>
          <ul className="mt-2 space-y-1 text-xs text-slate-600">
            {others.map(([k, it]) => (
              <li key={k}>
                {label(k)}: {Math.round(it.score)}/100 — vince {pct(it.probability)} (normale {pct(it.base_rate)})
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
