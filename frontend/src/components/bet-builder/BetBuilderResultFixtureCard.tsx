import { useState } from 'react'
import type { BetBuilderResultsFixture } from '../../lib/cecchinoBetBuilderApi'
import { bbCard, bbCardPadding, bbInEvidenzaBadge, bbSecondaryBtn } from './betBuilderStyles'
import {
  formatBookQuota,
  formatScoreLine,
  matchStatusLabel,
  outcomeBadgeClass,
  outcomeLabel,
} from './betBuilderResultsUtils'
import { formatKickoffShort, originBadgeLabel } from './betBuilderUtils'

type Props = {
  item: BetBuilderResultsFixture
  onOpenDetail: (item: BetBuilderResultsFixture) => void
}

function TeamSide({
  name,
  logo,
  align,
}: {
  name?: string | null
  logo?: string | null
  align: 'left' | 'right'
}) {
  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}
    >
      {logo ? (
        <img src={logo} alt="" className="h-9 w-9 shrink-0 rounded-full bg-slate-100 object-cover" />
      ) : (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-500">
          {(name ?? '?').slice(0, 1)}
        </span>
      )}
      <span className="truncate text-sm font-semibold text-slate-900">{name ?? '—'}</span>
    </div>
  )
}

export function BetBuilderResultFixtureCard({ item, onOpenDetail }: Props) {
  const [othersOpen, setOthersOpen] = useState(false)
  const { fixture, primary } = item
  const others = item.other_opportunities ?? []
  const matchStatus = fixture.match_status
  const outcome = primary.prediction_outcome
  const price = primary.price_value
  const purch = primary.purchasability_v31
  const signals = primary.signals
  const isLost = outcome === 'lost'
  const isWon = outcome === 'won'

  return (
    <article
      className={`${bbCard} ${bbCardPadding} space-y-3 overflow-hidden`}
      data-testid="bet-builder-result-card"
      data-fixture-id={fixture.today_fixture_id}
      data-outcome={outcome}
      data-match-status={matchStatus}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-slate-500">
            {[fixture.country, fixture.league].filter(Boolean).join(' · ') || '—'}
          </p>
          <p className="text-xs text-slate-500">{formatKickoffShort(fixture.kickoff)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {matchStatus === 'live' ? (
            <span
              className="inline-flex items-center rounded-md border border-sky-200 bg-sky-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-900"
              data-testid="result-live-badge"
            >
              LIVE
            </span>
          ) : (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {matchStatusLabel(matchStatus)}
            </span>
          )}
        </div>
      </header>

      <div className="flex items-center gap-2 sm:gap-3">
        <TeamSide name={fixture.home.name} logo={fixture.home.logo} align="left" />
        <div className="shrink-0 text-center">
          <p
            className="text-lg font-bold tabular-nums text-slate-900 sm:text-xl"
            data-testid="result-score"
          >
            {formatScoreLine(fixture.score, matchStatus)}
          </p>
        </div>
        <TeamSide name={fixture.away.name} logo={fixture.away.logo} align="right" />
      </div>

      <div
        className="space-y-2 rounded-2xl border border-emerald-200/80 bg-emerald-50/40 p-3"
        data-testid="result-primary-block"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={bbInEvidenzaBadge}>Predizione madre</span>
            <span className="text-lg font-semibold text-slate-900">{primary.market.label}</span>
          </div>
          <span
            className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${outcomeBadgeClass(outcome)}`}
            data-testid="result-outcome-badge"
          >
            {outcomeLabel(outcome)}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs sm:grid-cols-3 lg:grid-cols-4">
          <div>
            <dt className="text-slate-500">Origin</dt>
            <dd className="font-medium text-slate-800">{originBadgeLabel(primary.origin)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">V3.1</dt>
            <dd className="font-medium text-slate-800" data-testid="result-v31">
              {purch.score != null ? Math.round(purch.score) : 'N/D'}
              {purch.class ? ` · ${purch.class}` : ''}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Book</dt>
            <dd className="font-medium text-slate-800" data-testid="result-book">
              {formatBookQuota(price.quota_book)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Cecchino</dt>
            <dd className="font-medium text-slate-800">
              {price.quota_cecchino != null ? price.quota_cecchino.toFixed(2) : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Edge</dt>
            <dd className="font-medium text-slate-800">
              {price.edge_pct != null
                ? `${price.edge_pct > 0 ? '+' : ''}${price.edge_pct.toFixed(2)}%`
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Rating</dt>
            <dd className="font-medium text-slate-800">
              {price.rating != null ? price.rating : '—'}
              {price.rating_label ? ` · ${price.rating_label}` : ''}
            </dd>
          </div>
          <div className="col-span-2 sm:col-span-1">
            <dt className="text-slate-500">Signals</dt>
            <dd className="font-medium text-slate-800">
              {signals.yes_count}/{signals.available_count || signals.required_count || '—'}
              {signals.yes_columns?.length ? ` · ${signals.yes_columns.join(' · ')}` : ''}
            </dd>
          </div>
        </dl>
      </div>

      {others.length > 0 ? (
        <div data-testid="result-others-accordion">
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-left text-sm font-medium text-slate-800"
            aria-expanded={othersOpen}
            data-testid="result-others-toggle"
            onClick={() => setOthersOpen((v) => !v)}
          >
            <span>
              Altre opportunity · {others.length}
            </span>
            <span aria-hidden>{othersOpen ? '−' : '+'}</span>
          </button>
          {othersOpen ? (
            <ul className="mt-2 space-y-1.5" data-testid="result-others-list">
              {others.map((op) => (
                <li
                  key={op.opportunity_key}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-2 text-sm"
                  data-testid="result-other-row"
                >
                  <span className="font-semibold text-slate-900">{op.market.label}</span>
                  <span className="text-xs text-slate-500">
                    {originBadgeLabel(op.origin)}
                    {op.purchasability_v31.score != null
                      ? ` · V3.1 ${Math.round(op.purchasability_v31.score)}`
                      : ''}
                    {op.price_value.quota_book != null
                      ? ` · Book ${op.price_value.quota_book.toFixed(2)}`
                      : ' · Book N/D'}
                  </span>
                  <span
                    className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase ${outcomeBadgeClass(op.prediction_outcome)}`}
                  >
                    {outcomeLabel(op.prediction_outcome)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={bbSecondaryBtn}
          data-testid="result-analyze-cta"
          onClick={() => onOpenDetail(item)}
        >
          {isLost ? 'Analizza perdita' : isWon ? 'Apri analisi' : 'Apri dettaglio'}
        </button>
      </div>
    </article>
  )
}
