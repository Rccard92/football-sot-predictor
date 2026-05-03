import { Card } from '../components/ui/Card'

export function DataHealth() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Data Health</h1>
        <p className="mt-1 text-sm text-slate-600">
          Stato del database e delle pipeline di ingestion (placeholder).
        </p>
      </header>
      <Card title="Controlli pianificati">
        <p>
          Qui verranno mostrati esiti di <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">GET /api/health</code>, ultimi{' '}
          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">ingestion_runs</code> e gap nelle partite o nelle statistiche.
        </p>
      </Card>
    </div>
  )
}
