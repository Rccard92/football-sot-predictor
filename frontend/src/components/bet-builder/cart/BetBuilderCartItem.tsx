import { motion, useReducedMotion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { originBadgeLabel } from '../betBuilderUtils'
import { bbBadge, bbSecondaryBtn } from '../betBuilderStyles'
import {
  formatOddsDisplay,
  purchasabilitySummaryLabel,
  signalsSummaryLabel,
  type BetBuilderCartResolvedItem,
} from './betBuilderCartUtils'

type Props = {
  item: BetBuilderCartResolvedItem
  scanDate: string
  onRemove: () => void
}

function originBadgeClass(origin: string): string {
  if (origin === 'price') return `${bbBadge} border-sky-200 bg-sky-50 text-sky-900`
  if (origin === 'signals') return `${bbBadge} border-violet-200 bg-violet-50 text-violet-900`
  return `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
}

export function BetBuilderCartItem({ item, scanDate, onRemove }: Props) {
  const reduceMotion = useReducedMotion()
  const { stored, status, current, current_book_odds, odds_changed } = item
  const home = current?.fixture.home.name ?? stored.home.name ?? 'Home'
  const away = current?.fixture.away.name ?? stored.away.name ?? 'Away'
  const country = current?.fixture.country ?? stored.country ?? ''
  const league = current?.fixture.league ?? stored.league ?? ''
  const meta = [country, league].filter(Boolean).join(' · ')
  const marketLabel = current?.market.label ?? stored.market_label
  const origin = current?.origin
  const analysisHref = `/cecchino-today?date=${encodeURIComponent(scanDate)}&fixture=${stored.today_fixture_id}`
  const stale = status === 'stale'

  return (
    <motion.article
      layout={!reduceMotion}
      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduceMotion ? undefined : { opacity: 0, height: 0, marginBottom: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.18 }}
      className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
      data-testid="bet-builder-cart-item"
      data-opportunity-key={stored.opportunity_key}
      data-status={status}
      data-fixture-id={stored.today_fixture_id}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          {meta ? (
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
              {meta}
            </p>
          ) : null}
          <p className="text-sm font-semibold text-slate-900">
            {home} – {away}
          </p>
          <p className="text-base font-semibold tracking-tight text-slate-950">{marketLabel}</p>
        </div>
        <span
          className={
            stale
              ? `${bbBadge} border-amber-200 bg-amber-50 text-amber-950`
              : `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
          }
          data-testid="bet-builder-cart-item-status"
        >
          {stale ? 'Non disponibile' : 'Attuale'}
        </span>
      </div>

      {stale ? (
        <p className="mt-2 text-xs text-slate-600" data-testid="bet-builder-cart-item-stale-msg">
          Non più disponibile nel Bet Builder corrente
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {origin ? (
            <span className={originBadgeClass(origin)}>{originBadgeLabel(origin)}</span>
          ) : null}
        </div>
      )}

      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-slate-50 px-2 py-1.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Book
          </dt>
          <dd
            className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900"
            data-testid="bet-builder-cart-item-odds"
          >
            {stale ? formatOddsDisplay(stored.added_book_odds) : formatOddsDisplay(current_book_odds)}
          </dd>
          {!stale && odds_changed && stored.added_book_odds != null ? (
            <motion.p
              className="mt-0.5 text-[10px] tabular-nums text-slate-500"
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              data-testid="bet-builder-cart-item-odds-changed"
            >
              {formatOddsDisplay(stored.added_book_odds)} → {formatOddsDisplay(current_book_odds)}
            </motion.p>
          ) : null}
          {!stale && current_book_odds == null ? (
            <p className="mt-0.5 text-[10px] text-amber-800">Quota Book non disponibile</p>
          ) : null}
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-1.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            V3.1
          </dt>
          <dd className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
            {purchasabilitySummaryLabel(current)}
          </dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-1.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Segnali
          </dt>
          <dd className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
            {signalsSummaryLabel(current)}
          </dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className={`${bbSecondaryBtn} min-h-11 flex-1 sm:flex-none`}
          onClick={onRemove}
          aria-label={`Rimuovi ${marketLabel} dalla schedina`}
          data-testid="bet-builder-cart-item-remove"
        >
          Rimuovi
        </button>
        <Link
          to={analysisHref}
          className={`${bbSecondaryBtn} min-h-11 flex-1 sm:flex-none`}
          aria-label={`Apri analisi ${home} vs ${away}`}
          data-testid="bet-builder-cart-item-analysis"
        >
          Apri analisi
        </Link>
      </div>
    </motion.article>
  )
}
