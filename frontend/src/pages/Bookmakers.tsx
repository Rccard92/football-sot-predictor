import { useState } from 'react'
import { ApiSportsBookmakersPanel } from '../components/bookmakers/ApiSportsBookmakersPanel'
import { SportApiOddsDiscoveryPanel } from '../components/bookmakers/SportApiOddsDiscoveryPanel'

export function Bookmakers() {
  const [apiSportsTotal, setApiSportsTotal] = useState(0)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">Bookmakers</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Discovery quote e bookmaker: lista globale API-Sports e test per evento su SportAPI. Le quote non sono
          ancora usate nei pronostici o nel consiglio giocata.
        </p>
      </header>

      <ApiSportsBookmakersPanel onTotalsChange={setApiSportsTotal} />
      <SportApiOddsDiscoveryPanel apiSportsBookmakersTotal={apiSportsTotal} />
    </div>
  )
}
