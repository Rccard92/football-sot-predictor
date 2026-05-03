import { Card } from '../components/ui/Card'

export function MatchPrediction() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Match Prediction</h1>
        <p className="mt-1 text-sm text-slate-600">
          Previsione expected shots on target per partita (placeholder).
        </p>
      </header>
      <Card title="Motore statistico">
        <p>
          Selezione fixture, visualizzazione feature e output da{' '}
          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">team_sot_predictions</code>. La logica di stima non è ancora
          implementata lato backend.
        </p>
      </Card>
    </div>
  )
}
