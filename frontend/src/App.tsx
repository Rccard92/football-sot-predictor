import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Admin } from './pages/Admin'
import { Backtest } from './pages/Backtest'
import { Dashboard } from './pages/Dashboard'
import { DataHealth } from './pages/DataHealth'
import { MatchPrediction } from './pages/MatchPrediction'
import { MatchAnalysisFramework } from './pages/MatchAnalysisFramework'
import { ModelLegend } from './pages/ModelLegend'
import { Teams } from './pages/Teams'
import { UpcomingMatches } from './pages/UpcomingMatches'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<UpcomingMatches />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/data-health" element={<DataHealth />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/match-prediction" element={<MatchPrediction />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/model-legend" element={<ModelLegend />} />
          <Route path="/match-analysis-framework" element={<MatchAnalysisFramework />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
