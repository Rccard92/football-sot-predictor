import { useCallback, useId, useMemo, useState } from 'react'
import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import { getPurchasabilityAuditExport } from '../../lib/cecchinoTodayApi'
import { bbSecondaryBtn } from '../bet-builder/betBuilderStyles'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { CecchinoPurchasabilityDetailPanel } from './CecchinoPurchasabilityDetailPanel'
import { CecchinoPurchasabilitySelector } from './CecchinoPurchasabilitySelector'
import {
  defaultSelectedMarketKey,
  listActivePurchasabilityMarkets,
} from './cecchinoPurchasabilityUiUtils'

export type CecchinoPurchasabilityPanelProps = {
  version: string
  itemsByMarket: Record<string, CecchinoPurchasabilityV31Item>
  snapshotAvailable: boolean
  todayFixtureId?: number
  providerFixtureId?: number | null
}

function downloadAuditBlob(data: unknown, fixtureId: number) {
  const ts = new Date().toISOString().replace(/[:.]/g, '-')
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `purchasability-audit-${fixtureId}-${ts}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function CecchinoPurchasabilityPanel({
  version,
  itemsByMarket,
  snapshotAvailable,
  todayFixtureId,
  providerFixtureId,
}: CecchinoPurchasabilityPanelProps) {
  const panelId = useId()
  const activeItems = useMemo(
    () => listActivePurchasabilityMarkets(itemsByMarket),
    [itemsByMarket],
  )
  const defaultKey = useMemo(() => defaultSelectedMarketKey(itemsByMarket), [itemsByMarket])
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(defaultKey)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)

  const effectiveSelected =
    selectedMarketKey && activeItems.some((i) => i.market_key === selectedMarketKey)
      ? selectedMarketKey
      : defaultKey

  const selectedItem = effectiveSelected ? itemsByMarket[effectiveSelected] : undefined

  const handleDownloadAudit = useCallback(async () => {
    if (todayFixtureId == null) return
    setAuditLoading(true)
    setAuditError(null)
    try {
      const data = await getPurchasabilityAuditExport(todayFixtureId)
      downloadAuditBlob(data, providerFixtureId ?? todayFixtureId)
    } catch {
      setAuditError('Impossibile generare l\'audit Acquistabilità.')
    } finally {
      setAuditLoading(false)
    }
  }, [todayFixtureId, providerFixtureId])

  if (!snapshotAvailable || activeItems.length === 0) {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-panel"
        data-empty="true"
      >
        <h3 className="text-sm font-bold tracking-wide text-slate-800">Acquistabilità</h3>
        <p className="mt-2 text-sm text-slate-600">
          Nessuna opportunità attiva per questa partita.
        </p>
      </section>
    )
  }

  return (
    <section
      className={`${todayCard} ${todayCardPadding} space-y-4`}
      data-testid="cecchino-purchasability-panel"
      data-version={version}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-bold tracking-wide text-slate-800">Acquistabilità</h3>
        {todayFixtureId != null ? (
          <button
            type="button"
            className={bbSecondaryBtn}
            disabled={auditLoading}
            onClick={() => void handleDownloadAudit()}
            data-testid="purch-audit-download-btn"
          >
            {auditLoading ? 'Generazione…' : 'Scarica audit Acquistabilità'}
          </button>
        ) : null}
      </div>
      {auditError ? (
        <p className="text-sm text-red-700" role="alert">
          {auditError}
        </p>
      ) : null}

      <CecchinoPurchasabilitySelector
        items={activeItems}
        selectedMarketKey={effectiveSelected ?? activeItems[0].market_key}
        onSelect={setSelectedMarketKey}
        panelId={panelId}
      />

      {selectedItem ? (
        <CecchinoPurchasabilityDetailPanel item={selectedItem} panelId={panelId} />
      ) : null}
    </section>
  )
}
