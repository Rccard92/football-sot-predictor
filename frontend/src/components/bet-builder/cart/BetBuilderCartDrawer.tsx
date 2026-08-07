import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useEffect, useId, useRef } from 'react'
import { bbPrimaryBtn, bbSecondaryBtn } from '../betBuilderStyles'
import { BetBuilderCartItem } from './BetBuilderCartItem'
import { BetBuilderCartSummary } from './BetBuilderCartSummary'
import type { BetBuilderCartResolvedItem } from './betBuilderCartUtils'

type Props = {
  open: boolean
  onClose: () => void
  date: string
  items: BetBuilderCartResolvedItem[]
  combinedOdds: number | null
  onRemove: (identity: { today_fixture_id: number; opportunity_key: string }) => void
  onClear: () => void
}

function formatCartDate(isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00Z`)
  if (Number.isNaN(d.getTime())) return isoDate
  return new Intl.DateTimeFormat('it-IT', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(d)
}

/**
 * Un solo dialog accessibile:
 * - mobile: bottom sheet
 * - desktop (md+): drawer destro ~420px
 */
export function BetBuilderCartDrawer({
  open,
  onClose,
  date,
  items,
  combinedOdds,
  onRemove,
  onClear,
}: Props) {
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

  return (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-50" role="presentation" data-testid="bet-builder-cart-drawer-root">
          <motion.button
            type="button"
            aria-label="Chiudi schedina"
            className="absolute inset-0 bg-slate-900/40"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration }}
            data-testid="bet-builder-cart-overlay"
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="absolute inset-x-0 bottom-0 flex max-h-[85dvh] flex-col rounded-t-2xl bg-[#F6F7F9] shadow-xl md:inset-y-0 md:bottom-auto md:right-0 md:left-auto md:h-[100dvh] md:max-h-none md:w-[min(100vw-24px,420px)] md:rounded-none"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
            initial={
              reduceMotion
                ? false
                : { opacity: 0.9, y: 40 }
            }
            animate={{ opacity: 1, y: 0, x: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: 24 }}
            transition={{ duration, ease: 'easeOut' }}
            data-testid="bet-builder-cart-panel"
          >
            <div className="flex justify-center pt-2 md:hidden" aria-hidden>
              <span className="h-1 w-10 rounded-full bg-slate-300" />
            </div>

            <div className="flex shrink-0 items-start justify-between gap-2 border-b border-slate-200 bg-white px-4 py-3">
              <div className="min-w-0">
                <h2 id={titleId} className="text-base font-semibold text-slate-900">
                  La tua selezione
                </h2>
                <p className="mt-0.5 text-sm text-slate-600" data-testid="bet-builder-cart-date">
                  {formatCartDate(date)}
                </p>
                <p className="text-xs text-slate-500" data-testid="bet-builder-cart-count">
                  {items.length === 1 ? '1 selezione' : `${items.length} selezioni`}
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                data-testid="bet-builder-cart-close"
              >
                Chiudi
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
              {items.length === 0 ? (
                <p
                  className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500"
                  data-testid="bet-builder-cart-empty"
                >
                  Nessuna selezione. Usa «+ Aggiungi alla schedina» sulle opportunity.
                </p>
              ) : (
                <AnimatePresence initial={false}>
                  {items.map((item) => (
                    <BetBuilderCartItem
                      key={`${item.stored.today_fixture_id}::${item.stored.opportunity_key}`}
                      item={item}
                      scanDate={date}
                      onRemove={() =>
                        onRemove({
                          today_fixture_id: item.stored.today_fixture_id,
                          opportunity_key: item.stored.opportunity_key,
                        })
                      }
                    />
                  ))}
                </AnimatePresence>
              )}
            </div>

            <div className="shrink-0 space-y-2 border-t border-slate-200 bg-white px-3 py-3">
              <BetBuilderCartSummary selectionCount={items.length} combinedOdds={combinedOdds} />
              {items.length > 0 ? (
                <button
                  type="button"
                  className={`${bbSecondaryBtn} w-full`}
                  onClick={onClear}
                  data-testid="bet-builder-cart-clear"
                >
                  Svuota schedina
                </button>
              ) : (
                <button
                  type="button"
                  className={`${bbPrimaryBtn} w-full`}
                  disabled
                  aria-disabled
                >
                  Schedina vuota
                </button>
              )}
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
