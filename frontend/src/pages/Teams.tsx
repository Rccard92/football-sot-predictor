import { Card } from '../components/ui/Card'

export function Teams() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Teams</h1>
        <p className="mt-1 text-sm text-slate-600">Elenco squadre Serie A e dettagli (placeholder).</p>
      </header>
      <Card title="Prossimi passi">
        <p>
          Lista squadre da tabella <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">teams</code>, filtri per stagione e
          link alle serie storiche dei tiri in porta.
        </p>
      </Card>
    </div>
  )
}
