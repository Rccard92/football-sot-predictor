import { useMemo, useState } from 'react'
import type { LiveModelPrediction } from '../../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import { v36BadgeClass } from './cecchinoPurchasabilityV36UiUtils'
import { breakEvenQuota, groupPatternSignals, referencePattern, type PatternRelation } from './cecchinoPatternUtils'

/** Predizione del modello: pattern Master con quota accesi, in cima alla scheda (grafica del Pannello KPI). */

/** Conferma o contrasto di un mercato dell'indice con la predizione dei pattern. */
export function PatternRelationBadge({ relation }: { relation: PatternRelation }) {
  if (relation === 'confirmed') {
    return <span className="inline-flex rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-900 ring-1 ring-emerald-200">Indicato dal pattern</span>
  }
  if (relation === 'conflict') {
    return <span className="inline-flex rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-900 ring-1 ring-red-200">In contrasto col pattern</span>
  }
  return null
}

export type MarketIndex = { score: number | null | undefined; label: string | null | undefined; title: string }

const PATTERNS_PER_GROUP_VISIBLE = 5

function num(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })
}

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })}${suffix}`
}

function Cell({ label, value, className = 'text-white' }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`text-sm font-semibold tabular-nums ${className}`}>{value}</dd>
    </div>
  )
}

export function CecchinoPatternHero({
  p,
  model,
  indexFor,
}: {
  p: LiveModelPrediction | undefined
  model: string
  indexFor?: (marketKey: string) => MarketIndex | null
}) {
  const patterns = p?.modules?.patterns
  const groups = useMemo(
    () => groupPatternSignals((patterns?.active ?? []).filter((x) => x.target_type === 'market')),
    [patterns],
  )
  const [openKey, setOpenKey] = useState<string | null>(null)
  const results = p?.result?.markets ?? {}

  return (
    <section className="overflow-hidden rounded-xl border border-slate-300 shadow-md" data-testid={`pattern-hero-${model}`}>
      <div className="bg-[#1e3a5f] px-4 py-3">
        <h3 className="text-sm font-bold tracking-wide text-white sm:text-base">PREDIZIONE {model} · PATTERN ACCESI</h3>
        <p className="mt-1 text-[10px] text-slate-300 sm:text-xs">
          Mercati con quota Bet365 indicati dai Pattern Master {model} che valgono in questa partita · riuscita e ROI dello storico
        </p>
      </div>

      <div className="bg-[#163352] p-3">
        {patterns?.status !== 'ok' ? (
          <p className="px-1 py-2 text-sm text-slate-300">Pattern Master {model} non disponibili per questa partita.</p>
        ) : groups.length === 0 ? (
          <p className="px-1 py-2 text-sm text-slate-300">
            Nessun pattern con quota acceso: per la {model} questa partita non ha una giocata indicata.
          </p>
        ) : (
          <div className="grid gap-2 lg:grid-cols-2">
            {groups.map((g) => {
              const ref = referencePattern(g)
              const key = g.first.target_key
              const quota = g.first.quota_book
              const minQuota = breakEvenQuota(ref.win_rate_pct)
              const evToday = quota != null && ref.win_rate_pct != null ? (ref.win_rate_pct / 100) * quota * 100 - 100 : null
              const inProfit = quota != null && minQuota != null && quota >= minQuota
              const won = results[key]?.won
              const idx = indexFor?.(key)
              const open = openKey === g.key
              return (
                <article key={g.key} className="rounded-lg border border-slate-500/40 bg-[#1a3d5c]/40 p-3 text-white">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-lg font-bold">{MARKET_LABELS[key] ?? g.first.market_label}</span>
                      <span className="rounded-full bg-sky-500/80 px-2 py-0.5 text-[10px] font-semibold uppercase">
                        {g.patterns.length} {g.patterns.length === 1 ? 'pattern' : 'pattern concordi'}
                      </span>
                    </div>
                    {won != null &&
                      (won ? (
                        <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold text-white">Vinta</span>
                      ) : (
                        <span className="rounded-full bg-slate-600 px-2 py-0.5 text-[10px] font-semibold text-slate-100">Persa</span>
                      ))}
                  </div>

                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
                    <Cell label="Riuscita storica" value={`${num(ref.win_rate_pct, 1)}%`} />
                    <Cell label="Quota minima" value={num(minQuota)} className="text-amber-100" />
                    <Cell label="Quota Bet365" value={num(quota)} />
                    <Cell label="ROI storico" value={signed(ref.roi_pct)} className={(ref.roi_pct ?? 0) > 0 ? 'text-emerald-300' : 'text-orange-300'} />
                  </dl>

                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-500/40 pt-2 text-xs">
                    {quota == null ? (
                      <span className="text-slate-300">Quota Bet365 non disponibile</span>
                    ) : inProfit ? (
                      <span className="font-semibold text-emerald-300">Quota in profitto · atteso {signed(evToday)} per giocata</span>
                    ) : (
                      <span className="font-semibold text-orange-300">Quota sotto la minima · atteso {signed(evToday)} per giocata</span>
                    )}
                    {idx && idx.score != null && (
                      <span className="ml-auto inline-flex items-center gap-1.5 text-slate-300">
                        {idx.title} <span className="font-semibold tabular-nums text-white">{Math.round(idx.score)}/100</span>
                        {idx.label && <span className={v36BadgeClass(idx.label)}>{idx.label}</span>}
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setOpenKey(open ? null : g.key)}
                    aria-expanded={open}
                    className="mt-2 text-[11px] font-medium text-slate-300 underline"
                  >
                    {open ? 'Nascondi condizioni' : `Condizioni (su ${ref.total_n} partite)`}
                  </button>
                  {open && (
                    <ul className="mt-2 space-y-1.5 border-l-2 border-slate-500/50 pl-3">
                      {g.patterns.slice(0, PATTERNS_PER_GROUP_VISIBLE).map((x) => (
                        <li key={x.id} className="text-xs text-slate-300">
                          <span className="font-medium tabular-nums text-white">
                            {num(x.win_rate_pct, 1)}% · ROI {signed(x.roi_pct)} · {x.total_n} partite
                          </span>{' '}
                          — {x.conditions_text}
                        </li>
                      ))}
                      {g.patterns.length > PATTERNS_PER_GROUP_VISIBLE && (
                        <li className="text-xs text-slate-400">e altri {g.patterns.length - PATTERNS_PER_GROUP_VISIBLE} pattern con condizioni simili</li>
                      )}
                    </ul>
                  )}
                </article>
              )
            })}
          </div>
        )}
        {patterns?.status === 'ok' && (
          <p className="mt-2 px-1 text-[11px] text-slate-400">
            Quota minima = 100 / riuscita storica: sotto questa quota il pattern non rende. Pattern in osservazione, andamento reale in
            Osservazione live.
          </p>
        )}
      </div>
    </section>
  )
}
