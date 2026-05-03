import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Backtest } from './pages/Backtest'
import { Dashboard } from './pages/Dashboard'
import { DataHealth } from './pages/DataHealth'
import { MatchPrediction } from './pages/MatchPrediction'
import { Teams } from './pages/Teams'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/data-health" element={<DataHealth />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/match-prediction" element={<MatchPrediction />} />
          <Route path="/backtest" element={<Backtest />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
