import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import type {
  CecchinoSignalCellExplanation,
  CecchinoSignalExplanationsResponse,
} from '../../lib/cecchinoTodayApi'
import { getSignalExplanations } from '../../lib/cecchinoTodayApi'
import { CecchinoSignalAuditModal } from './CecchinoSignalAuditModal'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'
import {
  todayCard,
  todayCardPadding,
  todaySectionSubtitle,
  todaySectionTitle,
} from './cecchinoTodayStyles'

type Props = {
  matrix: CecchinoSignalsMatrix
  scanDate?: string | null
  todayFixtureId?: number | null
  providerFixtureId?: number | null
}

function downloadAuditJson(
  payload: CecchinoSignalExplanationsResponse,
  providerFixtureId: number | null | undefined,
) {
  const id = providerFixtureId ?? payload.fixture?.provider_fixture_id ?? 'unknown'
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cecchino-signals-audit-${id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function CecchinoSignalsCard({
  matrix,
  scanDate,
  todayFixtureId,
  providerFixtureId,
}: Props) {
  const monitoringHref =
    scanDate != null
      ? `/monitoraggio-segnali?date_from=${encodeURIComponent(scanDate)}&date_to=${encodeURIComponent(scanDate)}${
          todayFixtureId != null ? `&today_fixture_id=${todayFixtureId}` : ''
        }`
      : '/monitoraggio-segnali'

  const [analysisMode, setAnalysisMode] = useState(false)
  const [explanations, setExplanations] = useState<CecchinoSignalExplanationsResponse | null>(
    null,
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CecchinoSignalCellExplanation | null>(null)
  const [analysisFixtureId, setAnalysisFixtureId] = useState(todayFixtureId)

  if (analysisFixtureId !== todayFixtureId) {
    setAnalysisFixtureId(todayFixtureId)
    setAnalysisMode(false)
    setExplanations(null)
    setError(null)
    setLoading(false)
    setSelected(null)
  }

  const loadExplanations = useCallback(async (): Promise<CecchinoSignalExplanationsResponse | null> => {
    if (explanations) return explanations
    if (todayFixtureId == null) return null
    setLoading(true)
    setError(null)
    try {
      const res = await getSignalExplanations(todayFixtureId)
      if (res.status === 'error') {
        setError(res.message || res.code || 'Errore caricamento audit segnali')
        return null
      }
      setExplanations(res)
      return res
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento audit segnali')
      return null
    } finally {
      setLoading(false)
    }
  }, [explanations, todayFixtureId])

  const toggleAnalysis = async () => {
    if (analysisMode) {
      setAnalysisMode(false)
      setSelected(null)
      return
    }
    const res = await loadExplanations()
    if (res) setAnalysisMode(true)
  }

  const handleDownload = async () => {
    const res = await loadExplanations()
    if (res) downloadAuditJson(res, providerFixtureId)
  }

  const openCell = (rowKey: string, columnKey: string) => {
    const key = `${rowKey}:${columnKey}`
    const expl = explanations?.cells?.[key]
    if (expl) setSelected(expl)
  }

  const hasExplanation = (rowKey: string, columnKey: string) =>
    Boolean(explanations?.cells?.[`${rowKey}:${columnKey}`])

  return (
    <section className={`${todayCard} ${todayCardPadding} h-full space-y-4`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className={todaySectionTitle}>Segnali Cecchino</h3>
          <p className={todaySectionSubtitle}>Matrice SI/NO</p>
          <p className="mt-2 text-xs text-slate-500">
            Questi segnali vengono salvati nel Monitoraggio Segnali e valutati dopo
            l&apos;aggiornamento risultati.
          </p>
          <Link
            to={monitoringHref}
            className="mt-1 inline-block text-xs font-medium text-sky-700 hover:underline"
          >
            Apri monitoraggio segnali
          </Link>
          {error ? <p className="mt-2 text-xs text-amber-700">{error}</p> : null}
          {analysisMode ? (
            <p className="mt-2 text-xs text-slate-500">
              Modalità analisi: clicca un badge SI/NO per la formula
            </p>
          ) : null}
        </div>
        {todayFixtureId != null ? (
          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <button
              type="button"
              onClick={() => void toggleAnalysis()}
              disabled={loading}
              className={`rounded-md border px-2.5 py-1 text-[11px] font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 disabled:opacity-60 ${
                analysisMode
                  ? 'border-amber-300 bg-amber-50 text-amber-900'
                  : 'border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100'
              }`}
            >
              {loading ? 'Caricamento…' : analysisMode ? 'Analisi attiva' : 'ƒx Analisi segnali'}
            </button>
            <button
              type="button"
              onClick={() => void handleDownload()}
              disabled={loading}
              className="rounded-md border border-slate-300 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 disabled:opacity-60"
            >
              Scarica audit segnali
            </button>
          </div>
        ) : null}
      </div>
      <CecchinoSignalsMatrixPanel
        matrix={matrix}
        variant="embedded"
        analysisMode={analysisMode}
        onOpenCell={openCell}
        hasExplanation={hasExplanation}
      />
      {selected ? (
        <CecchinoSignalAuditModal explanation={selected} onClose={() => setSelected(null)} />
      ) : null}
    </section>
  )
}
