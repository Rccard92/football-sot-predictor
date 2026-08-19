import { useState } from 'react'
import type { BetBuilderResultAnalysisContext } from '../../lib/cecchinoBetBuilderApi'
import type { AnalysisContextState } from '../../hooks/useBetBuilderResultAnalysisContext'
import { useHistoricalReliabilityForFixture } from '../../hooks/useHistoricalReliabilityForFixture'
import { CecchinoTodayKpiPanel } from '../cecchino/CecchinoTodayKpiPanel'
import { CecchinoBalanceV5Panel } from '../cecchino/CecchinoBalanceV5Panel'
import { CecchinoGoalIntensityV5Panel } from '../cecchino/CecchinoGoalIntensityV5Panel'
import { CecchinoSignalsCard } from '../cecchino/CecchinoSignalsCard'
import { bbSecondaryBtn } from './betBuilderStyles'

export type TechnicalAnalysisTab = 'kpi' | 'balance' | 'gi' | 'signals'

type Props = {
  contextState: AnalysisContextState
  onRetry: () => void
}

const TAB_LABELS: { id: TechnicalAnalysisTab; label: string }[] = [
  { id: 'kpi', label: 'Pannello KPI' },
  { id: 'balance', label: 'Equilibrio vs Squilibrio' },
  { id: 'gi', label: 'Intensità Goal' },
  { id: 'signals', label: 'Segnali Cecchino' },
]

function TechnicalSkeleton() {
  return (
    <div className="space-y-3" data-testid="technical-analysis-skeleton" aria-busy="true">
      <p className="text-sm text-slate-500">Caricamento analisi tecnica…</p>
      <div className="h-48 animate-pulse rounded-xl bg-slate-200/70" />
      <div className="h-32 animate-pulse rounded-xl bg-slate-200/60" />
    </div>
  )
}

function tabButtonClass(active: boolean): string {
  return [
    'shrink-0 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors',
    active
      ? 'border-slate-800 bg-slate-800 text-white'
      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
  ].join(' ')
}

function isModuleAvailable(
  tab: TechnicalAnalysisTab,
  context: BetBuilderResultAnalysisContext,
): boolean {
  switch (tab) {
    case 'kpi':
      return Boolean(context.kpi_panel)
    case 'balance':
      return Boolean(context.balance_v5)
    case 'gi':
      return Boolean(context.goal_intensity_v5)
    case 'signals':
      return Boolean(context.signals_matrix)
    default:
      return false
  }
}

function TechnicalPanelContent({
  tab,
  context,
}: {
  tab: TechnicalAnalysisTab
  context: BetBuilderResultAnalysisContext
}) {
  const fixture = context.fixture
  const todayFixtureId = fixture.today_fixture_id
  const providerFixtureId = fixture.provider_fixture_id
  const hasKpi = Boolean(context.kpi_panel)

  const hr = useHistoricalReliabilityForFixture({
    scanDate: fixture.scan_date,
    competitionId: fixture.competition_id,
    todayFixtureId,
    enabled: tab === 'kpi' && hasKpi,
  })

  if (tab === 'kpi') {
    if (!context.kpi_panel) {
      return <p className="text-sm text-slate-500">Pannello KPI non disponibile.</p>
    }
    return (
      <div className="min-w-0 overflow-x-auto" data-testid="drawer-kpi-panel">
        <CecchinoTodayKpiPanel
          panel={context.kpi_panel}
          bookmakerStatus={context.kpi_panel.bookmaker_status}
          historicalReliabilityByMarketKey={hr.byMarketKey}
          historicalReliabilityLoading={hr.loading}
          historicalReliabilityError={hr.error}
          todayFixtureId={todayFixtureId}
          providerFixtureId={providerFixtureId}
        />
      </div>
    )
  }

  if (tab === 'balance') {
    return (
      <div data-testid="drawer-balance-panel">
        <CecchinoBalanceV5Panel
          balance={context.balance_v5}
          identityConsistency={context.fixture_identity_consistency}
          snapshotMeta={context.balance_v5_snapshot_meta}
          todayFixtureId={todayFixtureId}
          providerFixtureId={providerFixtureId}
        />
      </div>
    )
  }

  if (tab === 'gi') {
    return (
      <div data-testid="drawer-gi-panel">
        <CecchinoGoalIntensityV5Panel
          goalIntensity={context.goal_intensity_v5}
          todayFixtureId={todayFixtureId}
          providerFixtureId={providerFixtureId}
        />
      </div>
    )
  }

  if (!context.signals_matrix) {
    return (
      <p className="text-sm text-slate-500" data-testid="drawer-signals-unavailable">
        Segnali Cecchino non disponibili per questa partita.
      </p>
    )
  }

  return (
    <div data-testid="drawer-signals-panel">
      <CecchinoSignalsCard
        matrix={context.signals_matrix}
        scanDate={fixture.scan_date}
        todayFixtureId={todayFixtureId}
        providerFixtureId={providerFixtureId}
        signalContract={context.signal_contract ?? null}
      />
    </div>
  )
}

export function BetBuilderResultTechnicalAnalysis({ contextState, onRetry }: Props) {
  const [tab, setTab] = useState<TechnicalAnalysisTab>('kpi')

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3" data-testid="drawer-technical-analysis">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Analisi tecnica
      </h3>

      <div
        className="mt-3 flex gap-2 overflow-x-auto pb-1"
        role="tablist"
        aria-label="Analisi tecnica"
        data-testid="technical-analysis-tabs"
      >
        {TAB_LABELS.map(({ id, label }) => {
          const available =
            contextState.status === 'success' ? isModuleAvailable(id, contextState.data) : null
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={tabButtonClass(tab === id)}
              data-testid={`technical-tab-${id}`}
              onClick={() => setTab(id)}
            >
              <span className="inline-flex items-center gap-1.5">
                {label}
                {available === false ? (
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full bg-slate-300"
                    aria-hidden
                    data-testid={`technical-tab-${id}-unavailable`}
                  />
                ) : null}
              </span>
            </button>
          )
        })}
      </div>

      <div className="mt-4 min-w-0" role="tabpanel">
        {contextState.status === 'loading' || contextState.status === 'idle' ? (
          <TechnicalSkeleton />
        ) : null}

        {contextState.status === 'error' ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm" data-testid="technical-analysis-error">
            <p className="text-amber-900">Analisi tecnica non disponibile.</p>
            <button type="button" className={`${bbSecondaryBtn} mt-2`} onClick={onRetry} data-testid="technical-analysis-retry">
              Riprova
            </button>
          </div>
        ) : null}

        {contextState.status === 'success' ? (
          <TechnicalPanelContent tab={tab} context={contextState.data} />
        ) : null}
      </div>
    </section>
  )
}
