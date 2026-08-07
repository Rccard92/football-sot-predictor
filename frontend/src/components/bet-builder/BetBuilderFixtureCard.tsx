import { motion, useReducedMotion } from 'framer-motion'
import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import type { BetBuilderFixtureGroup, BetBuilderViewMode } from './betBuilderUtils'
import {
  formatKickoffShort,
  getPrimaryOpportunity,
  resolveSelectedOpportunity,
} from './betBuilderUtils'
import { BetBuilderOpportunitySelector } from './BetBuilderOpportunitySelector'
import { BetBuilderSelectedOpportunityPanel } from './BetBuilderSelectedOpportunityPanel'
import type { BetBuilderCartCtaState } from './cart/betBuilderCartUtils'
import { bbCard, bbCardPadding, bbSecondaryBtn } from './betBuilderStyles'

type CartHandlers = {
  getCtaFor: (opportunity: BetBuilderOpportunity) => BetBuilderCartCtaState
  cartOpportunityKeys: ReadonlySet<string>
  fixtureCartLabel?: string
  onAdd: (opportunity: BetBuilderOpportunity) => void
  onReplace: (opportunity: BetBuilderOpportunity) => void
  onRemove: (opportunity: BetBuilderOpportunity) => void
}

type Props = {
  group: BetBuilderFixtureGroup
  scanDate: string
  viewMode: BetBuilderViewMode
  cart?: CartHandlers
}

function TeamLogo({
  name,
  logo,
  sizeClass,
}: {
  name: string
  logo?: string | null
  sizeClass: string
}) {
  if (logo) {
    return (
      <img
        src={logo}
        alt={`Logo ${name}`}
        className={`${sizeClass} shrink-0 rounded-full object-cover bg-slate-100`}
        loading="lazy"
      />
    )
  }
  return (
    <span
      className={`flex ${sizeClass} shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-500`}
      aria-hidden
    >
      {(name || '?').slice(0, 1).toUpperCase()}
    </span>
  )
}

export function BetBuilderFixtureCard({ group, scanDate, viewMode, cart }: Props) {
  const reduceMotion = useReducedMotion()
  const panelId = useId()
  const primary = getPrimaryOpportunity(group)
  /** Intent utente; se key assente dopo filter/revision → resolveSelectedOpportunity fa fallback. */
  const [userSelectedKey, setUserSelectedKey] = useState<string | null>(null)

  const selected = resolveSelectedOpportunity(group.opportunities, userSelectedKey)
  const homeName = group.fixture.home.name ?? 'Home'
  const awayName = group.fixture.away.name ?? 'Away'
  const country = group.fixture.country ?? ''
  const league = group.fixture.league ?? ''
  const meta = [country, league].filter(Boolean).join(' · ')
  const analysisHref = `/cecchino-today?date=${encodeURIComponent(scanDate)}&fixture=${group.todayFixtureId}`
  const isPrimarySelected =
    Boolean(selected && primary && selected.opportunity_key === primary.opportunity_key)
  const cartCta = selected && cart ? cart.getCtaFor(selected) : undefined

  return (
    <motion.article
      className={`${bbCard} ${bbCardPadding} flex flex-col gap-4`}
      data-testid="bet-builder-fixture-card"
      data-fixture-id={group.todayFixtureId}
      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.2, ease: 'easeOut' }}
    >
      <header className="space-y-3 border-b border-slate-100 pb-3">
        <div
          className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-2 gap-y-1"
          data-testid="bet-builder-fixture-meta"
        >
          {meta ? (
            <p className="min-w-0 break-words text-xs font-medium uppercase tracking-wide text-slate-500">
              {meta}
            </p>
          ) : (
            <span />
          )}
          <span className="shrink-0 justify-self-end rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold tabular-nums text-slate-800">
            {formatKickoffShort(group.fixture.kickoff)}
          </span>
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-2.5 sm:gap-3">
            <TeamLogo
              name={homeName}
              logo={group.fixture.home.logo}
              sizeClass="h-10 w-10 sm:h-12 sm:w-12 md:h-14 md:w-14"
            />
            <span className="line-clamp-2 min-w-0 break-words text-[15px] font-semibold leading-tight text-slate-900 sm:text-base md:text-lg">
              {homeName}
            </span>
          </div>
          <span className="shrink-0 text-xs font-semibold uppercase tracking-wider text-slate-400">
            vs
          </span>
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2.5 sm:gap-3">
            <span className="line-clamp-2 min-w-0 break-words text-right text-[15px] font-semibold leading-tight text-slate-900 sm:text-base md:text-lg">
              {awayName}
            </span>
            <TeamLogo
              name={awayName}
              logo={group.fixture.away.logo}
              sizeClass="h-10 w-10 sm:h-12 sm:w-12 md:h-14 md:w-14"
            />
          </div>
        </div>
      </header>

      <BetBuilderOpportunitySelector
        opportunities={group.opportunities}
        selectedKey={selected?.opportunity_key ?? ''}
        onSelect={setUserSelectedKey}
        panelId={panelId}
        cartOpportunityKeys={cart?.cartOpportunityKeys}
        fixtureCartLabel={cart?.fixtureCartLabel}
      />

      {selected ? (
        <div data-testid="bet-builder-fixture-opportunities">
          <div
            data-testid="bet-builder-opportunity-row"
            data-origin={selected.origin}
            data-market={selected.market.market_key}
            data-opportunity-key={selected.opportunity_key}
          >
            <BetBuilderSelectedOpportunityPanel
              opportunity={selected}
              isPrimary={isPrimarySelected}
              viewMode={viewMode}
              panelId={panelId}
              cartCta={cartCta}
              onCartAdd={cart ? () => cart.onAdd(selected) : undefined}
              onCartReplace={cart ? () => cart.onReplace(selected) : undefined}
              onCartRemove={
                cart
                  ? () => cart.onRemove(selected)
                  : undefined
              }
            />
          </div>
        </div>
      ) : null}

      <div className="mt-auto flex justify-stretch pt-1 sm:justify-end">
        <Link
          to={analysisHref}
          className={`${bbSecondaryBtn} w-full sm:w-auto`}
          aria-label={`Apri analisi manuale ${homeName} vs ${awayName}`}
          data-testid="bet-builder-manual-analysis"
        >
          Apri analisi manuale →
        </Link>
      </div>
    </motion.article>
  )
}
