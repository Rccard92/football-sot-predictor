import { useState } from 'react'
import { SportApiMarketsDiscoveryPanel } from '../components/bookmakers/SportApiMarketsDiscoveryPanel'
import { SportApiSotProviderScanPanel } from '../components/bookmakers/SportApiSotProviderScanPanel'
import { SportApiNextRound1x2Panel } from '../components/bookmakers/SportApiNextRound1x2Panel'
import { SportApiNextRoundSotOddsPanel } from '../components/bookmakers/SportApiNextRoundSotOddsPanel'
import { SportApiProvidersPanel } from '../components/bookmakers/SportApiProvidersPanel'
import { SportApiSelectedProviderPanel } from '../components/bookmakers/SportApiSelectedProviderPanel'
import type { SportApiOddsProviderRow } from '../lib/api'

export function Bookmakers() {
  const [providers, setProviders] = useState<SportApiOddsProviderRow[]>([])
  const [reloadKey, setReloadKey] = useState(0)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">SportAPI Bookmakers</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Provider italiani e quote 1X2 informative da SportAPI. Le quote non alimentano pronostici,
          consiglio giocata o monitoraggio.
        </p>
      </header>

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
      <SportApiNextRoundSotOddsPanel />
    </div>
  )
}
