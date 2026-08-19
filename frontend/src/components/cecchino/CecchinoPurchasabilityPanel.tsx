import { useCallback, useId, useMemo, useState } from 'react'
import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import { getPurchasabilityAuditExport } from '../../lib/cecchinoTodayApi'
import { bbSecondaryBtn } from '../bet-builder/betBuilderStyles'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { CecchinoPurchasabilityDetailPanel } from './CecchinoPurchasabilityDetailPanel'
import { CecchinoPurchasabilitySelector } from './CecchinoPurchasabilitySelector'
import {
  defaultSelectedMarketKey,
  getPurchasabilityFormulaShortLabel,
  getPurchasabilityFriendlyVersionLabel,
  listActivePurchasabilityMarkets,
} from './cecchinoPurchasabilityUiUtils'

export type CecchinoPurchasabilityPanelProps = {
  formulaVersion?: string | null
  candidateName?: string | null
  candidateVersion?: string | null
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

function PurchasabilityPanelTitle({
  formulaVersion,
  candidateName,
  candidateVersion,
}: {
  formulaVersion?: string | null
  candidateName?: string | null
  candidateVersion?: string | null
}) {
  const friendlyLabel = getPurchasabilityFriendlyVersionLabel({
    candidateName,
    candidateVersion,
    formulaVersion,
  })
  const shortLabel = getPurchasabilityFormulaShortLabel(formulaVersion)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold tracking-wide text-slate-800">Acquistabilità</h3>
        <span
          data-testid="purch-version-badge"
          className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-800 ring-1 ring-indigo-200"
        >
          {friendlyLabel}
        </span>
      </div>
      {shortLabel ? (
        <p
          data-testid="purch-formula-short-label"
          className="mt-0.5 text-xs text-slate-500"
        >
          {shortLabel}
        </p>
      ) : null}
    </div>
  )
}

export function CecchinoPurchasabilityPanel({
  formulaVersion,
  candidateName,
  candidateVersion,
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
        data-version={formulaVersion ?? undefined}
      >
        <PurchasabilityPanelTitle
          formulaVersion={formulaVersion}
          candidateName={candidateName}
          candidateVersion={candidateVersion}
        />
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
      data-version={formulaVersion ?? undefined}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <PurchasabilityPanelTitle
          formulaVersion={formulaVersion}
          candidateName={candidateName}
          candidateVersion={candidateVersion}
        />
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
