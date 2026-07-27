import { useState } from 'react'
import { motion } from 'framer-motion'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { OverviewTab } from '../components/cecchino-data-lab/OverviewTab'
import { ImportWizardTab } from '../components/cecchino-data-lab/ImportWizardTab'
import { DatasetsTab } from '../components/cecchino-data-lab/DatasetsTab'
import { MatchesExplorerTab } from '../components/cecchino-data-lab/MatchesExplorerTab'
import { DataQualityTab } from '../components/cecchino-data-lab/DataQualityTab'
import { HistoricalScansTab } from '../components/cecchino-data-lab/HistoricalScansTab'
import { MatchDetailDrawer } from '../components/cecchino-data-lab/MatchDetailDrawer'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'import', label: 'Importa CSV' },
  { id: 'datasets', label: 'Dataset' },
  { id: 'matches', label: 'Partite' },
  { id: 'quality', label: 'Qualità dati' },
  { id: 'historical', label: 'Scansioni storiche' },
] as const

type TabId = (typeof TABS)[number]['id']

export function CecchinoLabPage() {
  const [tab, setTab] = useState<TabId>('overview')
  const [refreshKey, setRefreshKey] = useState(0)
  const [focusDatasetId, setFocusDatasetId] = useState<number | null>(null)
  const [drawerMatchId, setDrawerMatchId] = useState<number | null>(null)

  const bump = () => setRefreshKey((k) => k + 1)

  return (
    <CecchinoLabShell>
      <header className="border-b px-4 py-5 sm:px-6" style={{ borderColor: 'var(--lab-border)' }}>
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
          <div className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--lab-cyan)' }}>
            Cecchino Lab
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Archivio storico Football-Data
          </h1>
          <p className="mt-1 max-w-2xl text-sm" style={{ color: 'var(--lab-muted)' }}>
            Workspace dati isolato: analytics betting, import CSV, audit qualità Bet365 e scansioni
            storiche offline. Cecchino Today (Betfair) resta invariato.
          </p>
        </motion.div>

        <nav className="mt-5 flex flex-wrap gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`lab-tab rounded-t-lg px-4 py-2 text-sm font-medium ${tab === t.id ? 'lab-tab-active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <div>
        {tab === 'overview' && (
          <OverviewTab refreshKey={refreshKey} onGoImport={() => setTab('import')} />
        )}
        {tab === 'import' && (
          <ImportWizardTab
            onImported={(datasetId) => {
              bump()
              if (datasetId > 0) {
                setFocusDatasetId(datasetId)
                setTab('datasets')
              }
            }}
            onGoDatasets={() => {
              bump()
              setTab('datasets')
            }}
            onGoOverview={() => {
              bump()
              setTab('overview')
            }}
          />
        )}
        {tab === 'datasets' && (
          <DatasetsTab
            refreshKey={refreshKey}
            onOpenMatches={(id) => {
              setFocusDatasetId(id)
              setTab('matches')
            }}
            onReplaced={() => {
              bump()
            }}
          />
        )}
        {tab === 'matches' && <MatchesExplorerTab datasetId={focusDatasetId} refreshKey={refreshKey} />}
        {tab === 'quality' && (
          <DataQualityTab
            refreshKey={refreshKey}
            onOpenMatch={(id) => {
              setDrawerMatchId(id)
              setTab('matches')
            }}
          />
        )}
        {tab === 'historical' && <HistoricalScansTab refreshKey={refreshKey} />}
      </div>

      <MatchDetailDrawer matchId={drawerMatchId} onClose={() => setDrawerMatchId(null)} />
    </CecchinoLabShell>
  )
}
