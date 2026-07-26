import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { OverviewTab } from '../components/cecchino-data-lab/OverviewTab'
import { ImportWizardTab } from '../components/cecchino-data-lab/ImportWizardTab'
import { DatasetsTab } from '../components/cecchino-data-lab/DatasetsTab'
import { MatchesExplorerTab } from '../components/cecchino-data-lab/MatchesExplorerTab'
import { DataQualityTab } from '../components/cecchino-data-lab/DataQualityTab'
import { MatchDetailDrawer } from '../components/cecchino-data-lab/MatchDetailDrawer'
import { getCecchinoLabOverview, type CecchinoLabOverview } from '../lib/cecchinoLabApi'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'import', label: 'Importa CSV' },
  { id: 'datasets', label: 'Dataset' },
  { id: 'matches', label: 'Partite' },
  { id: 'quality', label: 'Qualità dati' },
] as const

type TabId = (typeof TABS)[number]['id']

export function CecchinoLabPage() {
  const [tab, setTab] = useState<TabId>('overview')
  const [overview, setOverview] = useState<CecchinoLabOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [focusDatasetId, setFocusDatasetId] = useState<number | null>(null)
  const [drawerMatchId, setDrawerMatchId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    getCecchinoLabOverview()
      .then((data) => {
        if (!cancelled) {
          setOverview(data)
          setOverviewError(null)
          setLoadingOverview(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setOverviewError(e instanceof Error ? e.message : 'Errore overview')
          setLoadingOverview(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

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
            Workspace dati isolato: import CSV, audit qualità e quote Bet365. Nessuna formula, nessuna predizione,
            nessun impatto su Cecchino Today.
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
          <OverviewTab
            overview={overview}
            loading={loadingOverview}
            error={overviewError}
            onGoImport={() => setTab('import')}
            onOpenDataset={(id) => {
              setFocusDatasetId(id)
              setTab('datasets')
            }}
          />
        )}
        {tab === 'import' && (
          <ImportWizardTab
            onImported={(datasetId) => {
              bump()
              setFocusDatasetId(datasetId)
              setTab('datasets')
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
      </div>

      <MatchDetailDrawer matchId={drawerMatchId} onClose={() => setDrawerMatchId(null)} />
    </CecchinoLabShell>
  )
}
