import { useEffect, useId, useMemo, useState } from 'react'
import type {
  CecchinoPurchasabilityV36SnapshotStatus,
  V36Item,
  V36Snapshot,
} from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { CecchinoPurchasabilityV36DetailPanel } from './CecchinoPurchasabilityV36DetailPanel'
import { CecchinoPurchasabilityV36MarketSelector } from './CecchinoPurchasabilityV36MarketSelector'
import {
  countV36ScoreMarkets,
  defaultV36SelectedMarketKey,
  listScoredV36Markets,
} from './cecchinoPurchasabilityV36UiUtils'

export type CecchinoPurchasabilityV36PanelProps = {
  snapshot: V36Snapshot | null | undefined
  snapshotStatus: CecchinoPurchasabilityV36SnapshotStatus | null | undefined
  snapshotReason?: string | null
  itemsByMarket: Record<string, V36Item>
  todayFixtureId?: number
  providerFixtureId?: number | null
  /** Mercati indicati dai pattern con quota accesi. */
  patternMarkets?: string[]
}

function V36PanelHeader() {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold tracking-wide text-slate-800">
          Indice di Acquistabilità V3.6
        </h3>
        <span
          data-testid="v36-version-badge"
          className="inline-flex items-center rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white"
        >
          V3.6
        </span>
        <span
          data-testid="v36-structural-badge"
          className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-900 ring-1 ring-emerald-200"
        >
          STRUCTURAL
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500" data-testid="v36-header-disclaimer">
        Indicatore strutturale pre-match su scala 0–100. Non rappresenta una probabilità certa di
        vittoria.
      </p>
    </div>
  )
}

export function CecchinoPurchasabilityV36Panel({
  snapshot,
  snapshotStatus,
  snapshotReason,
  itemsByMarket,
  patternMarkets,
}: CecchinoPurchasabilityV36PanelProps) {
  const panelId = useId()
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)

  const scoredItems = useMemo(() => listScoredV36Markets(itemsByMarket), [itemsByMarket])
  const defaultMarketKey = useMemo(
    () => defaultV36SelectedMarketKey(itemsByMarket),
    [itemsByMarket],
  )
  const scoreCount = useMemo(() => countV36ScoreMarkets(itemsByMarket), [itemsByMarket])

  useEffect(() => {
    setSelectedMarketKey((prev) => {
      if (prev && scoredItems.some((i) => i.market_key === prev)) return prev
      return defaultV36SelectedMarketKey(itemsByMarket)
    })
  }, [scoredItems, itemsByMarket])

  const effectiveMarketKey =
    selectedMarketKey && scoredItems.some((i) => i.market_key === selectedMarketKey)
      ? selectedMarketKey
      : defaultMarketKey

  const selectedItem = effectiveMarketKey ? itemsByMarket[effectiveMarketKey] : undefined

  if (snapshotStatus === 'present_but_invalid') {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v36-panel"
        data-status="present_but_invalid"
      >
        <V36PanelHeader />
        <p className="mt-3 text-sm font-medium text-amber-800" role="alert" data-testid="v36-absent-message">
          Indice V3.6 non disponibile
        </p>
        <details className="mt-2 text-xs text-slate-500" data-testid="v36-invalid-diagnostics">
          <summary className="cursor-pointer">Dettaglio diagnostico</summary>
          <p className="mt-1">{snapshotReason ?? 'invalid_snapshot'}</p>
        </details>
      </section>
    )
  }

  if (snapshotStatus === 'absent' || !snapshot) {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v36-panel"
        data-status="absent"
      >
        <V36PanelHeader />
        <p className="mt-3 text-sm font-medium text-slate-700" data-testid="v36-absent-message">
          Indice V3.6 non disponibile
        </p>
      </section>
    )
  }

  if (scoreCount === 0) {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v36-panel"
        data-status="valid-no-score"
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <V36PanelHeader />
        </div>
        <p className="mt-3 text-sm text-slate-600">
          Nessun mercato valutabile nello snapshot V3.6.
        </p>
      </section>
    )
  }

  return (
    <section
      className={`${todayCard} ${todayCardPadding} space-y-4`}
      data-testid="cecchino-purchasability-v36-panel"
      data-status="valid"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <V36PanelHeader />
      </div>

      <CecchinoPurchasabilityV36MarketSelector
        items={scoredItems}
        selectedMarketKey={effectiveMarketKey ?? scoredItems[0]?.market_key ?? 'HOME'}
        onSelect={setSelectedMarketKey}
        panelId={panelId}
        patternMarkets={patternMarkets}
      />

      {selectedItem && selectedItem.status === 'score' ? (
        <CecchinoPurchasabilityV36DetailPanel
          item={selectedItem}
          snapshot={snapshot}
          panelId={panelId}
        />
      ) : null}
    </section>
  )
}
