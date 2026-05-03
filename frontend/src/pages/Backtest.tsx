import { Card } from '../components/ui/Card'

export function Backtest() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Backtest</h1>
        <p className="mt-1 text-sm text-slate-600">
          Valutazione errori di previsione su storico (placeholder).
        </p>
      </header>
      <Card title="Metriche">
        <p>
          Risultati aggregati da{' '}
          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">prediction_backtests</code>: MAE, distribuzione errori e
          confronto tra versioni modello.
        </p>
      </Card>
    </div>
  )
}
