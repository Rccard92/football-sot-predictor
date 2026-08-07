import { Link } from 'react-router-dom'
import type { BetBuilderFixtureGroup } from './betBuilderUtils'
import { BetBuilderOpportunityRow } from './BetBuilderOpportunityRow'
import { bbCard, bbCardPadding, bbSecondaryBtn } from './betBuilderStyles'
import { formatKickoffShort } from './betBuilderUtils'

type Props = {
  group: BetBuilderFixtureGroup
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

function formatOriginBreakdown(counts: BetBuilderFixtureGroup['counts']): string {
  const parts: string[] = []
  if (counts.price_and_signals > 0) {
    parts.push(
      `${counts.price_and_signals} Quota + Segnali`,
    )
  }
  if (counts.signals_only > 0) {
    parts.push(`${counts.signals_only} Segnali`)
  }
  if (counts.price_only > 0) {
    parts.push(`${counts.price_only} Quota`)
  }
  return parts.join(' · ')
}

export function BetBuilderFixtureCard({ group, scanDate }: Props) {
  const homeName = group.fixture.home.name ?? 'Home'
  const awayName = group.fixture.away.name ?? 'Away'
  const country = group.fixture.country ?? ''
  const league = group.fixture.league ?? ''
  const meta = [country, league].filter(Boolean).join(' · ')
  const analysisHref = `/cecchino-today?date=${encodeURIComponent(scanDate)}&fixture=${group.todayFixtureId}`
  const n = group.counts.total
  const opportunityLabel = n === 1 ? '1 opportunity' : `${n} opportunity`
  const breakdown = formatOriginBreakdown(group.counts)

  return (
    <article
      className={`${bbCard} ${bbCardPadding} flex flex-col gap-4`}
      data-testid="bet-builder-fixture-card"
      data-fixture-id={group.todayFixtureId}
    >
      <header className="space-y-3">
        <div className="min-w-0">
          {meta ? <p className="truncate text-xs font-medium text-slate-500">{meta}</p> : null}
          <p className="text-sm font-semibold tabular-nums text-slate-800">
            {formatKickoffShort(group.fixture.kickoff)}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <TeamLogo name={homeName} logo={group.fixture.home.logo} />
            <span className="truncate text-sm font-semibold text-slate-900">{homeName}</span>
          </div>
          <span className="shrink-0 text-xs font-medium uppercase text-slate-400">vs</span>
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
            <span className="truncate text-right text-sm font-semibold text-slate-900">
              {awayName}
            </span>
            <TeamLogo name={awayName} logo={group.fixture.away.logo} />
          </div>
        </div>

        <div className="space-y-0.5">
          <p className="text-sm font-semibold uppercase tracking-wide text-slate-700">
            {opportunityLabel}
          </p>
          {breakdown ? <p className="text-xs text-slate-500">{breakdown}</p> : null}
        </div>
      </header>

      <div className="flex flex-col gap-0" data-testid="bet-builder-fixture-opportunities">
        {group.opportunities.map((op) => (
          <BetBuilderOpportunityRow key={op.opportunity_key} opportunity={op} />
        ))}
      </div>

      <div className="mt-auto pt-1">
        <Link
          to={analysisHref}
          className={`${bbSecondaryBtn} w-full`}
          aria-label={`Apri analisi manuale ${homeName} vs ${awayName}`}
          data-testid="bet-builder-manual-analysis"
        >
          Apri analisi manuale
        </Link>
      </div>
    </article>
  )
}
