import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useSearchParams } from 'react-router-dom'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { OverviewTab } from '../components/cecchino-data-lab/OverviewTab'
import { ImportWizardTab } from '../components/cecchino-data-lab/ImportWizardTab'
import { DatasetsTab } from '../components/cecchino-data-lab/DatasetsTab'
import { MatchesExplorerTab } from '../components/cecchino-data-lab/MatchesExplorerTab'
import { DataQualityTab } from '../components/cecchino-data-lab/DataQualityTab'
import { HistoricalScansTab } from '../components/cecchino-data-lab/HistoricalScansTab'
import { CecchinoRunV2Section } from '../components/cecchino-data-lab/run-v2/CecchinoRunV2Section'
import { CecchinoRunV2AnalysisTab } from '../components/cecchino-data-lab/run-v2/CecchinoRunV2AnalysisTab'
import { PatternLabTab } from '../components/cecchino-data-lab/PatternLabTab'
import { LeaguePatternAnalysisTab } from '../components/cecchino-data-lab/league-pattern-analysis/LeaguePatternAnalysisTab'
import { PatternGridTab } from '../components/cecchino-data-lab/pattern-grid/PatternGridTab'
import { MatchDetailDrawer } from '../components/cecchino-data-lab/MatchDetailDrawer'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'import', label: 'Importa CSV' },
  { id: 'datasets', label: 'Dataset' },
  { id: 'matches', label: 'Partite' },
  { id: 'quality', label: 'Qualità dati' },
  { id: 'historical', label: 'Scansioni storiche' },
  { id: 'run_v2', label: 'Run V2' },
  { id: 'pattern_lab', label: 'Pattern Lab' },
  { id: 'league_pattern_analysis', label: 'League Pattern Analysis' },
  { id: 'pattern_grid', label: 'Pattern Grid' },
] as const

type TabId = (typeof TABS)[number]['id']

function parseTab(raw: string | null): TabId {
  if (raw && TABS.some((t) => t.id === raw)) return raw as TabId
  return 'overview'
}

export function CecchinoLabPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<TabId>(() => parseTab(searchParams.get('tab')))
  const [refreshKey, setRefreshKey] = useState(0)
  const [focusDatasetId, setFocusDatasetId] = useState<number | null>(null)
  const [drawerMatchId, setDrawerMatchId] = useState<number | null>(null)

  const bump = () => setRefreshKey((k) => k + 1)

  useEffect(() => {
    const fromUrl = parseTab(searchParams.get('tab'))
    if (fromUrl !== tab) setTab(fromUrl)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const goTab = (id: TabId) => {
    setTab(id)
    const next = new URLSearchParams(searchParams)
    if (id === 'overview') next.delete('tab')
    else next.set('tab', id)
    if (id !== 'pattern_lab') next.delete('run_ids')
    if (id !== 'run_v2') next.delete('run_v2_id')
    setSearchParams(next, { replace: true })
  }

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
              onClick={() => goTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <div>
        {tab === 'overview' && (
          <OverviewTab refreshKey={refreshKey} onGoImport={() => goTab('import')} />
        )}
        {tab === 'import' && (
          <ImportWizardTab
            onImported={(datasetId) => {
              bump()
              if (datasetId > 0) {
                setFocusDatasetId(datasetId)
                goTab('datasets')
              }
            }}
            onGoDatasets={() => {
              bump()
              goTab('datasets')
            }}
            onGoOverview={() => {
              bump()
              goTab('overview')
            }}
          />
        )}
        {tab === 'datasets' && (
          <DatasetsTab
            refreshKey={refreshKey}
            onOpenMatches={(id) => {
              setFocusDatasetId(id)
              goTab('matches')
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
              goTab('matches')
            }}
          />
        )}
        {tab === 'historical' && <HistoricalScansTab refreshKey={refreshKey} />}
        {tab === 'run_v2' && (
          <>
            <CecchinoRunV2Section refreshKey={refreshKey} />
            <CecchinoRunV2AnalysisTab />
          </>
        )}
        {tab === 'pattern_lab' && <PatternLabTab />}
        {tab === 'league_pattern_analysis' && <LeaguePatternAnalysisTab />}
        {tab === 'pattern_grid' && <PatternGridTab />}
      </div>

      <MatchDetailDrawer matchId={drawerMatchId} onClose={() => setDrawerMatchId(null)} />
    </CecchinoLabShell>
  )
}
