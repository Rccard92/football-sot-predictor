import { useState } from 'react'
import { ContextBanner } from '../components/ContextBanner'
import { BookmakersDiscoveryPanel } from '../components/bookmakers/BookmakersDiscoveryPanel'
import { ApiFootballFixtureMarketsPanel } from '../components/bookmakers/ApiFootballFixtureMarketsPanel'
import { SportApiMarketsDiscoveryPanel } from '../components/bookmakers/SportApiMarketsDiscoveryPanel'
import { SportApiOddsDetailsProbePanel } from '../components/bookmakers/SportApiOddsDetailsProbePanel'
import { SportApiSotProviderScanPanel } from '../components/bookmakers/SportApiSotProviderScanPanel'
import { SportApiNextRound1x2Panel } from '../components/bookmakers/SportApiNextRound1x2Panel'
import { SportApiNextRoundSotOddsPanel } from '../components/bookmakers/SportApiNextRoundSotOddsPanel'
import { SportApiProvidersPanel } from '../components/bookmakers/SportApiProvidersPanel'
import { SportApiSelectedProviderPanel } from '../components/bookmakers/SportApiSelectedProviderPanel'
import { useCompetition } from '../contexts/CompetitionContext'
import type { SportApiOddsProviderRow } from '../lib/api'

export function Bookmakers() {
  const { selectedCompetitionId } = useCompetition()
  const [providers, setProviders] = useState<SportApiOddsProviderRow[]>([])
  const [reloadKey, setReloadKey] = useState(0)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">Bookmakers — Discovery</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Provider API-Football e SportAPI, mercati normalizzati e quote 1X2 sul prossimo turno per competizione.
          Non collegato a Cecchino né ai modelli SOT.
        </p>
      </header>

      <ContextBanner showModelSelector={false} />

      <ApiFootballFixtureMarketsPanel />

      <BookmakersDiscoveryPanel competitionId={selectedCompetitionId} />

      <details className="rounded-lg border border-slate-200 bg-slate-50/50 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-800">
          Strumenti SportAPI avanzati (legacy)
        </summary>
        <div className="mt-4 space-y-6">
          <SportApiProvidersPanel
            key={`prov-${reloadKey}`}
            onProvidersChange={setProviders}
          />
          <SportApiSelectedProviderPanel
            providers={providers}
            onRefresh={() => setReloadKey((k) => k + 1)}
          />
          <SportApiNextRound1x2Panel />
          <SportApiMarketsDiscoveryPanel />
          <SportApiSotProviderScanPanel />
          <SportApiOddsDetailsProbePanel />
          <SportApiNextRoundSotOddsPanel />
        </div>
      </details>
    </div>
  )
}
