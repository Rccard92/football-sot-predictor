import { Card } from '../components/ui/Card'

export function Dashboard() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          Panoramica MVP: analisi Serie A e previsioni sui tiri in porta.
        </p>
      </header>
      <Card title="Benvenuto">
        <p>
          Questa area conterrà indicatori sintetici su copertura dati, ultimi aggiornamenti
          ingestion e qualità delle previsioni. Nessuna integrazione API ancora attiva.
        </p>
      </Card>
    </div>
  )
}
