import { useEffect, useMemo, useState } from 'react'
import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import {
  getPurchasabilityEmpirical,
  type EmpiricalPurchasabilityItem,
} from '../../lib/cecchinoKpiSignalsApi'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { partitionTodayDetailWarnings } from '../../lib/cecchinoTodayApi'
import { CecchinoSignalsCard } from './CecchinoSignalsCard'
import { CecchinoTodayDetailHeader } from './CecchinoTodayDetailHeader'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import { CecchinoBalanceV5PreviewPanel } from './CecchinoBalanceV5PreviewPanel'
import { CecchinoGoalIntensityAnalysisPanel } from './CecchinoGoalIntensityAnalysisPanel'
import { CecchinoGoalIntensityV5PreviewPanel } from './CecchinoGoalIntensityV5PreviewPanel'
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

function mapPurchasabilityForFixture(
  items: Record<string, EmpiricalPurchasabilityItem>,
  todayFixtureId: number | null | undefined,
): Record<string, EmpiricalPurchasabilityItem> {
  const byMarket: Record<string, EmpiricalPurchasabilityItem> = {}
  for (const item of Object.values(items)) {
    if (
      todayFixtureId != null &&
      item.today_fixture_id != null &&
      Number(item.today_fixture_id) !== Number(todayFixtureId)
    ) {
      continue
    }
    const sel = item.selection
    if (sel) byMarket[sel] = item
  }
  return byMarket
}

export function CecchinoTodayDetailPanel({ detail, loading }: Props) {
  const [empByMarket, setEmpByMarket] = useState<Record<string, EmpiricalPurchasabilityItem>>({})
  const [empLoading, setEmpLoading] = useState(false)
  const [empError, setEmpError] = useState<string | null>(null)

  const scanDate = detail.scan_date
  const competitionId = detail.competition_id
  const todayFixtureId = detail.today_fixture_id ?? detail.id
  const hasKpi = Boolean(detail.kpi_panel_v2 ?? detail.kpi_panel)
  const canFetch = hasKpi && Boolean(scanDate) && detail.status === 'ok'

  useEffect(() => {
    if (!canFetch || !scanDate) return
    let cancelled = false
    void (async () => {
      setEmpLoading(true)
      setEmpError(null)
      try {
        const res = await getPurchasabilityEmpirical({
          date_from: scanDate,
          date_to: scanDate,
          competition_id: competitionId ?? null,
        })
        if (cancelled) return
        setEmpByMarket(mapPurchasabilityForFixture(res.items || {}, todayFixtureId))
      } catch {
        if (cancelled) return
        setEmpByMarket({})
        setEmpError('Acquistabilità non disponibile')
      } finally {
        if (!cancelled) setEmpLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [canFetch, scanDate, competitionId, todayFixtureId])

  const empMemo = useMemo(
    () => (canFetch ? empByMarket : {}),
    [canFetch, empByMarket],
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

      {(detail.kpi_panel_v2 ?? detail.kpi_panel) && (
        <CecchinoTodayKpiPanel
          panel={(detail.kpi_panel_v2 ?? detail.kpi_panel)!}
          bookmakerStatus={(detail.kpi_panel_v2 ?? detail.kpi_panel)?.bookmaker_status}
          purchasabilityByMarketKey={empMemo}
          purchasabilityLoading={empLoading}
          purchasabilityError={empError}
        />
      )}

      <CecchinoTodayPicchettiDebugPanel
        todayFixtureId={detail.today_fixture_id ?? detail.id}
        providerFixtureId={detail.provider_fixture_id}
        summary={detail.picchetti_debug_summary}
        kpiPanel={detail.kpi_panel_v2 ?? detail.kpi_panel}
      />

      <CecchinoBalanceV5PreviewPanel
        preview={detail.balance_v5 ?? detail.balance_v5_preview}
        identityConsistency={detail.fixture_identity_consistency}
      />

      <CecchinoGoalIntensityAnalysisPanel goalIntensityAnalysis={detail.goal_intensity_analysis} />

      <CecchinoGoalIntensityV5PreviewPanel preview={detail.goal_intensity_v5_preview} />

      <CecchinoExpectedGoalEngineDiagnosticsPanel
        diagnostics={detail.expected_goal_engine_diagnostics}
        todayFixtureId={detail.today_fixture_id ?? detail.id}
      />

      {signals && (
        <CecchinoSignalsCard
          matrix={signals}
          scanDate={detail.scan_date}
          todayFixtureId={detail.today_fixture_id ?? detail.id}
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
