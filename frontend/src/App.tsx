import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LegacyLabRedirect } from './components/module-monitoring/LegacyLabRedirect'
import { Admin } from './pages/Admin'
import { DataHealth } from './pages/DataHealth'
import { Changelog } from './pages/Changelog'
import { Bookmakers } from './pages/Bookmakers'
import { CecchinoPage } from './pages/CecchinoPage'
import { CecchinoSignalsMonitoringPage } from './pages/CecchinoSignalsMonitoringPage'
import { SegnaliKpiPage } from './pages/SegnaliKpiPage'
import { MonitoraggioModuliPage } from './pages/MonitoraggioModuliPage'
import { CecchinoTodayPage } from './pages/CecchinoTodayPage'
import { BetBuilderPage } from './pages/BetBuilderPage'
import { CecchinoLabPage } from './pages/CecchinoLabPage'
import { CecchinoLabPatternLabPage } from './pages/CecchinoLabPatternLabPage'
import { CecchinoLabPurchasabilityReplayPage } from './pages/CecchinoLabPurchasabilityReplayPage'
import { CecchinoHomeWinsPage } from './pages/CecchinoHomeWinsPage'

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
          <Route path="/cecchino" element={<CecchinoPage />} />
          <Route path="/cecchino-today" element={<CecchinoTodayPage />} />
          <Route path="/bet-builder" element={<BetBuilderPage />} />
          <Route path="/cecchino-lab" element={<CecchinoLabPage />} />
          <Route path="/cecchino-lab/pattern-lab" element={<CecchinoLabPatternLabPage />} />
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
            element={<CecchinoLabPurchasabilityReplayPage />}
          />
          <Route path="/monitoraggio-segno-1" element={<CecchinoHomeWinsPage />} />
          <Route path="/monitoraggio-segnali" element={<CecchinoSignalsMonitoringPage />} />
          <Route path="/monitoraggio-moduli" element={<MonitoraggioModuliPage />} />
          <Route
            path="/monitoraggio-segnali-lab"
            element={<LegacyLabRedirect module="signals" view="lab" />}
          />
          <Route path="/segnali-kpi" element={<SegnaliKpiPage />} />
          <Route
            path="/cecchino/ricerca-credibilita-x"
            element={<LegacyLabRedirect module="balance-v5" view="draw-credibility" />}
          />
          <Route
            path="/cecchino/ricerca-intensita-goal"
            element={<LegacyLabRedirect module="goal-intensity-v5" view="overview" />}
          />
          <Route path="/bookmakers" element={<Bookmakers />} />
          <Route path="/changelog" element={<Changelog />} />
          <Route path="/data-health" element={<DataHealth />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
