import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import type {
  CecchinoPurchasabilityV35CandidateKey,
  CecchinoPurchasabilityV35Item,
  CecchinoPurchasabilityV35Snapshot,
  CecchinoPurchasabilityV35SnapshotStatus,
} from '../../lib/cecchinoTodayApi'
import { getPurchasabilityV35AuditExport } from '../../lib/cecchinoTodayApi'
import { bbSecondaryBtn } from '../bet-builder/betBuilderStyles'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'
import { CecchinoPurchasabilityV35CandidateSelector } from './CecchinoPurchasabilityV35CandidateSelector'
import { CecchinoPurchasabilityV35DetailPanel } from './CecchinoPurchasabilityV35DetailPanel'
import { CecchinoPurchasabilityV35MarketSelector } from './CecchinoPurchasabilityV35MarketSelector'
import {
  countV35ScoreMarkets,
  defaultV35SelectedMarketKey,
  listActiveV35Markets,
} from './cecchinoPurchasabilityV35UiUtils'

export type CecchinoPurchasabilityV35PanelProps = {
  snapshot: CecchinoPurchasabilityV35Snapshot | null | undefined
  snapshotStatus: CecchinoPurchasabilityV35SnapshotStatus | null | undefined
  snapshotReason?: string | null
  itemsByMarket: Record<string, CecchinoPurchasabilityV35Item>
  todayFixtureId?: number
  providerFixtureId?: number | null
}

function downloadV35AuditBlob(data: unknown, providerFixtureId: number) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `purchasability-v35-audit-${providerFixtureId}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function V35PanelHeader() {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold tracking-wide text-slate-800">Acquistabilità V3.5</h3>
        <span
          data-testid="v35-live-shadow-badge"
          className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-900 ring-1 ring-violet-200"
        >
          LIVE SHADOW
        </span>
        <span
          data-testid="v35-formula-badge"
          className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700 ring-1 ring-slate-200"
        >
          structural_v1
        </span>
      </div>
      <p className="mt-0.5 text-xs text-slate-500">Esperimento pre-match — non operativo</p>
    </div>
  )
}

export function CecchinoPurchasabilityV35Panel({
  snapshot,
  snapshotStatus,
  snapshotReason,
  itemsByMarket,
  todayFixtureId,
  providerFixtureId,
}: CecchinoPurchasabilityV35PanelProps) {
  const panelId = useId()
  const [selectedCandidate, setSelectedCandidate] =
    useState<CecchinoPurchasabilityV35CandidateKey>('A')
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)

  const activeItems = useMemo(
    () => listActiveV35Markets(itemsByMarket, selectedCandidate),
    [itemsByMarket, selectedCandidate],
  )

  const defaultMarketKey = useMemo(
    () => defaultV35SelectedMarketKey(itemsByMarket, 'A'),
    [itemsByMarket],
  )

  useEffect(() => {
    setSelectedMarketKey((prev) => {
      if (prev && activeItems.some((i) => i.market_key === prev)) return prev
      return defaultV35SelectedMarketKey(itemsByMarket, selectedCandidate)
    })
  }, [activeItems, itemsByMarket, selectedCandidate])

  const effectiveMarketKey =
    selectedMarketKey && activeItems.some((i) => i.market_key === selectedMarketKey)
      ? selectedMarketKey
      : defaultV35SelectedMarketKey(itemsByMarket, selectedCandidate)

  const selectedItem = effectiveMarketKey ? itemsByMarket[effectiveMarketKey] : undefined
  const scoreCount = useMemo(() => countV35ScoreMarkets(itemsByMarket), [itemsByMarket])

  const handleDownloadAudit = useCallback(async () => {
    if (todayFixtureId == null) return
    setAuditLoading(true)
    setAuditError(null)
    try {
      const data = await getPurchasabilityV35AuditExport(todayFixtureId)
      downloadV35AuditBlob(data, providerFixtureId ?? todayFixtureId)
    } catch {
      setAuditError('Impossibile scaricare l\'audit V3.5.')
    } finally {
      setAuditLoading(false)
    }
  }, [todayFixtureId, providerFixtureId])

  if (snapshotStatus === 'invalid') {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v35-panel"
        data-status="invalid"
      >
        <V35PanelHeader />
        <p className="mt-3 text-sm font-medium text-amber-800" role="alert">
          Snapshot V3.5 non valido — escluso dall&apos;esperimento.
        </p>
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer">Dettaglio diagnostico</summary>
          <p className="mt-1">{snapshotReason ?? 'invalid_snapshot'}</p>
        </details>
      </section>
    )
  }

  if (snapshotStatus === 'unavailable' || !snapshot) {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v35-panel"
        data-status="unavailable"
      >
        <V35PanelHeader />
        <p className="mt-3 text-sm font-medium text-slate-700">
          Snapshot V3.5 non disponibile per questa partita.
        </p>
        <p className="mt-1 text-xs text-slate-500">
          La V3.5 viene registrata solo durante una scansione live pre-match.
        </p>
      </section>
    )
  }

  if (scoreCount === 0) {
    return (
      <section
        className={`${todayCard} ${todayCardPadding}`}
        data-testid="cecchino-purchasability-v35-panel"
        data-status="valid-no-score"
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <V35PanelHeader />
          {todayFixtureId != null ? (
            <button
              type="button"
              className={bbSecondaryBtn}
              disabled={auditLoading}
              onClick={() => void handleDownloadAudit()}
              data-testid="v35-audit-download-btn"
            >
              {auditLoading ? 'Download…' : 'Scarica audit V3.5'}
            </button>
          ) : null}
        </div>
        {auditError ? (
          <p className="text-sm text-red-700" role="alert">
            {auditError}
          </p>
        ) : null}
        <p className="mt-3 text-sm text-slate-600">
          Nessun mercato supera il gate V3.5 in questo snapshot.
        </p>
      </section>
    )
  }

  return (
    <section
      className={`${todayCard} ${todayCardPadding} space-y-4`}
      data-testid="cecchino-purchasability-v35-panel"
      data-status="valid"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <V35PanelHeader />
        {todayFixtureId != null ? (
          <button
            type="button"
            className={bbSecondaryBtn}
            disabled={auditLoading}
            onClick={() => void handleDownloadAudit()}
            data-testid="v35-audit-download-btn"
          >
            {auditLoading ? 'Download…' : 'Scarica audit V3.5'}
          </button>
        ) : null}
      </div>
      {auditError ? (
        <p className="text-sm text-red-700" role="alert">
          {auditError}
        </p>
      ) : null}

      <CecchinoPurchasabilityV35CandidateSelector
        snapshot={snapshot}
        selectedCandidate={selectedCandidate}
        onSelect={setSelectedCandidate}
        panelId={panelId}
      />

      <CecchinoPurchasabilityV35MarketSelector
        items={activeItems}
        selectedMarketKey={effectiveMarketKey ?? activeItems[0]?.market_key ?? defaultMarketKey ?? 'HOME'}
        selectedCandidate={selectedCandidate}
        onSelect={setSelectedMarketKey}
        panelId={panelId}
      />

      {selectedItem ? (
        <CecchinoPurchasabilityV35DetailPanel
          item={selectedItem}
          snapshot={snapshot}
          selectedCandidate={selectedCandidate}
          panelId={panelId}
        />
      ) : null}
    </section>
  )
}
