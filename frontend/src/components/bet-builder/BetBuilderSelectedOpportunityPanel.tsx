import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useId, useState } from 'react'
import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderContextBlock } from './BetBuilderContextBlock'
import { BetBuilderPurchasabilityRing } from './BetBuilderPurchasabilityRing'
import { BetBuilderSignalsBlock } from './BetBuilderSignalsBlock'
import {
  bbBadge,
  bbInEvidenzaBadge,
  bbMetricCell,
  bbSecondaryBtn,
} from './betBuilderStyles'
import type { BetBuilderViewMode } from './betBuilderUtils'
import { originBadgeLabel } from './betBuilderUtils'

type Props = {
  opportunity: BetBuilderOpportunity
  isPrimary: boolean
  viewMode: BetBuilderViewMode
  panelId: string
}

function originBadgeClass(origin: BetBuilderOpportunity['origin']): string {
  if (origin === 'price') return `${bbBadge} border-sky-200 bg-sky-50 text-sky-900`
  if (origin === 'signals') return `${bbBadge} border-violet-200 bg-violet-50 text-violet-900`
  return `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
}

function fmtEdge(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function fmtQuota(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(2)
}

export function BetBuilderSelectedOpportunityPanel({
  opportunity,
  isPrimary,
  viewMode,
  panelId,
}: Props) {
  const reduceMotion = useReducedMotion()
  const contextId = useId()
  const [contextOpen, setContextOpen] = useState(viewMode === 'analysis')
  const [prevViewMode, setPrevViewMode] = useState(viewMode)

  // Reset collapse quando cambia Compatta/Analisi (pattern React: adjust state on prop change).
  if (prevViewMode !== viewMode) {
    setPrevViewMode(viewMode)
    setContextOpen(viewMode === 'analysis')
  }

  const duration = reduceMotion ? 0 : 0.18
  const y = reduceMotion ? 0 : 5
  const price = opportunity.price_value
  const hasContext =
    opportunity.context_support.available ||
    opportunity.context_support.reason === 'no_validated_context_module'

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={opportunity.opportunity_key}
        id={panelId}
        role="tabpanel"
        aria-labelledby={`bb-tab-${opportunity.opportunity_key}`}
        initial={{ opacity: 0, y }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -y }}
        transition={{ duration, ease: 'easeOut' }}
        className="space-y-4 rounded-2xl border border-slate-200 bg-white p-3 sm:p-4"
        data-testid="bet-builder-selected-opportunity"
        data-opportunity-key={opportunity.opportunity_key}
        data-origin={opportunity.origin}
        data-market={opportunity.market.market_key}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">
                {opportunity.market.label}
              </h3>
              {isPrimary ? (
                <span className={bbInEvidenzaBadge} data-testid="in-evidenza-badge-panel">
                  In evidenza
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {opportunity.origin === 'price_and_signals' ? (
                <>
                  <span className={`${bbBadge} border-sky-200 bg-sky-50 text-sky-900`}>QUOTA</span>
                  <span className={`${bbBadge} border-violet-200 bg-violet-50 text-violet-900`}>
                    SEGNALI
                  </span>
                </>
              ) : (
                <span className={originBadgeClass(opportunity.origin)}>
                  {originBadgeLabel(opportunity.origin)}
                </span>
              )}
            </div>
          </div>
          {/* Slot riservato futuro CTA "+" BET-03 — non implementato */}
          <div
            className="hidden min-h-11 min-w-11 sm:block"
            aria-hidden
            data-testid="bet-builder-cart-slot"
          />
        </div>

        <div
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3"
          data-testid="bet-builder-core-metrics"
        >
          <div className={`${bbMetricCell} col-span-2 sm:col-span-1`}>
            <BetBuilderPurchasabilityRing
              purchasability={opportunity.purchasability_v31}
              size="md"
            />
          </div>

          <div className={bbMetricCell} aria-label="Quota Book e Cecchino">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Quota
            </p>
            {price.present ? (
              <span
                className={`${bbBadge} mt-1 border-emerald-200 bg-emerald-50 text-emerald-800`}
              >
                Valore quota
              </span>
            ) : (
              <p className="mt-1 text-xs text-slate-500">Nessun valore quota rilevato</p>
            )}
            <p className="mt-2 text-lg font-semibold tabular-nums text-slate-900">
              {fmtQuota(price.quota_book)}
            </p>
            <p className="text-xs text-slate-500">Book</p>
            <p className="mt-1 text-base font-semibold tabular-nums text-slate-800">
              {fmtQuota(price.quota_cecchino)}
              <span className="ml-1 text-xs font-medium text-slate-500">Cecchino</span>
            </p>
          </div>

          <div className={bbMetricCell} aria-label="Edge e Rating">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Edge
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
              {fmtEdge(price.edge_pct)}
            </p>
            <p className="mt-2 text-sm font-semibold tabular-nums text-slate-800">
              {price.rating != null ? price.rating : '—'}
              {price.rating_label ? (
                <span className="ml-1 text-xs font-medium text-slate-600">
                  · {price.rating_label}
                </span>
              ) : null}
            </p>
            <p className="text-xs text-slate-500">Rating</p>
          </div>

          <div className={bbMetricCell}>
            <BetBuilderSignalsBlock
              signals={opportunity.signals}
              marketKey={opportunity.market.market_key}
            />
          </div>
        </div>

        {hasContext ? (
          <div className="border-t border-slate-100 pt-3">
            <button
              type="button"
              className={`${bbSecondaryBtn} w-full sm:w-auto`}
              aria-expanded={contextOpen}
              aria-controls={contextId}
              data-testid="bet-builder-context-toggle"
              onClick={() => setContextOpen((v) => !v)}
            >
              {contextOpen ? 'Nascondi contesto analitico' : 'Contesto analitico'}
            </button>
            <AnimatePresence initial={false}>
              {contextOpen ? (
                <motion.div
                  id={contextId}
                  key="context"
                  initial={{ opacity: 0, height: reduceMotion ? 'auto' : 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: reduceMotion ? 'auto' : 0 }}
                  transition={{ duration }}
                  className="overflow-hidden"
                  data-testid="bet-builder-context-panel"
                >
                  <div className="pt-3">
                    <BetBuilderContextBlock
                      context={opportunity.context_support}
                      marketLabel={opportunity.market.label}
                    />
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        ) : null}
      </motion.div>
    </AnimatePresence>
  )
}
