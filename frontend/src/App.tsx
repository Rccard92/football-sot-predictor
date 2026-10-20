import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LegacyLabRedirect } from './components/module-monitoring/LegacyLabRedirect'
import { todaySkeleton } from './components/cecchino/cecchinoTodayStyles'
import { CecchinoTodayPage } from './pages/CecchinoTodayPage'

// La pagina di atterraggio (Cecchino Today) e il Layout restano nel bundle iniziale;
// le altre pagine si caricano solo quando si apre la loro rotta.
const Admin = lazy(() => import('./pages/Admin').then((m) => ({ default: m.Admin })))
const DataHealth = lazy(() =>
  import('./pages/DataHealth').then((m) => ({ default: m.DataHealth })),
)
const Changelog = lazy(() => import('./pages/Changelog').then((m) => ({ default: m.Changelog })))
const Bookmakers = lazy(() =>
  import('./pages/Bookmakers').then((m) => ({ default: m.Bookmakers })),
)
const CecchinoSignalsMonitoringPage = lazy(() =>
  import('./pages/CecchinoSignalsMonitoringPage').then((m) => ({
    default: m.CecchinoSignalsMonitoringPage,
  })),
)
const SegnaliKpiPage = lazy(() =>
  import('./pages/SegnaliKpiPage').then((m) => ({ default: m.SegnaliKpiPage })),
)
const MonitoraggioModuliPage = lazy(() =>
  import('./pages/MonitoraggioModuliPage').then((m) => ({ default: m.MonitoraggioModuliPage })),
)
const BetBuilderPage = lazy(() =>
  import('./pages/BetBuilderPage').then((m) => ({ default: m.BetBuilderPage })),
)
const BetBuilderV3Page = lazy(() =>
  import('./pages/BetBuilderV3Page').then((m) => ({ default: m.BetBuilderV3Page })),
)
const CecchinoLabPage = lazy(() =>
  import('./pages/CecchinoLabPage').then((m) => ({ default: m.CecchinoLabPage })),
)
const CecchinoLabPatternLabPage = lazy(() =>
  import('./pages/CecchinoLabPatternLabPage').then((m) => ({
    default: m.CecchinoLabPatternLabPage,
  })),
)
const CecchinoLabPurchasabilityReplayPage = lazy(() =>
  import('./pages/CecchinoLabPurchasabilityReplayPage').then((m) => ({
    default: m.CecchinoLabPurchasabilityReplayPage,
  })),
)
const CecchinoHomeWinsPage = lazy(() =>
  import('./pages/CecchinoHomeWinsPage').then((m) => ({ default: m.CecchinoHomeWinsPage })),
)
const RoadmapPage = lazy(() =>
  import('./pages/RoadmapPage').then((m) => ({ default: m.RoadmapPage })),
)
const ModelsGuidePage = lazy(() =>
  import('./pages/ModelsGuidePage').then((m) => ({ default: m.ModelsGuidePage })),
)
const MasterPatternPage = lazy(() =>
  import('./pages/MasterPatternPage').then((m) => ({ default: m.MasterPatternPage })),
)
const LiveObservationPage = lazy(() =>
  import('./pages/LiveObservationPage').then((m) => ({ default: m.LiveObservationPage })),
)
const CecchinoV4Page = lazy(() =>
  import('./pages/CecchinoV4Page').then((m) => ({ default: m.CecchinoV4Page })),
)

/** Segnaposto leggero mostrato mentre arriva il codice di una pagina. */
function RouteFallback() {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <span className="sr-only">Caricamento pagina…</span>
      <div className={`${todaySkeleton} h-10 w-64`} />
      <div className={`${todaySkeleton} h-32`} />
      <div className={`${todaySkeleton} h-64`} />
    </div>
  )
}

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteFallback />}>{children}</Suspense>
}

function RedirectHistoricalRunToPatternLab() {
  const { runId } = useParams()
  const qs = new URLSearchParams()
  qs.set('tab', 'pattern_lab')
  if (runId) qs.set('run_ids', runId)
  return <Navigate to={`/cecchino-lab?${qs.toString()}`} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<CecchinoTodayPage />} />
          <Route path="/cecchino" element={<Navigate to="/cecchino-today" replace />} />
          <Route path="/cecchino-today" element={<CecchinoTodayPage />} />
          <Route
            path="/cecchino-v4"
            element={
              <Suspense fallback={<p className="text-base text-slate-500">Carico Cecchino V4…</p>}>
                <CecchinoV4Page />
              </Suspense>
            }
          />
          <Route path="/bet-builder" element={<Page><BetBuilderPage /></Page>} />
          <Route path="/bet-builder-v3" element={<Page><BetBuilderV3Page /></Page>} />
          <Route path="/cecchino-lab" element={<Page><CecchinoLabPage /></Page>} />
          <Route path="/roadmap" element={<Page><RoadmapPage /></Page>} />
          <Route path="/guida-modelli" element={<Page><ModelsGuidePage /></Page>} />
          <Route path="/master-pattern" element={<Page><MasterPatternPage /></Page>} />
          <Route path="/osservazione-live" element={<Page><LiveObservationPage /></Page>} />
          <Route
            path="/cecchino-lab/pattern-lab"
            element={<Page><CecchinoLabPatternLabPage /></Page>}
          />
          <Route
            path="/cecchino-lab/historical-scans/:runId/kpi-signals"
            element={<RedirectHistoricalRunToPatternLab />}
          />
          <Route
            path="/cecchino-lab/historical-scans/:runId/signals-af"
            element={<RedirectHistoricalRunToPatternLab />}
          />
          <Route
            path="/cecchino-lab/historical-scans/:runId"
            element={<RedirectHistoricalRunToPatternLab />}
          />
          <Route
            path="/cecchino-lab/purchasability-replay"
            element={<Page><CecchinoLabPurchasabilityReplayPage /></Page>}
          />
          <Route path="/monitoraggio-segno-1" element={<Page><CecchinoHomeWinsPage /></Page>} />
          <Route
            path="/monitoraggio-segnali"
            element={<Page><CecchinoSignalsMonitoringPage /></Page>}
          />
          <Route path="/monitoraggio-moduli" element={<Page><MonitoraggioModuliPage /></Page>} />
          <Route
            path="/monitoraggio-segnali-lab"
            element={<LegacyLabRedirect module="signals" view="lab" />}
          />
          <Route path="/segnali-kpi" element={<Page><SegnaliKpiPage /></Page>} />
          <Route
            path="/cecchino/ricerca-credibilita-x"
            element={<LegacyLabRedirect module="balance-v5" view="draw-credibility" />}
          />
          <Route
            path="/cecchino/ricerca-intensita-goal"
            element={<LegacyLabRedirect module="goal-intensity-v5" view="overview" />}
          />
          <Route path="/bookmakers" element={<Page><Bookmakers /></Page>} />
          <Route path="/changelog" element={<Page><Changelog /></Page>} />
          <Route path="/data-health" element={<Page><DataHealth /></Page>} />
          <Route path="/admin" element={<Page><Admin /></Page>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
