import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useEffect, useId, useRef } from 'react'
import type { BetBuilderResultsFixture } from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderContextBlock } from './BetBuilderContextBlock'
import { bbSecondaryBtn } from './betBuilderStyles'
import {
  formatBookQuota,
  formatScoreLine,
  matchStatusLabel,
  outcomeBadgeClass,
  outcomeLabel,
} from './betBuilderResultsUtils'
import { formatKickoffShort, originBadgeLabel } from './betBuilderUtils'

type Props = {
  open: boolean
  item: BetBuilderResultsFixture | null
  onClose: () => void
}

export function BetBuilderResultDetailDrawer({ open, item, onClose }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement as HTMLElement | null
    const t = window.setTimeout(() => closeRef.current?.focus(), 0)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.clearTimeout(t)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      previouslyFocused.current?.focus?.()
    }
  }, [open, onClose])

  const duration = reduceMotion ? 0 : 0.22
  const primary = item?.primary
  const fixture = item?.fixture
  const score = fixture?.score
  const others = item?.other_opportunities ?? []

  return (
    <AnimatePresence>
      {open && item && primary && fixture ? (
        <div
          className="fixed inset-0 z-50"
          role="presentation"
          data-testid="bet-builder-result-drawer-root"
        >
          <motion.button
            type="button"
            aria-label="Chiudi dettaglio"
            className="absolute inset-0 bg-slate-900/40"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration }}
            data-testid="bet-builder-result-drawer-overlay"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="absolute inset-x-0 bottom-0 flex max-h-[88dvh] flex-col overflow-hidden rounded-t-2xl bg-[#F6F7F9] shadow-xl md:inset-y-0 md:bottom-auto md:right-0 md:left-auto md:h-[100dvh] md:max-h-none md:w-[min(100vw-24px,440px)] md:rounded-none"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
            initial={reduceMotion ? false : { opacity: 0.9, y: 40 }}
            animate={{ opacity: 1, y: 0, x: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: 24 }}
            transition={{ duration, ease: 'easeOut' }}
            data-testid="bet-builder-result-drawer"
          >
            <div className="flex justify-center pt-2 md:hidden" aria-hidden>
              <span className="h-1 w-10 rounded-full bg-slate-300" />
            </div>

            <div className="flex shrink-0 items-start justify-between gap-2 border-b border-slate-200 bg-white px-4 py-3">
              <div className="min-w-0">
                <h2 id={titleId} className="text-base font-semibold text-slate-900">
                  Analisi prediction
                </h2>
                <p className="mt-0.5 truncate text-sm text-slate-600">
                  {fixture.home.name} – {fixture.away.name}
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                className={bbSecondaryBtn}
                onClick={onClose}
                data-testid="result-drawer-close"
              >
                Chiudi
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
              <section className="rounded-xl border border-slate-200 bg-white p-3" data-testid="drawer-match">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Match</h3>
                <p className="mt-1 text-sm text-slate-700">
                  {[fixture.country, fixture.league].filter(Boolean).join(' · ')} ·{' '}
                  {formatKickoffShort(fixture.kickoff)} · {matchStatusLabel(fixture.match_status)}
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-slate-900">
                  {formatScoreLine(score, fixture.match_status)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  HT:{' '}
                  {score?.halftime_home != null && score?.halftime_away != null
                    ? `${score.halftime_home} – ${score.halftime_away}`
                    : '—'}{' '}
                  · FT:{' '}
                  {score?.fulltime_home != null && score?.fulltime_away != null
                    ? `${score.fulltime_home} – ${score.fulltime_away}`
                    : '—'}
                </p>
              </section>

              <section className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3" data-testid="drawer-primary">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                  Predizione madre
                </h3>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-xl font-semibold text-slate-900">{primary.market.label}</span>
                  <span
                    className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-bold uppercase ${outcomeBadgeClass(primary.prediction_outcome)}`}
                  >
                    {outcomeLabel(primary.prediction_outcome)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{originBadgeLabel(primary.origin)}</p>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-3 space-y-2 text-sm">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quota</h3>
                <dl className="grid grid-cols-2 gap-2">
                  <div>
                    <dt className="text-slate-500">Book</dt>
                    <dd className="font-semibold" data-testid="drawer-book">
                      {formatBookQuota(primary.price_value.quota_book)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Cecchino</dt>
                    <dd className="font-semibold">
                      {primary.price_value.quota_cecchino?.toFixed(2) ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Edge</dt>
                    <dd className="font-semibold">
                      {primary.price_value.edge_pct != null
                        ? `${primary.price_value.edge_pct > 0 ? '+' : ''}${primary.price_value.edge_pct.toFixed(2)}%`
                        : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Rating</dt>
                    <dd className="font-semibold">
                      {primary.price_value.rating ?? '—'}
                      {primary.price_value.rating_label
                        ? ` · ${primary.price_value.rating_label}`
                        : ''}
                    </dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Acquistabilità
                </h3>
                <p className="mt-1 font-semibold">
                  {primary.purchasability_v31.score != null
                    ? Math.round(primary.purchasability_v31.score)
                    : 'N/D'}
                  {primary.purchasability_v31.class
                    ? ` · ${primary.purchasability_v31.class}`
                    : ''}
                  {primary.purchasability_v31.status
                    ? ` · ${primary.purchasability_v31.status}`
                    : ''}
                </p>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Segnali
                </h3>
                <p className="mt-1">
                  {primary.signals.yes_count}/{primary.signals.available_count} SI
                  {primary.signals.yes_columns?.length
                    ? ` · ${primary.signals.yes_columns.join(' · ')}`
                    : ''}
                </p>
                <p className="text-xs text-slate-500">
                  soglia {primary.signals.required_count} · passed{' '}
                  {primary.signals.passed ? 'sì' : 'no'}
                </p>
              </section>

              {primary.context_support.available || primary.context_support.reason ? (
                <section className="rounded-xl border border-slate-200 bg-white p-3">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Contesto
                  </h3>
                  <BetBuilderContextBlock
                    context={primary.context_support}
                    marketLabel={primary.market.label}
                    compact
                  />
                </section>
              ) : null}

              {others.length > 0 ? (
                <section className="rounded-xl border border-slate-200 bg-white p-3" data-testid="drawer-others">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Altre opportunity
                  </h3>
                  <ul className="mt-2 space-y-2">
                    {others.map((op) => (
                      <li
                        key={op.opportunity_key}
                        className="flex items-center justify-between gap-2 text-sm"
                      >
                        <span className="font-medium">{op.market.label}</span>
                        <span
                          className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase ${outcomeBadgeClass(op.prediction_outcome)}`}
                        >
                          {outcomeLabel(op.prediction_outcome)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <p className="text-xs text-slate-500">
                Evidenze pre-match analitiche. Nessuna spiegazione causale automatica.
              </p>
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
