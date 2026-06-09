import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Admin } from './pages/Admin'
import { ApiDataCatalog } from './pages/ApiDataCatalog'
import { Backtest } from './pages/Backtest'
import { PredictiveSimulatorPage } from './pages/PredictiveSimulatorPage'
import { Dashboard } from './pages/Dashboard'
import { DataHealth } from './pages/DataHealth'
import { MatchPrediction } from './pages/MatchPrediction'
import { MatchAnalysisFramework } from './pages/MatchAnalysisFramework'
import { MatchVariableAudit } from './pages/MatchVariableAudit'
import { ModelDebug } from './pages/ModelDebug'
import { ModelLegend } from './pages/ModelLegend'
import { Teams } from './pages/Teams'
import { Changelog } from './pages/Changelog'
import { BetMonitoring } from './pages/BetMonitoring'
import { Bookmakers } from './pages/Bookmakers'
import { CecchinoPage } from './pages/CecchinoPage'
import { CecchinoSignalsMonitoringPage } from './pages/CecchinoSignalsMonitoringPage'
import { MonitoraggioSegnaliLab } from './pages/MonitoraggioSegnaliLab'
import { CecchinoTodayPage } from './pages/CecchinoTodayPage'
import { UpcomingMatches } from './pages/UpcomingMatches'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<UpcomingMatches />} />
          <Route path="/cecchino" element={<CecchinoPage />} />
          <Route path="/cecchino-today" element={<CecchinoTodayPage />} />
          <Route path="/monitoraggio-segnali" element={<CecchinoSignalsMonitoringPage />} />
          <Route path="/monitoraggio-segnali-lab" element={<MonitoraggioSegnaliLab />} />
          <Route path="/monitoraggio-giocate" element={<BetMonitoring />} />
          <Route path="/bookmakers" element={<Bookmakers />} />
          <Route path="/changelog" element={<Changelog />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/data-health" element={<DataHealth />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/match-prediction" element={<MatchPrediction />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/predictive-simulator" element={<PredictiveSimulatorPage />} />
          <Route path="/model-legend" element={<ModelLegend />} />
          <Route path="/api-data-catalog" element={<ApiDataCatalog />} />
          <Route path="/model-debug" element={<ModelDebug />} />
          <Route path="/match-analysis-framework" element={<MatchAnalysisFramework />} />
          <Route path="/match-variable-audit" element={<MatchVariableAudit />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
