import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useBetBuilderResultAnalysisContext } from '../../hooks/useBetBuilderResultAnalysisContext'
import { BetBuilderResultTechnicalAnalysis } from '../bet-builder/BetBuilderResultTechnicalAnalysis'
import { bbBadge, bbSecondaryBtn } from '../bet-builder/betBuilderStyles'
import { formatKickoffDateTime } from '../bet-builder/betBuilderUtils'
import { indexClassLabel } from '../cecchino/CecchinoPurchasabilityIndexV25'
import { PurchasabilityScoreRing } from '../cecchino/PurchasabilityScoreRing'
import {
  INDEX_RELATION_LABEL,
  PATTERN_RELATION_LABEL,
  type BbV3Group,
  type BbV3Opportunity,
  type BbV3Tab,
} from './bbV3Utils'

/** Analisi manuale di una partita del Bet Builder V3 in un pannello laterale, senza lasciare la pagina
 *  (come il vecchio Bet Builder): risultato, predizioni dell'indice, quota e analisi tecnica completa. */

type Props = {
  open: boolean
  group: BbV3Group | null
  tab: BbV3Tab
  initialKey: string | null
  onClose: () => void
}

const TAB_TITLE: Record<BbV3Tab, string> = {
  'V2.5': 'Indice V2.5',
  V3: 'Indice V3',
  combo: 'Combo V2.5 + V3',
}

const STATUS_LABEL: Record<string, string> = {
  finished: 'Conclusa',
  live: 'Live',
  upcoming: 'Da giocare',
}

function fmtQuota(n: number | null | undefined): string {
  return n == null || Number.isNaN(n) ? '—' : n.toFixed(2)
}

function fmtProb(v: number | null | undefined): string {
  return v == null ? '—' : `${(v * 100).toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`
}

function pair(h: number | null | undefined, a: number | null | undefined): string {
  return h == null || a == null ? '—' : `${h} – ${a}`
}

function OutcomeBadge({ won }: { won: boolean | null }) {
  if (won === true) return <span className={`${bbBadge} border-emerald-300 bg-emerald-600 text-white`}>Vinta</span>
  if (won === false) return <span className={`${bbBadge} border-rose-300 bg-rose-600 text-white`}>Persa</span>
  return <span className={`${bbBadge} border-slate-200 bg-slate-50 text-slate-600`}>In attesa</span>
}

function Section({
  title,
  children,
  testId,
  className = 'rounded-xl border border-slate-200 bg-white p-3',
}: {
  title: string
  children: ReactNode
  testId?: string
  className?: string
}) {
  return (
    <section className={className} data-testid={testId}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function relationText(op: BbV3Opportunity): string | null {
  if (op.source === 'pattern') return op.indexRelation ? INDEX_RELATION_LABEL[op.indexRelation] : null
  return op.pattern ? PATTERN_RELATION_LABEL[op.pattern] : null
}

export function BetBuilderV3AnalysisDrawer({ open, group, tab, initialKey, onClose }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)
  const reduceMotion = useReducedMotion()
  const [pickedKey, setPickedKey] = useState<string | null>(null)

  const fixture = group?.fixture ?? null
  const todayFixtureId = fixture?.today_fixture_id
  const { state: contextState, retry } = useBetBuilderResultAnalysisContext(todayFixtureId, open && todayFixtureId != null)

  // la scelta fatta nel pannello vale solo finche' resta aperto sulla stessa partita
  const [lastFixture, setLastFixture] = useState<number | undefined>(todayFixtureId)
  if (lastFixture !== todayFixtureId) {
    setLastFixture(todayFixtureId)
    setPickedKey(null)
  }

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

  const opportunities = group?.opportunities ?? []
  const op =
    opportunities.find((o) => o.key === (pickedKey ?? initialKey)) ?? opportunities[0] ?? null
  const duration = reduceMotion ? 0 : 0.22
  const score = fixture?.score ?? null
  const status = fixture ? STATUS_LABEL[fixture.match_status] ?? '' : ''
  const todayHref = fixture
    ? `/cecchino-today?date=${encodeURIComponent(fixture.scan_date)}&fixture=${fixture.today_fixture_id}`
    : '#'
  const relation = op ? relationText(op) : null

  return (
    <AnimatePresence>
      {open && group && fixture && op ? (
        <div className="fixed inset-0 z-50" role="presentation" data-testid="bb-v3-analysis-drawer-root">
          <motion.button
            type="button"
            aria-label="Chiudi analisi"
            className="absolute inset-0 bg-slate-900/40"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration }}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="absolute inset-x-0 bottom-0 flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-2xl bg-[#F6F7F9] shadow-xl md:inset-y-0 md:bottom-auto md:right-0 md:left-auto md:h-[100dvh] md:max-h-none md:w-[min(94vw,760px)] md:rounded-none lg:w-[min(90vw,860px)] xl:w-[min(90vw,920px)]"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
            initial={reduceMotion ? false : { opacity: 0.9, y: 40 }}
            animate={{ opacity: 1, y: 0, x: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: 24 }}
            transition={{ duration, ease: 'easeOut' }}
            data-testid="bb-v3-analysis-drawer"
          >
            <div className="flex justify-center pt-2 md:hidden" aria-hidden>
              <span className="h-1 w-10 rounded-full bg-slate-300" />
            </div>

            <div className="sticky top-0 z-10 flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
              <div className="min-w-0 flex-1">
                <h2 id={titleId} className="text-base font-semibold text-slate-900">
                  Analisi manuale
                </h2>
                <p className="mt-0.5 truncate text-sm font-medium text-slate-800">
                  {fixture.home.name ?? 'Casa'} – {fixture.away.name ?? 'Ospite'}
                </p>
                <p className="mt-1 truncate text-xs text-slate-500">
                  {[fixture.country, fixture.league].filter(Boolean).join(' · ') || '—'}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  <span>{formatKickoffDateTime(fixture.kickoff)}</span>
                  {status ? (
                    <span className="font-semibold uppercase tracking-wide text-slate-500">{status}</span>
                  ) : null}
                </div>
              </div>
              <button ref={closeRef} type="button" className={bbSecondaryBtn} onClick={onClose}>
                Chiudi
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
              <div className="grid gap-4 md:grid-cols-2">
                <Section title="Match / risultato" testId="bb-v3-drawer-score">
                  <p className="text-2xl font-bold tabular-nums text-slate-900">
                    {score ? pair(score.home, score.away) : '—'}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    PT: {score ? pair(score.halftime_home, score.halftime_away) : '—'} · Finale:{' '}
                    {fixture.match_status === 'finished' && score ? pair(score.home, score.away) : '—'}
                  </p>
                </Section>

                <Section
                  title={`Predizione · ${TAB_TITLE[tab]}`}
                  testId="bb-v3-drawer-prediction"
                  className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xl font-semibold text-slate-900">{op.label}</span>
                    <OutcomeBadge won={op.won} />
                    {op.key === opportunities[0]?.key ? (
                      <span className={`${bbBadge} border-emerald-200 bg-white text-emerald-800`}>In evidenza</span>
                    ) : null}
                  </div>
                  {relation ? <p className="mt-1 text-sm text-slate-600">{relation}</p> : null}
                </Section>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Section title="Indice">
                  <PurchasabilityScoreRing
                    score={op.score}
                    classLabel={op.score != null ? indexClassLabel(op.score) : null}
                    size="md"
                    title={TAB_TITLE[tab]}
                    unavailableMessage="Indice non disponibile su questo mercato"
                    testId="bb-v3-drawer-ring"
                  />
                  {tab === 'combo' ? (
                    <p className="mt-1 text-xs text-slate-500">
                      V2.5 {op.scoreV25 != null ? Math.round(op.scoreV25) : '—'} · V3{' '}
                      {op.scoreV3 != null ? Math.round(op.scoreV3) : '—'}
                    </p>
                  ) : null}
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-slate-500">Vince (stima moduli)</dt>
                      <dd className="font-semibold tabular-nums">{fmtProb(op.probability)}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Frequenza normale</dt>
                      <dd className="font-semibold tabular-nums">{fmtProb(op.baseRate)}</dd>
                    </div>
                  </dl>
                </Section>

                <Section title="Quota">
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-slate-500">Bet365</dt>
                      <dd className="font-semibold tabular-nums">{fmtQuota(op.quota)}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Quota minima</dt>
                      <dd className="font-semibold tabular-nums">{fmtQuota(op.minQuota)}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-slate-500">Giocabile</dt>
                      <dd className="font-semibold">{op.playable ? 'Sì (quota da 1,50 in su)' : 'No'}</dd>
                    </div>
                  </dl>
                </Section>
              </div>

              {opportunities.length > 1 ? (
                <Section title={`Opportunità della partita · ${opportunities.length}`} testId="bb-v3-drawer-others">
                  <div className="flex flex-wrap gap-2">
                    {opportunities.map((o) => (
                      <button
                        key={o.key}
                        type="button"
                        aria-pressed={o.key === op.key}
                        className={`rounded-lg border px-3 py-1.5 text-left text-sm transition ${
                          o.key === op.key
                            ? 'border-slate-800 bg-slate-800 text-white'
                            : 'border-slate-200 bg-white text-slate-800 hover:bg-slate-50'
                        }`}
                        onClick={() => setPickedKey(o.key)}
                      >
                        <span className="font-semibold">{o.label}</span>
                        <span className="ml-2 tabular-nums opacity-80">
                          {o.score != null ? `${Math.round(o.score)}/100` : '—'}
                        </span>
                      </button>
                    ))}
                  </div>
                </Section>
              ) : null}

              <BetBuilderResultTechnicalAnalysis contextState={contextState} onRetry={retry} />

              <div className="flex justify-end">
                <Link to={todayHref} className={bbSecondaryBtn}>
                  Apri in Cecchino Today →
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
