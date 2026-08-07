import { motion, useReducedMotion } from 'framer-motion'
import { formatCombinedOddsDisplay } from './betBuilderCartUtils'

type Props = {
  selectionCount: number
  combinedOdds: number | null
  onOpen: () => void
}

/**
 * Controllo flottante persistente.
 * Desktop: bottom-right. Mobile: bottom sticky con safe-area (nav mobile è top bar).
 */
export function BetBuilderCartButton({ selectionCount, combinedOdds, onOpen }: Props) {
  const reduceMotion = useReducedMotion()
  const oddsLabel =
    selectionCount === 0
      ? null
      : combinedOdds == null
        ? 'N/D'
        : `×${formatCombinedOddsDisplay(combinedOdds)}`
  const discrete = selectionCount === 0
  const countLabel =
    selectionCount === 1 ? '1 selezione' : `${selectionCount} selezioni`

  return (
    <motion.div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-3 md:inset-x-auto md:bottom-6 md:right-6 md:justify-end"
      style={{
        paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom, 0px))',
      }}
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.22, ease: 'easeOut' }}
      data-testid="bet-builder-floating-cart"
    >
      <button
        type="button"
        onClick={onOpen}
        className={
          discrete
            ? 'pointer-events-auto flex min-h-11 items-center gap-2 rounded-xl border border-slate-200/90 bg-white/95 px-3 py-2 text-sm font-medium text-slate-600 shadow-md shadow-slate-900/10 backdrop-blur transition hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 md:min-w-[11rem]'
            : 'pointer-events-auto flex min-h-12 w-full max-w-md items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900 px-4 py-3 text-white shadow-lg shadow-slate-900/25 transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 md:w-auto md:min-w-[16rem]'
        }
        aria-label={
          discrete
            ? 'Apri schedina, 0 selezioni'
            : `Apri schedina, ${countLabel}${oddsLabel ? `, moltiplicatore ${oddsLabel}` : ''}`
        }
        data-testid="bet-builder-floating-cart-button"
      >
        <span className="flex min-w-0 flex-col items-start text-left">
          <span
            className={
              discrete
                ? 'text-sm font-semibold text-slate-700'
                : 'text-sm font-semibold tracking-tight'
            }
          >
            Schedina · {selectionCount}
          </span>
          {!discrete ? (
            <span className="text-xs text-white/70 md:hidden">{countLabel}</span>
          ) : null}
        </span>
        {!discrete ? (
          <span className="flex shrink-0 items-center gap-3">
            <span
              className="tabular-nums text-base font-semibold"
              data-testid="bet-builder-floating-multiplier"
            >
              {oddsLabel}
            </span>
            <span className="hidden rounded-lg bg-white/15 px-2.5 py-1 text-xs font-semibold sm:inline">
              Apri
            </span>
          </span>
        ) : null}
      </button>
    </motion.div>
  )
}
