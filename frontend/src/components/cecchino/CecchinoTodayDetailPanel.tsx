import { useMemo } from 'react'
import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import { useHistoricalReliabilityForFixture } from '../../hooks/useHistoricalReliabilityForFixture'
import type {
  CecchinoTodayDetailResponse,
} from '../../lib/cecchinoTodayApi'
import { indexPurchasabilityV31ByMarketKey, indexPurchasabilityV35ByMarketKey, partitionTodayDetailWarnings } from '../../lib/cecchinoTodayApi'
import { CecchinoSignalsCard } from './CecchinoSignalsCard'
import { CecchinoTodayDetailHeader } from './CecchinoTodayDetailHeader'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import { CecchinoPurchasabilityPanel } from './CecchinoPurchasabilityPanel'
import { CecchinoPurchasabilityV35Panel } from './CecchinoPurchasabilityV35Panel'
import { CecchinoBalanceV5Panel } from './CecchinoBalanceV5Panel'
import { CecchinoGoalIntensityV5Panel } from './CecchinoGoalIntensityV5Panel'
import { CecchinoExpectedGoalEngineDiagnosticsPanel } from './CecchinoExpectedGoalEngineDiagnosticsPanel'
import { CecchinoTodayPicchettiDebugPanel } from './CecchinoTodayPicchettiDebugPanel'
import { todayCard, todayCardPadding, todaySkeleton } from './cecchinoTodayStyles'

type Props = {
  detail: CecchinoTodayDetailResponse
  loading?: boolean
}

export function CecchinoTodayDetailPlaceholder() {
  return (
    <div className={`${todayCard} ${todayCardPadding} flex min-h-[320px] flex-col items-center justify-center text-center`}>
      <p className="text-sm font-medium text-slate-700">Seleziona una partita dalla lista</p>
      <p className="mt-2 max-w-xs text-xs text-slate-500">
        Il dettaglio con Pannello KPI e segnali Cecchino apparirà qui.
      </p>
    </div>
  )
}

export function CecchinoTodayDetailSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Caricamento dettaglio">
      <div className={`${todaySkeleton} h-36 w-full rounded-xl`} />
      <div className={`${todaySkeleton} h-64 w-full rounded-xl`} />
      <div className={`${todaySkeleton} h-48 w-full rounded-xl`} />
    </div>
  )
}

export function CecchinoTodayDetailPanel({ detail, loading }: Props) {
  const scanDate = detail.scan_date
  const competitionId = detail.competition_id
  const todayFixtureId = detail.today_fixture_id ?? detail.id
  const hasKpi = Boolean(detail.kpi_panel_v2 ?? detail.kpi_panel)
  const canFetch = hasKpi && Boolean(scanDate) && detail.status === 'ok'

  const {
    byMarketKey: hrMemo,
    loading: hrLoading,
    error: hrError,
  } = useHistoricalReliabilityForFixture({
    scanDate,
    competitionId,
    todayFixtureId,
    enabled: canFetch,
  })

  const purchasabilityV31ByMarketKey = useMemo(
    () => indexPurchasabilityV31ByMarketKey(detail.purchasability_preview_v31),
    [detail.purchasability_preview_v31],
  )
  const purchasabilityV31SnapshotAvailable =
    detail.purchasability_preview_v31 != null &&
    detail.purchasability_preview_v31.status !== 'unavailable'

  const purchasabilityV35ByMarketKey = useMemo(
    () => indexPurchasabilityV35ByMarketKey(detail.purchasability_preview_v35),
    [detail.purchasability_preview_v35],
  )

  if (loading) {
    return <CecchinoTodayDetailSkeleton />
  }

  if (detail.status !== 'ok') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        {detail.message ?? 'Dettaglio non disponibile.'}
      </div>
    )
  }

  const output = detail.cecchino_output
  const signals = (detail.signals_matrix ?? output?.signals_matrix) as
    | CecchinoSignalsMatrix
    | undefined
  const { notes: dataNotes, blocking: blockingWarnings } = partitionTodayDetailWarnings(detail.warnings)

  return (
    <div className="space-y-5">
      <CecchinoTodayDetailHeader detail={detail} />

      <CecchinoPurchasabilityPanel
        key={todayFixtureId}
        formulaVersion={detail.purchasability_preview_v31?.formula_version}
        candidateName={detail.purchasability_preview_v31?.candidate_name}
        candidateVersion={detail.purchasability_preview_v31?.candidate_version}
        itemsByMarket={purchasabilityV31ByMarketKey}
        snapshotAvailable={purchasabilityV31SnapshotAvailable}
        todayFixtureId={todayFixtureId}
        providerFixtureId={detail.provider_fixture_id}
      />

      <CecchinoPurchasabilityV35Panel
        key={`v35-${todayFixtureId}`}
        snapshot={detail.purchasability_preview_v35}
        snapshotStatus={detail.purchasability_v35_snapshot_status ?? 'unavailable'}
        snapshotReason={detail.purchasability_v35_snapshot_reason}
        itemsByMarket={purchasabilityV35ByMarketKey}
        todayFixtureId={todayFixtureId}
        providerFixtureId={detail.provider_fixture_id}
      />

      {(detail.kpi_panel_v2 ?? detail.kpi_panel) && (
        <CecchinoTodayKpiPanel
          panel={(detail.kpi_panel_v2 ?? detail.kpi_panel)!}
          bookmakerStatus={(detail.kpi_panel_v2 ?? detail.kpi_panel)?.bookmaker_status}
          historicalReliabilityByMarketKey={hrMemo}
          historicalReliabilityLoading={hrLoading}
          historicalReliabilityError={hrError}
          todayFixtureId={detail.today_fixture_id ?? detail.id}
          providerFixtureId={detail.provider_fixture_id}
        />
      )}

      <CecchinoTodayPicchettiDebugPanel
        todayFixtureId={detail.today_fixture_id ?? detail.id}
        providerFixtureId={detail.provider_fixture_id}
        summary={detail.picchetti_debug_summary}
        kpiPanel={detail.kpi_panel_v2 ?? detail.kpi_panel}
      />

      <CecchinoBalanceV5Panel
        balance={detail.balance_v5}
        identityConsistency={detail.fixture_identity_consistency}
        snapshotMeta={detail.balance_v5_snapshot_meta}
        todayFixtureId={detail.today_fixture_id ?? detail.id}
        providerFixtureId={detail.provider_fixture_id}
      />

      <CecchinoGoalIntensityV5Panel
        goalIntensity={detail.goal_intensity_v5 ?? detail.goal_intensity_v5_preview}
        todayFixtureId={detail.today_fixture_id ?? detail.id}
        providerFixtureId={detail.provider_fixture_id}
      />

      <CecchinoExpectedGoalEngineDiagnosticsPanel
        diagnostics={detail.expected_goal_engine_diagnostics}
        todayFixtureId={detail.today_fixture_id ?? detail.id}
      />

      {signals && (
        <CecchinoSignalsCard
          matrix={signals}
          scanDate={detail.scan_date}
          todayFixtureId={detail.today_fixture_id ?? detail.id}
          providerFixtureId={detail.provider_fixture_id}
          signalContract={detail.signal_contract ?? null}
        />
      )}

      {(blockingWarnings.length > 0 || dataNotes.length > 0) && (
        <div className="space-y-2 text-xs">
          {blockingWarnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
              <ul className="list-disc pl-4">
                {blockingWarnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          {dataNotes.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-600">
              <ul className="list-disc pl-4">
                {dataNotes.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
