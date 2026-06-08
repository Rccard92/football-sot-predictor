import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { partitionTodayDetailWarnings } from '../../lib/cecchinoTodayApi'
import { CecchinoSignalsCard } from './CecchinoSignalsCard'
import { CecchinoTodayDetailHeader } from './CecchinoTodayDetailHeader'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
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
  const importInfo = (detail.stats_snapshot?.import_info as string[] | undefined) ?? []
  const { notes: dataNotes, blocking: blockingWarnings } = partitionTodayDetailWarnings(detail.warnings)

  return (
    <div className="space-y-5">
      <CecchinoTodayDetailHeader detail={detail} />

      {(detail.kpi_panel_v2 ?? detail.kpi_panel) && (
        <CecchinoTodayKpiPanel
          panel={(detail.kpi_panel_v2 ?? detail.kpi_panel)!}
          bookmakerStatus={(detail.kpi_panel_v2 ?? detail.kpi_panel)?.bookmaker_status}
        />
      )}

      <CecchinoTodayPicchettiDebugPanel
        todayFixtureId={detail.today_fixture_id ?? detail.id}
        providerFixtureId={detail.provider_fixture_id}
        summary={detail.picchetti_debug_summary}
        kpiPanel={detail.kpi_panel_v2 ?? detail.kpi_panel}
      />

      {signals && <CecchinoSignalsCard matrix={signals} />}

      {(importInfo.length > 0 || dataNotes.length > 0) && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Note dati</p>
          <ul className="mt-2 list-inside list-disc text-sm text-slate-700">
            {importInfo.map((info) => (
              <li key={info}>{info}</li>
            ))}
            {dataNotes.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {blockingWarnings.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">Avvisi</p>
          <ul className="mt-2 list-inside list-disc text-sm text-amber-900/90">
            {blockingWarnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
