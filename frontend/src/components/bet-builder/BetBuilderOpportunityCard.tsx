import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import { Link } from 'react-router-dom'
import { BetBuilderContextBlock } from './BetBuilderContextBlock'
import { BetBuilderPriceBlock } from './BetBuilderPriceBlock'
import { BetBuilderPurchasabilityBlock } from './BetBuilderPurchasabilityBlock'
import { BetBuilderSignalsBlock } from './BetBuilderSignalsBlock'
import { bbBadge, bbCard, bbCardPadding, bbSecondaryBtn } from './betBuilderStyles'
import { formatKickoffShort, originBadgeLabel } from './betBuilderUtils'

type Props = {
  opportunity: BetBuilderOpportunity
  scanDate: string
}

function TeamLogo({
  name,
  logo,
}: {
  name: string
  logo?: string | null
}) {
  if (logo) {
    return (
      <img
        src={logo}
        alt={`Logo ${name}`}
        className="h-9 w-9 shrink-0 rounded-full object-cover bg-slate-100"
        loading="lazy"
      />
    )
  }
  return (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-500"
      aria-hidden
    >
      {(name || '?').slice(0, 1).toUpperCase()}
    </span>
  )
}

function originBadgeClass(origin: BetBuilderOpportunity['origin']): string {
  if (origin === 'price') return `${bbBadge} border-sky-200 bg-sky-50 text-sky-900`
  if (origin === 'signals') return `${bbBadge} border-violet-200 bg-violet-50 text-violet-900`
  return `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
}

export function BetBuilderOpportunityCard({ opportunity, scanDate }: Props) {
  const homeName = opportunity.fixture.home.name ?? 'Home'
  const awayName = opportunity.fixture.away.name ?? 'Away'
  const country = opportunity.fixture.country ?? ''
  const league = opportunity.fixture.league ?? ''
  const meta = [country, league].filter(Boolean).join(' · ')
  const analysisHref = `/cecchino-today?date=${encodeURIComponent(scanDate)}&fixture=${opportunity.fixture.today_fixture_id}`

  return (
    <article
      className={`${bbCard} ${bbCardPadding} flex flex-col gap-4`}
      data-testid="bet-builder-opportunity-card"
      data-origin={opportunity.origin}
      data-market={opportunity.market.market_key}
    >
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {meta ? <p className="truncate text-xs font-medium text-slate-500">{meta}</p> : null}
            <p className="text-sm font-semibold tabular-nums text-slate-800">
              {formatKickoffShort(opportunity.fixture.kickoff)}
            </p>
          </div>
          <span className={originBadgeClass(opportunity.origin)}>
            {originBadgeLabel(opportunity.origin)}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <TeamLogo name={homeName} logo={opportunity.fixture.home.logo} />
            <span className="truncate text-sm font-semibold text-slate-900">{homeName}</span>
          </div>
          <span className="shrink-0 text-xs font-medium uppercase text-slate-400">vs</span>
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
            <span className="truncate text-right text-sm font-semibold text-slate-900">
              {awayName}
            </span>
            <TeamLogo name={awayName} logo={opportunity.fixture.away.logo} />
          </div>
        </div>

        <p className="text-center text-2xl font-semibold tracking-tight text-slate-900">
          {opportunity.market.label}
        </p>
      </header>

      <BetBuilderPurchasabilityBlock purchasability={opportunity.purchasability_v31} />
      <BetBuilderPriceBlock price={opportunity.price_value} />
      <BetBuilderSignalsBlock
        signals={opportunity.signals}
        marketKey={opportunity.market.market_key}
      />
      <BetBuilderContextBlock
        context={opportunity.context_support}
        marketLabel={opportunity.market.label}
      />

      <div className="mt-auto pt-1">
        <Link
          to={analysisHref}
          className={`${bbSecondaryBtn} w-full`}
          aria-label={`Apri analisi manuale ${homeName} vs ${awayName}`}
        >
          Apri analisi manuale
        </Link>
      </div>
    </article>
  )
}
