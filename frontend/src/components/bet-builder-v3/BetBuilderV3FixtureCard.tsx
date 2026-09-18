import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import type { BbV3PatternRelation } from '../../lib/cecchinoBetBuilderV3Api'
import {
  bbBadge,
  bbCard,
  bbCardPadding,
  bbInEvidenzaBadge,
  bbInEvidenzaBadgeOnDark,
  bbInEvidenzaBadgeOnLight,
  bbMetricCell,
  bbOppTabIdle,
  bbOppTabPrimary,
  bbOppTabPrimarySelected,
  bbOppTabScroll,
  bbOppTabSelected,
  bbSecondaryBtn,
} from '../bet-builder/betBuilderStyles'
import { formatKickoffShort } from '../bet-builder/betBuilderUtils'
import { indexClassLabel } from '../cecchino/CecchinoPurchasabilityIndexV25'
import { PurchasabilityScoreRing } from '../cecchino/PurchasabilityScoreRing'
import { PATTERN_RELATION_LABEL, type BbV3Group, type BbV3Opportunity, type BbV3Tab } from './bbV3Utils'

type Props = {
  group: BbV3Group
  tab: BbV3Tab
  showOutcome: boolean
}

function TeamLogo({ name, logo, sizeClass }: { name: string; logo?: string | null; sizeClass: string }) {
  if (logo) {
    return (
      <img
        src={logo}
        alt={`Logo ${name}`}
        className={`${sizeClass} shrink-0 rounded-full bg-slate-100 object-cover`}
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

function fmtQuota(n: number | null | undefined): string {
  return n == null || Number.isNaN(n) ? '—' : n.toFixed(2)
}

function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v.toLocaleString('it-IT', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`
}

function fmtProb(v: number | null | undefined): string {
  return v == null ? '—' : fmtPct(v * 100)
}

function signedPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${fmtPct(v)}`
}

function relationBadgeClass(rel: BbV3PatternRelation): string {
  if (rel === 'confermata') return `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
  if (rel === 'in_contrasto') return `${bbBadge} border-rose-200 bg-rose-50 text-rose-900`
  return `${bbBadge} border-slate-200 bg-slate-50 text-slate-600`
}

function OutcomeBadge({ won }: { won: boolean | null }) {
  if (won === true) return <span className={`${bbBadge} border-emerald-300 bg-emerald-600 text-white`}>Vinta</span>
  if (won === false) return <span className={`${bbBadge} border-rose-300 bg-rose-600 text-white`}>Persa</span>
  return <span className={`${bbBadge} border-slate-200 bg-slate-50 text-slate-600`}>In attesa</span>
}

const TAB_RING_TITLE: Record<BbV3Tab, string> = {
  'V2.5': 'Indice V2.5',
  V3: 'Indice V3',
  combo: 'Combo V2.5 + V3',
}

function OpportunityTabs({
  opportunities,
  selectedKey,
  onSelect,
  panelId,
  showOutcome,
}: {
  opportunities: BbV3Opportunity[]
  selectedKey: string
  onSelect: (key: string) => void
  panelId: string
  showOutcome: boolean
}) {
  const n = opportunities.length
  const primaryKey = opportunities[0]?.key
  if (n === 1) {
    return (
      <div className="flex flex-wrap items-center gap-2" data-testid="bb-v3-opportunity-selector">
        <span className={`${bbBadge} border-slate-200 bg-slate-50 text-slate-700`}>1 opportunità</span>
        <span className={bbInEvidenzaBadge}>In evidenza</span>
      </div>
    )
  }
  return (
    <div className="space-y-2" data-testid="bb-v3-opportunity-selector">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{n} opportunità</p>
      <div className={bbOppTabScroll} role="tablist" aria-label="Seleziona opportunità">
        {opportunities.map((op) => {
          const isPrimary = op.key === primaryKey
          const selected = op.key === selectedKey
          let className = bbOppTabIdle
          if (isPrimary && selected) className = bbOppTabPrimarySelected
          else if (isPrimary) className = bbOppTabPrimary
          else if (selected) className = bbOppTabSelected
          const onDark = isPrimary && selected
          const labelClass = onDark
            ? 'text-sm font-semibold leading-tight text-white sm:text-base'
            : isPrimary
              ? 'text-sm font-semibold leading-tight text-emerald-950 sm:text-base'
              : 'text-sm font-semibold leading-tight text-slate-900'
          const scoreClass = onDark
            ? 'tabular-nums text-base font-semibold text-white'
            : isPrimary
              ? 'tabular-nums text-base font-semibold text-emerald-950'
              : 'tabular-nums text-sm font-semibold text-slate-900'
          const mutedClass = onDark ? 'text-white/70' : isPrimary ? 'text-emerald-700/70' : 'text-slate-400'
          const microClass = onDark
            ? 'text-[10px] font-medium text-white/75'
            : isPrimary
              ? 'text-[10px] font-medium text-emerald-800/80'
              : 'text-[10px] font-medium text-slate-500'
          const micro = showOutcome
            ? op.won === true
              ? 'Vinta'
              : op.won === false
                ? 'Persa'
                : 'In attesa'
            : op.playable
              ? `Quota ${fmtQuota(op.quota)}`
              : 'Non giocabile'
          return (
            <button
              key={op.key}
              type="button"
              role="tab"
              id={`bb-v3-tab-${op.key}`}
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              className={`${className} ${isPrimary ? 'min-w-[5.5rem] sm:min-w-[6.5rem]' : ''}`}
              data-testid="bb-v3-opportunity-tab"
              onClick={() => onSelect(op.key)}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className={labelClass}>{op.label}</span>
                {isPrimary ? (
                  <span className={onDark ? bbInEvidenzaBadgeOnDark : bbInEvidenzaBadgeOnLight}>In evidenza</span>
                ) : null}
              </span>
              <span className={scoreClass}>
                {Math.round(op.score)}
                <span className={mutedClass}> / 100</span>
              </span>
              <span className={microClass}>{micro}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function SelectedPanel({
  op,
  tab,
  isPrimary,
  panelId,
  showOutcome,
}: {
  op: BbV3Opportunity
  tab: BbV3Tab
  isPrimary: boolean
  panelId: string
  showOutcome: boolean
}) {
  const reduceMotion = useReducedMotion()
  const duration = reduceMotion ? 0 : 0.18
  const y = reduceMotion ? 0 : 5
  const relations: { label: string; rel: BbV3PatternRelation }[] =
    tab === 'combo'
      ? [
          ...(op.patternV25 ? [{ label: 'V2.5', rel: op.patternV25 }] : []),
          ...(op.patternV3 ? [{ label: 'V3', rel: op.patternV3 }] : []),
        ]
      : op.pattern
        ? [{ label: '', rel: op.pattern }]
        : []

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={op.key}
        id={panelId}
        role="tabpanel"
        aria-labelledby={`bb-v3-tab-${op.key}`}
        initial={{ opacity: 0, y }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -y }}
        transition={{ duration, ease: 'easeOut' }}
        className="space-y-4 rounded-2xl border border-slate-200 bg-white p-3 sm:p-4"
        data-testid="bb-v3-selected-opportunity"
      >
        <div className="flex max-w-full flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 max-w-full space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="break-words text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{op.label}</h3>
              {isPrimary ? <span className={bbInEvidenzaBadge}>In evidenza</span> : null}
              {showOutcome ? <OutcomeBadge won={op.won} /> : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {relations.map((r) => (
                <span key={r.label || r.rel} className={relationBadgeClass(r.rel)}>
                  {r.label ? `${r.label}: ` : ''}
                  {PATTERN_RELATION_LABEL[r.rel]}
                </span>
              ))}
              <span
                className={
                  op.playable
                    ? `${bbBadge} border-sky-200 bg-sky-50 text-sky-900`
                    : `${bbBadge} border-amber-200 bg-amber-50 text-amber-900`
                }
              >
                {op.playable ? 'Giocabile' : 'Quota sotto 1,50'}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2" data-testid="bb-v3-core-metrics">
          <div className={bbMetricCell}>
            <PurchasabilityScoreRing
              score={op.score}
              classLabel={indexClassLabel(op.score)}
              size="md"
              title={TAB_RING_TITLE[tab]}
              testId="bb-v3-ring"
            />
          </div>

          <div className={bbMetricCell} aria-label="Quota">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Quota</p>
            <p className="mt-1 whitespace-nowrap text-lg font-semibold tabular-nums text-slate-900">{fmtQuota(op.quota)}</p>
            <p className="text-xs text-slate-500">Bet365</p>
            <p className="mt-1 text-base font-semibold tabular-nums text-slate-800">
              <span className="whitespace-nowrap">{fmtQuota(op.minQuota)}</span>
              <span className="mt-0.5 block text-xs font-medium text-slate-500 sm:ml-1 sm:mt-0 sm:inline">
                Quota minima
              </span>
            </p>
          </div>

          {tab === 'combo' ? (
            <div className={bbMetricCell} aria-label="Punteggi dei due modelli">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">I due modelli</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                {op.scoreV25 != null ? Math.round(op.scoreV25) : '—'}
                <span className="text-xs font-medium text-slate-500"> V2.5</span>
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                {op.scoreV3 != null ? Math.round(op.scoreV3) : '—'}
                <span className="text-xs font-medium text-slate-500"> V3</span>
              </p>
              <p className="mt-1 text-xs text-slate-500">Il cerchio mostra il più prudente dei due.</p>
            </div>
          ) : (
            <div className={bbMetricCell} aria-label="Stima dei moduli">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Vince (stima moduli)</p>
              <p className="mt-1 whitespace-nowrap text-lg font-semibold tabular-nums text-slate-900">
                {fmtProb(op.probability)}
              </p>
              <p className="mt-2 text-sm font-semibold tabular-nums text-slate-800">{fmtProb(op.baseRate)}</p>
              <p className="text-xs text-slate-500">Frequenza normale del mercato</p>
            </div>
          )}

          <div className={bbMetricCell} aria-label="Pattern">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Pattern</p>
            {op.patternInfo ? (
              <>
                <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                  {op.patternInfo.patterns_count} {op.patternInfo.patterns_count === 1 ? 'pattern' : 'pattern'}
                </p>
                <p className="mt-1 text-sm text-slate-700">
                  Riuscita storica <span className="font-semibold tabular-nums">{fmtPct(op.patternInfo.hist_win_pct)}</span>
                </p>
                <p className="text-sm text-slate-700">
                  ROI storico <span className="font-semibold tabular-nums">{signedPct(op.patternInfo.hist_roi_pct)}</span>
                </p>
              </>
            ) : (
              <p className="mt-1 text-sm text-slate-600">
                {tab === 'combo'
                  ? 'Nessun pattern dei due modelli è in contrasto.'
                  : 'Nessun pattern acceso su questo mercato.'}
              </p>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

export function BetBuilderV3FixtureCard({ group, tab, showOutcome }: Props) {
  const reduceMotion = useReducedMotion()
  const panelId = useId()
  const [userKey, setUserKey] = useState<string | null>(null)
  const selected = group.opportunities.find((o) => o.key === userKey) ?? group.opportunities[0]
  const fx = group.fixture
  const homeName = fx.home.name ?? 'Casa'
  const awayName = fx.away.name ?? 'Ospite'
  const meta = [fx.country, fx.league].filter(Boolean).join(' · ')
  const analysisHref = `/cecchino-today?date=${encodeURIComponent(fx.scan_date)}&fixture=${fx.today_fixture_id}`
  const scoreText = fx.score ? `${fx.score.home} - ${fx.score.away}` : null

  return (
    <motion.article
      className={`${bbCard} ${bbCardPadding} flex flex-col gap-4`}
      data-testid="bb-v3-fixture-card"
      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.2, ease: 'easeOut' }}
    >
      <header className="space-y-3 border-b border-slate-100 pb-3">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-2 gap-y-1">
          {meta ? (
            <p className="min-w-0 break-words text-xs font-medium uppercase tracking-wide text-slate-500">{meta}</p>
          ) : (
            <span />
          )}
          <span className="shrink-0 justify-self-end rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm font-semibold tabular-nums text-slate-800">
            {showOutcome && scoreText ? scoreText : formatKickoffShort(fx.kickoff)}
          </span>
        </div>
        <div className="flex items-center gap-3 sm:gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-2.5 sm:gap-3">
            <TeamLogo name={homeName} logo={fx.home.logo} sizeClass="h-10 w-10 sm:h-12 sm:w-12 md:h-14 md:w-14" />
            <span className="line-clamp-2 min-w-0 break-words text-[15px] font-semibold leading-tight text-slate-900 sm:text-base md:text-lg">
              {homeName}
            </span>
          </div>
          <span className="shrink-0 text-xs font-semibold uppercase tracking-wider text-slate-400">vs</span>
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2.5 sm:gap-3">
            <span className="line-clamp-2 min-w-0 break-words text-right text-[15px] font-semibold leading-tight text-slate-900 sm:text-base md:text-lg">
              {awayName}
            </span>
            <TeamLogo name={awayName} logo={fx.away.logo} sizeClass="h-10 w-10 sm:h-12 sm:w-12 md:h-14 md:w-14" />
          </div>
        </div>
      </header>

      <OpportunityTabs
        opportunities={group.opportunities}
        selectedKey={selected?.key ?? ''}
        onSelect={setUserKey}
        panelId={panelId}
        showOutcome={showOutcome}
      />

      {selected ? (
        <SelectedPanel
          op={selected}
          tab={tab}
          isPrimary={selected.key === group.opportunities[0]?.key}
          panelId={panelId}
          showOutcome={showOutcome}
        />
      ) : null}

      <div className="mt-auto flex justify-stretch pt-1 sm:justify-end">
        <Link
          to={analysisHref}
          className={`${bbSecondaryBtn} w-full sm:w-auto`}
          aria-label={`Apri analisi ${homeName} vs ${awayName}`}
        >
          Apri analisi manuale →
        </Link>
      </div>
    </motion.article>
  )
}
